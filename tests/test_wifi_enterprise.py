"""Real PEM/SSL and native WPA parsing; isolated control-failure transactions."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("enterprise", str(ROOT / "freebsd-bin/omarchy-wifi-enterprise"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
enterprise = importlib.util.module_from_spec(SPEC)
sys.dont_write_bytecode = True
LOADER.exec_module(enterprise)


class EnterpriseWifi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.material = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.material.cleanup)
        cls.certs = Path(cls.material.name)
        def openssl(*args):
            subprocess.run(["openssl", *args], cwd=cls.certs, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=Test CA",
                "-days", "1", "-keyout", "ca.key", "-out", "ca.pem")
        openssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=Test Client",
                "-keyout", "client.key", "-out", "client.csr")
        openssl("x509", "-req", "-in", "client.csr", "-CA", "ca.pem", "-CAkey", "ca.key",
                "-CAcreateserial", "-days", "1", "-out", "client.pem")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "etc").mkdir()
        self.profile = dict(schema=1, ssid='Corporate "Wi-Fi"', method="peap", identity='user"@example.test',
                            password='secret"\\parameter', ca_cert=str(self.certs / "ca.pem"),
                            domain_suffix_match="auth.example.test")

    def tls(self):
        return dict(self.profile, method="tls", client_cert=str(self.certs / "client.pem"),
                    private_key=str(self.certs / "client.key"))

    def test_requires_ca_domain_credentials_and_known_schema(self):
        for change in ({"ca_cert": ""}, {"domain_suffix_match": ""}, {"domain_suffix_match": "*.test"},
                       {"domain_suffix_match": "evil.test\nkey_mgmt=NONE"}, {"password": ""},
                       {"hidden": "false"}, {"schema": True}, {"identity": "one\ntwo"},
                       {"ssid": "é" * 17}, {"unexpected": "value"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                enterprise.validate(dict(self.profile, **change))

    def test_client_key_must_match_and_material_must_be_pem(self):
        enterprise.validate(self.tls())
        with self.assertRaises(ValueError):
            enterprise.validate(dict(self.tls(), private_key=str(self.certs / "ca.key")))
        invalid = self.root / "bad-ca.pem"
        invalid.write_text("not a CA\n")
        with self.assertRaises(ValueError):
            enterprise.validate(dict(self.profile, ca_cert=str(invalid)))

    def test_hex_fields_cannot_inject_configuration_or_log_password(self):
        rendered = enterprise.render(self.profile)
        self.assertIn("key_mgmt=WPA-EAP", rendered)
        self.assertIn("eap=PEAP", rendered)
        for name in ("ssid", "identity", "password", "domain_suffix_match", "ca_cert"):
            self.assertIn(f"\t{name}={self.profile[name].encode().hex()}\n", rendered)
            self.assertNotIn(self.profile[name], rendered)
        self.assertIn("phase2=" + b"auth=MSCHAPV2".hex(), rendered)
        self.assertNotIn("password=", enterprise.render(self.tls()))

    def test_staging_retains_material_with_private_permissions_and_target_paths(self):
        staged, directory = enterprise.stage(self.tls(), self.root / "etc/wpa_supplicant/enterprise")
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        for field in enterprise.CERT_FIELDS:
            self.assertEqual(Path(staged[field]).read_bytes(), Path(self.tls()[field]).read_bytes())
            self.assertEqual(stat.S_IMODE(Path(staged[field]).stat().st_mode), 0o600)
        rendered = enterprise.render(staged, self.root)
        self.assertNotIn(str(self.root).encode().hex(), rendered)
        self.assertIn(("/" + str(Path(staged["ca_cert"]).relative_to(self.root))).encode().hex(), rendered)

    def test_private_profile_file_required(self):
        path = self.root / "profile.json"
        path.write_text(json.dumps(self.profile))
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            enterprise.load_file(path)
        path.chmod(0o600)
        enterprise.load_file(path)
        link = self.root / "link.json"
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            enterprise.load_file(link)

    def test_private_datagram_control_and_service_failure(self):
        server_dir = self.root / "control"
        server_dir.mkdir()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.addCleanup(server.close)
        server.bind(str(server_dir / "wlan0"))
        server.settimeout(5)
        commands = []
        failures = []
        def respond():
            try:
                for response in (b"PONG\n", b"wpa_state=COMPLETED\nid=2\n", b"FAIL\n"):
                    command, address = server.recvfrom(65536)
                    commands.append(command)
                    server.sendto(response, address)
            except Exception as error:
                failures.append(error)
        worker = threading.Thread(target=respond, daemon=True)
        worker.start()
        control = enterprise.Control("wlan0", control_dir=server_dir, client_dir="/tmp")
        try:
            self.assertEqual(stat.S_IMODE(Path(control.directory.name).stat().st_mode), 0o700)
            self.assertEqual(control.request("PING"), "PONG")
            control.await_connection("2")
            with self.assertRaises(RuntimeError):
                control.request("SET_NETWORK 2 password " + self.profile["password"].encode().hex())
        finally:
            local = control.directory.name
            control.close()
        worker.join(timeout=6)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertFalse(Path(local).exists())
        self.assertEqual(commands[0], b"PING")
        self.assertEqual(commands[1], b"STATUS")
        self.assertNotIn(self.profile["password"].encode(), commands[2])

    @unittest.skipUnless(os.geteuid() == 0, "Run as root to exercise installer credential transfer")
    def test_installer_cli_transfers_private_material(self):
        profile_file = self.root / "profile.json"
        profile_file.write_text(json.dumps(self.tls()))
        profile_file.chmod(0o600)
        result = subprocess.run([sys.executable, str(ROOT / "freebsd-bin/omarchy-wifi-enterprise"),
                                 "--install", str(self.root), str(profile_file)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        config = self.root / "etc/wpa_supplicant.conf"
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
        self.assertNotIn(str(self.root).encode().hex(), config.read_text())
        certificates = list((self.root / "etc/wpa_supplicant/enterprise").glob("network-*/*"))
        self.assertEqual(len(certificates), 3)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in certificates))

    def transaction(self, fail):
        config = self.root / "etc/wpa_supplicant.conf"
        original = b'ctrl_interface=/var/run/wpa_supplicant\nnetwork={\nssid="old"\n}\n'
        config.write_bytes(original)
        commands = []
        class FakeControl:
            def request(self, command):
                commands.append(command)
                if command == "LIST_NETWORKS": return "network id / ssid / bssid / flags\n0\told\tany\t"
                if command == "GET_NETWORK 0 ssid": return '"old"'
                if command == "ADD_NETWORK": return "1"
                if command.startswith("SET_NETWORK") and fail == "set":
                    raise RuntimeError("Rejected operation")
                if command == "SAVE_CONFIG" and fail == "save":
                    config.write_bytes(b"partial update\n")
                    raise RuntimeError("Failed save")
                return "OK"
            def await_connection(self, network_id):
                if fail == "auth": raise RuntimeError("Authentication failed")
            def close(self): pass
        with self.assertRaises(RuntimeError) as error:
            enterprise.apply(self.profile, "wlan0", root=self.root, control_factory=lambda iface: FakeControl())
        self.assertNotIn(self.profile["password"], str(error.exception))
        self.assertEqual(config.read_bytes(), original)
        self.assertIn("RECONFIGURE", commands)
        self.assertEqual(list((self.root / "etc/wpa_supplicant/enterprise").iterdir()), [])

    def test_setting_failure_restores_configuration(self): self.transaction("set")
    def test_authentication_failure_restores_configuration(self): self.transaction("auth")
    def test_partial_save_failure_restores_configuration(self): self.transaction("save")

    @unittest.skipUnless(sys.platform.startswith("freebsd"), "Native FreeBSD wpa_supplicant parser")
    def test_real_wpa_supplicant_accepts_both_profiles(self):
        # The deliberately nonexistent interface prevents network/device changes.
        for profile in (self.profile, self.tls()):
            config = self.root / "wpa.conf"
            config.write_text(enterprise.render(profile))
            config.chmod(0o600)
            result = subprocess.run(["/usr/sbin/wpa_supplicant", "-D", "wired", "-i", "dawifitest999",
                                     "-c", str(config), "-d"], capture_output=True, text=True, timeout=10)
            output = result.stdout + result.stderr
            self.assertNotIn("Failed to read or parse configuration", output)
            self.assertNotIn("failed to parse", output.lower())
            self.assertIn("Failed to initialize driver interface", output)


if __name__ == "__main__":
    unittest.main()
