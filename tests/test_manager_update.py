import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from helpers import ROOT, sources
import manager_update


class ManagerUpdate(unittest.TestCase):
    def release(self, tag):
        return patch.object(sources, "fetch", return_value=json.dumps({"tag_name": tag}))

    def test_only_newer_stable_releases_are_offered(self):
        for tag, available in [("v0.1.0", False), ("v0.2.0", False), ("v0.10.0", True)]:
            with self.subTest(tag=tag), self.release(tag), patch.object(sources, "VERSION", "0.2.0"):
                self.assertEqual(manager_update.check()["available"], available)
        with self.release("v0.9.0-rc1"), self.assertRaises(sources.Problem):
            manager_update.check()

    def test_stale_offer_cannot_install(self):
        with self.release("v1.0.0"), patch.object(manager_update, "installed_copy", return_value=True):
            with self.assertRaisesRegex(sources.Problem, "release changed"):
                manager_update.apply("0.9.0")

    @unittest.skipUnless(Path("/usr/share/omarchy/shell/Commons").is_dir(), "needs Omarchy")
    def test_update_installs_tagged_copy_without_the_original_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            data = folder / "data"
            env = dict(os.environ, XDG_DATA_HOME=str(data))
            subprocess.run(["python3", str(ROOT / "scripts/install.py")], env=env, capture_output=True, check=True)
            installed = data / "wow-addons/app"
            state = installed.parent / "state.json"
            state.write_text('{"keep": true}')
            release = folder / "release"
            shutil.copytree(ROOT, release, symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            (release / "sources.py").write_text((release / "sources.py").read_text().replace(
                f'VERSION = "{sources.VERSION}"', 'VERSION = "9.0.0"'))
            for args in (["init", "-q"], ["add", "."], ["-c", "user.name=Test", "-c", "user.email=test@localhost",
                                                       "commit", "-qm", "fixture"], ["tag", "v9.0.0"]):
                subprocess.run(["git", *args], cwd=release, check=True, capture_output=True)
            with patch.object(manager_update, "__file__", str(installed / "manager_update.py")), patch.dict(os.environ, env), \
                    patch.object(manager_update, "GIT_URL", release.as_uri()), self.release("v9.0.0"):
                self.assertIn("9.0.0", manager_update.apply("9.0.0")["message"])
            self.assertIn('VERSION = "9.0.0"', (installed / "sources.py").read_text())
            self.assertEqual(state.read_text(), '{"keep": true}')
