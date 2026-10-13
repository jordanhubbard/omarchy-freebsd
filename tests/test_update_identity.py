"""Updater identity and catalog behavior; no package or network mutations."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UpdateIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        OMARCHY_PATH="%%DATADIR%%", OMARCHY_UPDATE_LOGGED="1",
                        TEST_DAEMONARCHY="1", TEST_NEW="1", TEST_CATALOG="1")
        self.command("pkg", '''case "$1" in
info) test "$TEST_DAEMONARCHY" = 1 ;;
query) echo 1.0.0 ;;
rquery)
  test "$TEST_CATALOG" = 1 || exit 1
  if test "$TEST_DAEMONARCHY" = 1; then
    test "$3" = -r && test "$4" = Daemonarchy || exit 9
  fi
  for package do :; done
  if test "$package" = daemonarchy && test "$TEST_NEW" = 1; then echo 1.1.0; else echo 1.0.0; fi ;;
version) if test "$3" = "$4"; then echo =; else echo '<'; fi ;;
*) exit 99 ;;
esac
''')
        self.command("gum", 'printf "%s\\n" "$@"\n')

    def tearDown(self):
        self.tmp.cleanup()

    def command(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def run_script(self, name, *args):
        return subprocess.run(["bash", str(ROOT / "freebsd-bin" / name), *args],
                              env=self.env, text=True, capture_output=True)

    def test_daemonarchy_update_detected_without_omarchy_update(self):
        result = self.run_script("omarchy-update-available")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Daemonarchy: daemonarchy 1.0.0 -> 1.1.0", result.stdout)

    def test_current_daemonarchy(self):
        self.env["TEST_NEW"] = "0"
        result = self.run_script("omarchy-update-available")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Daemonarchy is up to date", result.stdout)

    def test_missing_catalog_is_not_up_to_date(self):
        self.env["TEST_CATALOG"] = "0"
        result = self.run_script("omarchy-update-available")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Cannot check Daemonarchy", result.stderr)
        self.assertNotIn("up to date", result.stdout)

    def test_confirmation_names_daemonarchy_sources(self):
        result = self.run_script("omarchy-update-confirm")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Ready to update Daemonarchy?", result.stdout)
        self.assertIn("jordanhubbard/daemonarchy/releases", result.stdout)
        self.assertIn("signed Daemonarchy repository", result.stdout)
        self.assertIn("FreeBSD package repositories", result.stdout)
        self.assertNotIn("basecamp/omarchy", result.stdout)

    def test_standalone_omarchy_keeps_its_identity(self):
        self.env["TEST_DAEMONARCHY"] = "0"
        result = self.run_script("omarchy-update-confirm")
        self.assertIn("Ready to update Omarchy?", result.stdout)
        self.assertNotIn("Daemonarchy", result.stdout)
        result = self.run_script("omarchy-update-available")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Omarchy is up to date", result.stdout)

    def test_space_warning_names_daemonarchy(self):
        self.command("df", "echo 'disk 9999999 9999998 1 99% /'\n")
        result = self.run_script("omarchy-update-requires-free-space")
        self.assertEqual(result.returncode, 1)
        self.assertIn("safely update Daemonarchy", result.stdout)

    def test_session_names_daemonarchy_for_the_widget(self):
        result = subprocess.run(["bash", "-c", 'source "$1"; echo "$OMARCHY_DISTRIBUTION_NAME"',
                                 "bash", str(ROOT / "env-freebsd")],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Daemonarchy")

    def test_failure_points_to_daemonarchy_support(self):
        for name in ("omarchy-update-lock", "omarchy-update-stay-awake",
                     "omarchy-update-requires-free-space"):
            self.command(name, "exit 0\n")
        self.command("omarchy-update-pkg-prune", "exit 17\n")
        result = self.run_script("omarchy-update", "-y")
        self.assertEqual(result.returncode, 17)
        self.assertIn("Daemonarchy update", result.stdout)
        self.assertIn("jordanhubbard/daemonarchy/issues", result.stderr)
        self.assertNotIn("omarchy.org/discord", result.stderr)


if __name__ == "__main__":
    unittest.main()
