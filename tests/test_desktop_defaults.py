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
                         "GNU_COREUTILS": "gfind", "PYTHON_CMD": sys.executable,
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

    def test_real_upstream_menu_has_native_package_paths(self):
        source = Path(os.environ["OMARCHY_TEST_MENU"])
        menu = self.tree / "default/omarchy/omarchy-menu.jsonc"
        shutil.copyfile(source, menu)
        shutil.copyfile(ROUTER, self.tree / "bin/omarchy")
        # Unknown future upstream apps are excluded until reviewed.
        (self.tree / "applications/NewLinuxApp.desktop").write_text("[Desktop Entry]\n")
        unsafe = self.tree / "bin/omarchy-windows-vm"
        unsafe.write_text("#!/bin/sh\necho should-not-run\n")
        unsafe.chmod(0o755)
        linux_probes = ("omarchy-network-band", "omarchy-network-speedtest", "omarchy-disk-speedtest",
                        "omarchy-network-password", "omarchy-dev-install-ydoo", "omarchy-dev-pkg-test",
                        "omarchy-pkg-aur-add", "omarchy-update-aur-pkgs", "omarchy-plymouth-set",
                        "omarchy-hibernation-setup", "omarchy-reinstall-configs", "omarchy-upgrade-to-quattro",
                        "omarchy-refresh-limine", "omarchy-refresh-pacman", "omarchy-install-hermes-cli",
                        "omarchy-launch-openclaw", "omarchy-openclaw-onboard", "omarchy-voxtype-install",
                        "omarchy-install-service-sunshine", "omarchy-remove-service-1password",
                        "omarchy-install-gaming-gpu-lib32", "omarchy-agent")
        for name in linux_probes:
            path = self.tree / "bin" / name
            path.write_text("#!/bin/sh\n# omarchy:summary=Unsupported Linux action\necho should-not-run\n")
            path.chmod(0o755)
        hooks = self.tree / "install/user/first-run"
        hooks.mkdir(parents=True)
        for name in ("setup-agent.hook", "install-voxtype.hook", "setup-fingerprint.hook"):
            (hooks / name).write_text("#!/bin/sh\necho should-not-run\n")
        shared = self.tree / "bin/omarchy-launch-floating-terminal-with-presentation"
        shared.write_text("#!/bin/sh\necho native-terminal\n")
        bindings = self.tree / "default/hypr/bindings"
        bindings.mkdir(parents=True)
        (bindings / "applications.lua").write_text(
            Path(os.environ.get("OMARCHY_TEST_BINDINGS", str(Path(os.environ["OMARCHY_TEST_MENU"]).parent / "upstream/default/hypr/bindings/applications.lua"))).read_text())
        self.adapt()
        self.assertNotIn('"Docker"', (bindings / "applications.lua").read_text())
        self.assertNotIn('omarchy = "spotify"', (bindings / "applications.lua").read_text())
        self.assertIn('"Browser"', (bindings / "applications.lua").read_text())
        result = subprocess.run([str(unsafe), "install"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not supported on FreeBSD", result.stderr)
        self.assertNotIn("should-not-run", result.stdout)
        for name in linux_probes:
            result = subprocess.run([str(self.tree / "bin" / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("not supported on FreeBSD", result.stderr)
            self.assertNotIn("should-not-run", result.stdout)
        self.assertIn("native-terminal", shared.read_text())
        routes = subprocess.run(["bash", str(self.tree / "bin/daemonarchy"), "commands", "--json"],
                                capture_output=True, text=True)
        self.assertEqual(routes.returncode, 0, routes.stderr)
        visible = {row['binary'] for row in json.loads(routes.stdout)['commands']}
        self.assertFalse(visible.intersection(linux_probes), visible.intersection(linux_probes))
        for hook in hooks.iterdir():
            result = subprocess.run(["sh", str(hook)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
        entries = {}
        for line in menu.read_text().splitlines():
            if line.strip().startswith('"'):
                entries.update(json.loads("{" + line.strip().rstrip(",") + "}"))
        for key, value in entries.items():
            action = value.get("action", "")
            self.assertNotIn("omarchy-install-browser", action)
            self.assertNotIn("omarchy-install-dev-env", action)
            self.assertNotIn("omarchy-pkg-aur", action)
            self.assertFalse(key.startswith("update.channel"))
            self.assertFalse(key.startswith("setup.default.agent"))
            self.assertNotIn("plymouth", action)
            self.assertNotIn("cryptsetup", action)
        self.assertEqual(entries["install.package"]["action"], "uwsm-app -- octopkg")
        self.assertEqual(entries["remove.package"]["action"], "uwsm-app -- octopkg")
        self.assertEqual(entries["learn.arch"]["label"], "FreeBSD Handbook")
        self.assertFalse((self.tree / "applications/NewLinuxApp.desktop").exists())
        self.assertEqual(entries["setup.default.editor.helix"]["action"], "omarchy-default-editor hx")
        self.assertIn("zedit", entries["setup.default.editor.zed"]["when"])
        self.assertIn("system.reboot", entries)
        self.assertIn("trigger.capture.screenshot", entries)
        self.assertNotIn("trigger.tests.network-speedtest", entries)
        self.assertNotIn("trigger.tests.disk-speedtest", entries)

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
    def test_webapp_uses_chromium_and_preserves_url(self):
        url = 'https://example.test/a%20b?x="quoted"&y=$(literal)&z=`literal`'
        result = self.browser("firefox.desktop", "--webapp", url)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(Path(self.env["TEST_OUTPUT"]).read_text()),
                         ["--configured=a b", "--app=" + url])
        self.assertNotEqual(self.browser("", "--webapp", "file:///tmp/a").returncode, 0)

    @unittest.skipUnless(sys.platform.startswith("freebsd"), "Native GIO launch test on FreeBSD")
    def test_browser_rejects_invalid_desktop_id(self):
        for desktop in ("/tmp/browser.desktop", "--help.desktop", "bad\nvalue.desktop"):
            self.assertNotEqual(self.browser(desktop).returncode, 0)
        self.assertFalse(Path(self.env["TEST_OUTPUT"]).exists())

    def test_seed_existing_home_keeps_choices_and_completes(self):
        home = self.work / "home"
        (home / ".config").mkdir(parents=True)
        home.chmod(0o700)
        (home / ".config/choice").write_text("custom")
        skel = self.tree / "skel"
        (skel / ".config").mkdir(parents=True)
        (skel / ".config/choice").write_text("upstream")
        (skel / ".config/added").write_text("new")
        extra = self.tree / "skel.d/daemonarchy/.config"
        extra.mkdir(parents=True)
        (extra / "added").write_text("native")
        result = subprocess.run(["bash", str(self.substituted("seed-user"))],
                                env={**self.env, "HOME": str(home)}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((home / ".config/choice").read_text(), "custom")
        self.assertEqual((home / ".config/added").read_text(), "native")
        self.assertEqual(home.stat().st_mode & 0o777, 0o700)
        self.assertTrue((home / ".local/state/omarchy/freebsd-seeded").is_file())

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
