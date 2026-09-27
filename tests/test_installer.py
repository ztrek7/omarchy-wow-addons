import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT


class Installer(unittest.TestCase):
    def run_installer(self, data, *args):
        env = dict(os.environ, XDG_DATA_HOME=str(data))
        return subprocess.run([sys.executable, str(ROOT / "scripts/install.py"), *args], env=env, capture_output=True, text=True)

    @unittest.skipUnless(Path("/usr/share/omarchy/shell/Commons").is_dir(), "needs Omarchy")
    def test_install_replace_and_uninstall(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            state = data / "wow-addons/state.json"
            state.parent.mkdir(parents=True)
            state.write_text("{}")
            for _ in range(2):  # Reinstalling replaces the previous copy.
                result = self.run_installer(data)
                self.assertEqual(result.returncode, 0, result.stderr)
            app = data / "wow-addons/app"
            self.assertTrue((app / "App.qml").is_file() and (app / "ui/Theme.qml").is_file())
            self.assertFalse((app / "Smoke.qml").exists())
            self.assertTrue(os.access(app / "run", os.X_OK))
            entry = (data / "applications/wow-addons.desktop").read_text()
            self.assertIn(f'Exec="{app}/run"', entry)
            self.assertTrue((data / "icons/hicolor/scalable/apps/wow-addons.svg").is_file())
            self.assertEqual(self.run_installer(data, "--uninstall").returncode, 0)
            self.assertFalse(app.exists())
            self.assertFalse((data / "applications/wow-addons.desktop").exists())
            self.assertEqual(state.read_text(), "{}")


if __name__ == "__main__":
    unittest.main()
