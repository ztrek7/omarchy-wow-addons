import json
from unittest.mock import patch
import unittest

from helpers import FakeInstall, ROOT, make_addon, make_zip, toc, library, sources, wowdir
import importlib.util

spec = importlib.util.spec_from_file_location("backend", ROOT / "backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class Backend(FakeInstall):
    def call(self, **request):
        with patch("sys.argv", ["backend.py", json.dumps(request)]), patch("builtins.print") as out:
            backend.main()
        return json.loads(out.call_args[0][0])

    def test_list(self):
        make_addon(self.addons, "Bags")
        data = self.call(action="list")
        self.assertTrue(data["ok"])
        self.assertEqual(data["setup"]["flavor"]["key"], "_classic_era_")
        self.assertEqual([a["name"] for a in data["addons"]], ["Bags"])

    def test_problem_is_reported(self):
        data = self.call(action="disable", id="local:Missing")
        self.assertFalse(data["ok"])
        self.assertIn("no longer installed", data["error"])

    def test_configure_rejects_non_wow_folder(self):
        data = self.call(action="configure", root=str(self.home))
        self.assertFalse(data["ok"])
        self.assertTrue(self.call(action="configure", flavor="_retail_")["ok"])
        self.assertEqual(self.call(action="list")["setup"]["flavor"]["key"], "_retail_")

    def test_install_from_wowinterface_then_check_and_update(self):
        v1 = make_zip({"Bar/Bar.toc": toc("Bar", Version="1")})
        v2 = make_zip({"Bar/Bar.toc": toc("Bar", Version="2")})
        details = {"id": "10", "name": "Bar", "version": "1", "updated": 1000, "download": "https://example.invalid/bar",
                   "md5": "", "author": "someone"}
        with patch.object(sources, "wowi_details", return_value=details), patch.object(sources, "fetch", return_value=v1):
            data = self.call(action="install", source="wowinterface", id="10")
        self.assertTrue(data["ok"], data)
        self.assertEqual(self.call(action="list")["addons"][0]["id"], "wowi:10")
        catalog = {"entries": [{"id": "10", "version": "2", "updated": 2000}]}
        with patch.object(sources, "refresh_catalog"), patch.object(sources, "load_catalog", return_value=catalog):
            checks = self.call(action="check")["checks"]
        self.assertEqual(checks["wowi:10"], {"state": "available", "latest": "2"})
        with patch.object(sources, "wowi_details", return_value=dict(details, version="2", updated=2000)), \
                patch.object(sources, "fetch", return_value=v2):
            results = self.call(action="update", ids=["wowi:10", "local:Nope"])["results"]
        self.assertEqual([r["ok"] for r in results], [True, False])
        addon = self.call(action="list")["addons"][0]
        self.assertEqual((addon["version"], addon["tocVersion"]), ("2", "2"))

    def test_install_local_zip(self):
        archive = self.home / "Downloads/Coords-1.0.zip"
        archive.parent.mkdir()
        archive.write_bytes(make_zip({"Coords/Coords.toc": toc("Coords")}))
        data = self.call(action="install", location=str(archive))
        self.assertTrue(data["ok"], data)
        self.assertEqual(self.call(action="list")["addons"][0]["id"], "file:coords")
        leftovers = [p.name for p in self.addons.parent.iterdir() if p.name.startswith(library.STAGING_PREFIX)]
        self.assertEqual(leftovers, [])

    def test_bad_location(self):
        data = self.call(action="install", location="nothing here")
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
