import json
from unittest.mock import patch
import unittest

from helpers import FakeInstall, ROOT, make_addon, make_zip, toc, library, sources, wowdir
import catalog
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
        with patch.object(catalog, "refresh"), patch.object(catalog, "source_entries", return_value=[{"id": "10", "version": "2", "updated": 2000}]):
            checks = self.call(action="check")["checks"]
        self.assertEqual(checks["wowi:10"], {"state": "available", "latest": "2", "source": "wowinterface"})
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

    def curse(self, version="340", file_id=8939586, size=0, project="auctionator"):
        return {"project": project, "title": project.capitalize(), "fileId": file_id, "version": version, "size": size,
                "download": f"https://edge.forgecdn.net/files/8939/586/{project}", "url": f"https://www.curseforge.com/wow/addons/{project}"}

    def test_hand_install_is_checked_through_its_toc_source(self):
        make_addon(self.addons, "Auctionator", Version="339", **{"X-Website": "https://www.curseforge.com/wow/addons/auctionator"})
        make_addon(self.addons, "NoSource", Version="1")
        with patch.object(sources, "curseforge_release", return_value=self.curse("339")) as lookup:
            checks = self.call(action="check")["checks"]
        lookup.assert_called_once()
        self.assertEqual(lookup.call_args[0][0], "auctionator")
        self.assertEqual(checks, {"local:Auctionator": {"state": "current", "latest": "339", "source": "curseforge"}})
        with patch.object(sources, "curseforge_release", return_value=self.curse("340")):
            self.assertEqual(self.call(action="check")["checks"]["local:Auctionator"]["state"], "available")

    def test_updating_a_hand_install_makes_it_managed(self):
        make_addon(self.addons, "Auctionator", Version="339", **{"X-Website": "https://www.curseforge.com/wow/addons/auctionator"})
        data = make_zip({"Auctionator/Auctionator.toc": toc("Auctionator", Version="340")})
        with patch.object(sources, "curseforge_release", return_value=self.curse("340", size=len(data))), \
                patch.object(sources, "fetch", return_value=data):
            results = self.call(action="update", ids=["local:Auctionator"], sources={"local:Auctionator": "curseforge"})["results"]
        self.assertTrue(results[0]["ok"], results)
        addon = self.call(action="list")["addons"][0]
        self.assertEqual((addon["id"], addon["version"], addon["managed"]), ("curseforge:auctionator", "340", True))
        self.assertTrue((self.home / ".local/share/Trash/files/Auctionator").is_dir())
        with patch.object(sources, "curseforge_release", return_value=self.curse("340", size=len(data))):
            check = self.call(action="check")["checks"]["curseforge:auctionator"]
        self.assertEqual(check["state"], "current")

    def test_zip_installs_are_not_checked(self):
        archive = self.home / "Coords.zip"
        archive.write_bytes(make_zip({"Coords/Coords.toc": toc("Coords", **{"X-WoWI-ID": "1"})}))
        self.call(action="install", location=str(archive))
        self.assertEqual(self.call(action="check")["checks"], {})

    def test_curseforge_page_installs(self):
        data = make_zip({"Auctionator/Auctionator.toc": toc("Auctionator")})
        with patch.object(sources, "curseforge_release", return_value=self.curse(size=len(data))) as lookup, \
                patch.object(sources, "fetch", return_value=data):
            self.assertTrue(self.call(action="install", location="https://www.curseforge.com/wow/addons/auctionator")["ok"])
        self.assertEqual(lookup.call_args[0][0], "auctionator")

    def test_source_toggles_are_saved(self):
        self.assertEqual(self.call(action="list")["setup"]["sources"], {"curseforge": True, "wowinterface": True})
        self.call(action="configure", sources={"curseforge": False, "wowinterface": True})
        self.assertEqual(self.call(action="list")["setup"]["sources"]["curseforge"], False)

    def test_falls_back_to_next_source(self):
        make_addon(self.addons, "Boss", Version="v2", **{"X-WoWI-ID": "77", "X-Curse-Project-ID": "2382"})
        with patch.object(catalog, "refresh", side_effect=sources.Problem("offline")), patch.object(catalog, "source_entries", return_value=[]), \
                patch.object(sources, "curseforge_release", return_value=self.curse("v3")):
            check = self.call(action="check")["checks"]["local:Boss"]
        self.assertEqual(check, {"state": "available", "latest": "v3", "source": "curseforge"})
        with patch.object(catalog, "refresh"), patch.object(catalog, "source_entries", return_value=[]), \
                patch.object(sources, "curseforge_release", side_effect=sources.Problem("timed out")):
            check = self.call(action="check")["checks"]["local:Boss"]
        self.assertEqual(check["state"], "error")
        self.assertIn("WoWInterface: not listed", check["message"])
        self.assertIn("CurseForge: timed out", check["message"])

    def test_only_trusted_sites_are_downloaded_from(self):
        with patch.object(sources, "fetch") as fetch:
            for location in ("https://example.invalid/addon.zip", "BigWigsMods/BigWigs", "https://github.com/BigWigsMods/BigWigs",
                             "https://api.tukui.org/v1/download/elvui/x"):
                data = self.call(action="install", location=location)
                self.assertFalse(data["ok"], location)
                self.assertIn("CurseForge or WoWInterface", data["error"])
        fetch.assert_not_called()

    def test_wowinterface_page_installs(self):
        data = make_zip({"TomTom/TomTom.toc": toc("TomTom")})
        details = {"id": "7032", "name": "TomTom", "version": "4", "updated": 1, "download": "https://cdn.wowinterface.com/x", "md5": "", "author": "a"}
        with patch.object(sources, "wowi_details", return_value=details) as lookup, patch.object(sources, "fetch", return_value=data):
            self.assertTrue(self.call(action="install", location="https://www.wowinterface.com/downloads/info7032-TomTom.html")["ok"])
        self.assertEqual(lookup.call_args[0][0], "7032")

    def catalog_with(self, *entries):
        return patch.object(catalog, "load_entries", return_value=list(entries))

    def test_install_brings_required_addons(self):
        module = make_zip({"DBM-Raids/DBM-Raids.toc": toc("Raids", Dependencies="DBM-Core, DBM-GUI, Blizzard_Calendar")})
        core = make_zip({"DBM-Core/DBM-Core.toc": toc("Core", RequiredDeps="LibFoo"), "DBM-GUI/DBM-GUI.toc": toc("GUI")})
        dbm = {"name": "DBM - Deadly Boss Mods (DBM-Core)", "dirs": ["DBM-Core", "DBM-GUI"],
               "sources": [{"source": "curseforge", "id": "deadly-boss-mods", "flavours": ["vanilla_classic"], "updated": 5, "downloads": 9}]}
        other = {"name": "Someone's DBM skin", "dirs": ["DBM-Core", "Skin"], "sources": [{"source": "wowinterface", "id": "1", "gameVersions": ["1.15.7"], "updated": 9, "downloads": 1}]}
        archives = {"raids": module, "deadly-boss-mods": core}
        def release(project, game):
            return self.curse("1", size=len(archives[project]), project=project)
        downloads = []
        def fetch(url, **kwargs):
            downloads.append(url)
            return archives[url.rsplit("/", 1)[1]]
        with patch.object(sources, "curseforge_release", side_effect=release), patch.object(sources, "fetch", side_effect=fetch), \
                patch.object(catalog, "refresh"), self.catalog_with(other, dbm):
            data = self.call(action="install", source="curseforge", id="raids")
        self.assertTrue(data["ok"], data)
        self.assertEqual(data["message"].count("Also installed DBM - Deadly Boss Mods (DBM-Core), which Raids requires."), 1)
        self.assertEqual(len(downloads), 2)  # The module and DBM once, though DBM provides two required folders.
        self.assertIn("Deadly-boss-mods needs LibFoo, which isn't on CurseForge or WoWInterface.", data["message"])
        self.assertTrue((self.addons / "DBM-Core").is_dir() and (self.addons / "DBM-GUI").is_dir())
        rows = {a["id"]: a for a in self.call(action="list")["addons"]}
        self.assertEqual(rows["curseforge:raids"]["missing"], [])
        self.assertEqual(rows["curseforge:deadly-boss-mods"]["missing"], ["LibFoo"])

    def test_disabled_requirement_is_turned_on(self):
        make_addon(self.addons, "Core")
        make_addon(self.addons, "Plugin", Dependencies="Core")
        self.call(action="disable", id="local:Core")
        rows = {a["id"]: a for a in self.call(action="list")["addons"]}
        self.assertEqual((rows["local:Plugin"]["missing"], rows["local:Plugin"]["requiresDisabled"]), ([], ["Core"]))
        data = self.call(action="requirements", id="local:Plugin")
        self.assertIn("Turned on Core, which Plugin requires.", data["message"])
        self.assertTrue((self.addons / "Core").is_dir())

    def test_bad_location(self):
        data = self.call(action="install", location="nothing here")
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
