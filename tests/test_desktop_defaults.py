"""Use the real upstream router; set OMARCHY_TEST_ROUTER or install Omarchy."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = Path(os.environ.get("OMARCHY_TEST_ROUTER", "/usr/local/bin/omarchy"))


class DesktopDefaults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.tree = self.work / "tree"
        for folder in ("bin", "applications", "default/applications", "default/omarchy", "config"):
            (self.tree / folder).mkdir(parents=True, exist_ok=True)
        self.env = dict(os.environ)
        self.bin = self.work / "tools"
        self.bin.mkdir()
        self.env["PATH"] = f"{self.bin}:{os.environ['PATH']}"
        self.env["TEST_OUTPUT"] = str(self.work / "args.json")

    def command(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def substituted(self, name):
        text = (ROOT / name).read_text()
        substitutions = {"DATADIR": str(self.tree), "PREFIX": "/usr/local",
                         "LOCALBASE": "/usr/local", "PREFIX_SHARE": "applications",
                         "GNU_COREUTILS": "gfind", "PYTHON_CMD": "/usr/local/bin/python3",
                         "PERL": "/usr/local/bin/perl"}
        for key, value in substitutions.items():
            text = text.replace(f"%%{key}%%", value)
        path = self.work / Path(name).name
        path.write_text(text)
        return path

    def adapt(self):
        result = subprocess.run(["bash", str(self.substituted("freebsdize.in")),
                                 "--in-place", str(self.tree)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_router_help_dispatch_metadata_and_exit_status(self):
        self.assertTrue(ROUTER.is_file(), "Set OMARCHY_TEST_ROUTER to the upstream router")
        shutil.copyfile(ROUTER, self.tree / "bin/omarchy")
        probe = self.tree / "bin/omarchy-probe"
        probe.write_text(f'#!{shutil.which("bash")}\n' + '''
# omarchy:summary=Inspect argument forwarding
# omarchy:args=[values...]
# omarchy:examples=omarchy probe example
# omarchy:aliases=omarchy inspect
printf '%s\\n' "$@"
exit 23
''')
        probe.chmod(0o755)
        for name in ("vm", "dev-setup"):
            native = self.tree / ("bin/daemonarchy-" + name)
            native.write_text(f'#!{shutil.which("bash")}\n' + '''
# omarchy:summary=Native FreeBSD helper
# omarchy:args=[values...]
printf '%s\\n' "$@"
exit 17
''')
            native.chmod(0o755)
        self.adapt()
        command = ["bash", str(self.tree / "bin/daemonarchy")]
        help_result = subprocess.run(command + ["--help"], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Daemonarchy command center", help_result.stdout)
        self.assertNotIn("omarchy ", help_result.stdout)
        for route in ("probe", "inspect"):
            result = subprocess.run(command + [route, "a b", "$(literal)", "--private"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["a b", "$(literal)", "--private"])
        result = subprocess.run(command + ["probe", "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("daemonarchy probe example", result.stdout)
        self.assertNotIn("omarchy ", result.stdout)
        result = subprocess.run(command + ["commands", "--json"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("daemonarchy probe", json.dumps(json.loads(result.stdout)))
        self.assertIn("daemonarchy vm", result.stdout)
        for route in (("vm",), ("dev", "setup")):
            result = subprocess.run(command + list(route) + ["native argument"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 17, result.stderr)
            self.assertEqual(result.stdout, "native argument\n")
            result = subprocess.run(command + list(route) + ["--help"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("daemonarchy " + " ".join(route), result.stdout)
        result = subprocess.run(command + ["dev", "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("daemonarchy dev setup", result.stdout)

    def test_linux_docker_entries_removed_and_browser_ids_adapted(self):
        (self.tree / "applications/Docker.desktop").write_text("[Desktop Entry]\nName=Docker\n")
        menu = self.tree / "default/omarchy/omarchy-menu.jsonc"
        menu.write_text('''{
"install.development.docker-dbs": {"action":"docker"},
"setup.security.sudoless-docker": {"action":"docker"},
"remove.security.sudoless-docker": {"action":"docker"},
"system.reboot": {"action":"systemctl reboot"}
}
''')
        mime = self.tree / "default/applications/mimeapps.list"
        mime.write_text("[Default Applications]\nx-scheme-handler/https=chromium.desktop\n")
        self.adapt()
        self.assertFalse((self.tree / "applications/Docker.desktop").exists())
        self.assertNotIn("docker", menu.read_text())
        self.assertIn("system.reboot", menu.read_text())
        self.assertIn("chromium-browser.desktop", mime.read_text())

    def browser(self, desktop, *args):
        self.command("xdg-settings", 'printf "%s" "$TEST_DESKTOP"\n')
        self.command("xdg-mime", "exit 1\n")
        applications = self.work / "data/applications"
        applications.mkdir(parents=True, exist_ok=True)
        capture = self.work / "capture.py"
        capture.write_text('import json,os,sys\nopen(os.environ["TEST_OUTPUT"],"w").write(json.dumps(sys.argv[1:]))\n')
        for name in ("chromium-browser.desktop", "firefox.desktop"):
            (applications / name).write_text(
                f'[Desktop Entry]\nType=Application\nName=Test browser\n'
                f'Exec="{sys.executable}" "{capture}" "--configured=a b" %U\n')
        self.env["XDG_DATA_HOME"] = str(applications.parent)
        self.env["TEST_DESKTOP"] = desktop
        Path(self.env["TEST_OUTPUT"]).unlink(missing_ok=True)
        result = subprocess.run([sys.executable, str(ROOT / "freebsd-bin/omarchy-launch-browser"), *args],
                                env=self.env, capture_output=True, text=True)
        if result.returncode == 0:
            deadline = time.monotonic() + 5
            while not Path(self.env["TEST_OUTPUT"]).exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(Path(self.env["TEST_OUTPUT"]).exists(), "GIO did not execute the browser")
        return result

    @unittest.skipUnless(sys.platform.startswith("freebsd"), "Native GIO launch test on FreeBSD")
    def test_browser_fallback_and_argument_boundaries(self):
        result = self.browser("", "https://example.test/a?x=a b", "--private")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(Path(self.env["TEST_OUTPUT"]).read_text()),
                         ["--configured=a b", "https://example.test/a?x=a b", "--incognito"])
        result = self.browser("firefox.desktop", "--private")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(Path(self.env["TEST_OUTPUT"]).read_text()),
                         ["--configured=a b", "--private-window"])

    @unittest.skipUnless(sys.platform.startswith("freebsd"), "Native GIO launch test on FreeBSD")
    def test_browser_rejects_invalid_desktop_id(self):
        for desktop in ("/tmp/browser.desktop", "--help.desktop", "bad\nvalue.desktop"):
            self.assertNotEqual(self.browser(desktop).returncode, 0)
        self.assertFalse(Path(self.env["TEST_OUTPUT"]).exists())

    def test_already_seeded_home_migration_preserves_custom_settings(self):
        home = self.work / "home"
        apps = home / ".local/share/applications"
        apps.mkdir(parents=True)
        marker = home / ".local/state/omarchy/freebsd-seeded"
        marker.parent.mkdir(parents=True)
        marker.touch()
        source = self.tree / "default/applications/mimeapps.list"
        source.write_text("[Default Applications]\nx-scheme-handler/https=chromium-browser.desktop\n")
        docker = apps / "Docker.desktop"
        docker.write_text("[Desktop Entry]\nExec=xdg-terminal-exec --app-id=TUI.tile -e omarchy-launch-docker-tui\n")
        seed = self.substituted("seed-user")
        env = dict(self.env, HOME=str(home))
        subprocess.run(["bash", str(seed)], env=env, check=True)
        self.assertFalse(docker.exists())
        mime = home / ".config/mimeapps.list"
        self.assertEqual(mime.read_text(), source.read_text())
        mime.write_text("custom browser\n")
        docker.write_text("[Desktop Entry]\nExec=docker --host ssh://remote ps\n")
        subprocess.run(["bash", str(seed)], env=env, check=True)
        self.assertEqual(mime.read_text(), "custom browser\n")
        self.assertTrue(docker.exists())


if __name__ == "__main__":
    unittest.main()
