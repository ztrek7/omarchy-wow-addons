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
    def setUp(self):
        super().setUp()
        # The catalog counts as up to date unless a test says otherwise.
        fresh = patch.object(catalog, "refresh")
        fresh.start()
        self.addCleanup(fresh.stop)

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
        with patch.object(sources, "curseforge_release", return_value=self.curse("339")) as lookup, \
                self.listings(games={("curseforge", "auctionator"): "1.15.7"}):
            checks = self.call(action="check")["checks"]
        lookup.assert_called_once()
        self.assertEqual(lookup.call_args[0][0], "auctionator")
        self.assertEqual(checks, {"local:Auctionator": {"state": "current", "latest": "339", "source": "curseforge"}})
        with patch.object(sources, "curseforge_release", return_value=self.curse("340")), \
                self.listings(games={("curseforge", "auctionator"): "1.15.7"}):
            self.assertEqual(self.call(action="check")["checks"]["local:Auctionator"]["state"], "available")

    def test_updating_a_hand_install_makes_it_managed(self):
        make_addon(self.addons, "Auctionator", Version="339", **{"X-Website": "https://www.curseforge.com/wow/addons/auctionator"})
        data = make_zip({"Auctionator/Auctionator.toc": toc("Auctionator", Version="340")})
        with patch.object(sources, "curseforge_release", return_value=self.curse("340", size=len(data))), \
                patch.object(sources, "fetch", return_value=data), self.listings(games={("curseforge", "auctionator"): "1.15.7"}):
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
        listed = self.listings(games={("wowinterface", "77"): "1.15.7", ("curseforge", "2382"): "1.15.7"})
        listed.start()
        self.addCleanup(listed.stop)
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
        dbm = {"key": "curseforge:deadly-boss-mods", "name": "DBM - Deadly Boss Mods (DBM-Core)", "dirs": ["DBM-Core", "DBM-GUI"],
               "sources": [{"source": "curseforge", "id": "deadly-boss-mods", "flavours": ["vanilla_classic"], "updated": 5, "downloads": 9}]}
        other = {"key": "wowinterface:1", "name": "Someone's DBM skin", "dirs": ["DBM-Core", "Skin"], "sources": [{"source": "wowinterface", "id": "1", "gameVersions": ["1.15.7"], "updated": 9, "downloads": 1}]}
        archives = {"raids": module, "deadly-boss-mods": core}
        def release(project, game, listed_updated=0, other_games=False):
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

    def test_game_match_is_exact(self):
        forever = {"flavour": "forever_classic", "major": 1}
        self.assertFalse(backend.fits({"source": "wowinterface", "flavours": ["vanilla_classic"], "gameVersions": ["1.13.2"]}, forever))
        self.assertTrue(backend.fits({"source": "curseforge", "flavours": ["forever_classic"]}, forever))

    def test_disabled_requirement_is_turned_on(self):
        make_addon(self.addons, "Core")
        make_addon(self.addons, "Plugin", Dependencies="Core")
        self.call(action="disable", id="local:Core")
        rows = {a["id"]: a for a in self.call(action="list")["addons"]}
        self.assertEqual((rows["local:Plugin"]["missing"], rows["local:Plugin"]["requiresDisabled"]), ([], ["Core"]))
        data = self.call(action="requirements", id="local:Plugin")
        self.assertIn("Turned on Core, which Plugin requires.", data["message"])
        self.assertTrue((self.addons / "Core").is_dir())

    def test_falls_back_to_the_other_site(self):
        data = make_zip({"BigWigs/BigWigs.toc": toc("BigWigs", Version="v425.7")})
        details = {"id": "5086", "name": "BigWigs", "version": "v425.7", "updated": 1, "download": "https://cdn.wowinterface.com/x", "md5": "", "author": "a"}
        stale = sources.Problem("CFWidget's copy of BigWigs is out of date (its newest file is from May 12, 2022), so it can't be installed from CurseForge right now.")
        with patch.object(sources, "curseforge_release", side_effect=stale), patch.object(sources, "wowi_details", return_value=details), \
                patch.object(sources, "fetch", return_value=data), self.listings(games={("wowinterface", "5086"): "1.15.7"}):
            result = self.call(action="install", source="curseforge", id="bigwigs", alternatives=[{"source": "wowinterface", "id": "5086"}])
        self.assertTrue(result["ok"], result)
        self.assertIn("Installed BigWigs v425.7", result["message"])
        self.assertIn("CurseForge didn't work: CFWidget's copy of BigWigs is out of date", result["message"])
        self.assertEqual(self.call(action="list")["addons"][0]["id"], "wowi:5086")
        with patch.object(sources, "curseforge_release", side_effect=stale):
            result = self.call(action="install", source="curseforge", id="bigwigs")
        self.assertFalse(result["ok"])
        self.assertIn("out of date", result["error"])

    def test_stale_curseforge_install_updates_from_wowinterface(self):
        data = make_zip({"DBM-Core/DBM-Core.toc": toc("DBM", Version="12.1.0")})
        with patch.object(sources, "curseforge_release", return_value=self.curse("12.1.0", size=len(data), project="deadly-boss-mods")), \
                patch.object(sources, "fetch", return_value=data):
            self.call(action="install", source="curseforge", id="deadly-boss-mods")
        entries = [{"key": "curseforge:deadly-boss-mods", "name": "DBM", "dirs": ["DBM-Core"], "sources": [
            {"source": "curseforge", "id": "deadly-boss-mods", "numericId": "3358"}, {"source": "wowinterface", "id": "8814"}]}]
        stale = sources.Problem("CFWidget's copy of DBM is out of date.")
        with self.catalog_with(*entries), patch.object(catalog, "refresh"), patch.object(sources, "curseforge_release", side_effect=stale), \
                patch.object(catalog, "source_entries", return_value=[{"id": "8814", "version": "12.1.1", "updated": 5}]), \
                self.listings(games={("wowinterface", "8814"): "1.15.7"}):
            check = self.call(action="check")["checks"]["curseforge:deadly-boss-mods"]
        # Compared with the installed version, not the CurseForge record.
        self.assertEqual(check, {"state": "available", "latest": "12.1.1", "source": "wowinterface"})

    def test_pasted_link_falls_back_to_the_other_site(self):
        data = make_zip({"DBM-Core/DBM-Core.toc": toc("DBM")})
        details = {"id": "8814", "name": "Deadly Boss Mods", "version": "12.1.1", "updated": 1, "download": "https://cdn.wowinterface.com/x", "md5": "", "author": "a"}
        entries = [{"key": "curseforge:deadly-boss-mods", "name": "DBM", "dirs": ["DBM-Core"], "sources": [
            {"source": "curseforge", "id": "deadly-boss-mods", "numericId": "3358"}, {"source": "wowinterface", "id": "8814"}]}]
        with self.catalog_with(*entries), patch.object(sources, "curseforge_release", side_effect=sources.Problem("out of date")), \
                patch.object(sources, "wowi_details", return_value=details), patch.object(sources, "fetch", return_value=data), \
                self.listings(games={("wowinterface", "8814"): "1.15.7"}):
            result = self.call(action="install", location="curseforge.com/wow/addons/deadly-boss-mods")
        self.assertTrue(result["ok"], result)
        self.assertIn("Installed Deadly Boss Mods 12.1.1", result["message"])

    def listings(self, dates=None, games=None):
        """Pretend catalog listings: dates as {(source, id): "YYYY-MM-DD"}, and the game
        versions each site lists as {(source, id): "1.15.7"} (Classic Era, like the test install)."""
        found = {}
        for key, day in (dates or {}).items():
            found.setdefault(key, {})["updated"] = sources.iso_ms(day + "T12:00:00+00:00")
        for (source, ident), version in (games or {}).items():
            listed = {"flavours": [wowdir.game_flavour(version)]} if source == "curseforge" else {"gameVersions": [version]}
            found.setdefault((source, ident), {}).update(listed)
        return patch.object(catalog, "listing", side_effect=lambda source, ident: found.get((source, str(ident)), {}))

    def test_old_listing_on_the_other_site_is_not_used(self):
        stale = sources.Problem("CFWidget's copy of DBM is out of date.")
        with self.listings({("curseforge", "deadly-boss-mods"): "2026-09-25", ("wowinterface", "8814"): "2025-09-15"}), \
                patch.object(sources, "curseforge_release", side_effect=stale), patch.object(sources, "wowi_details") as wowi:
            result = self.call(action="install", source="curseforge", id="deadly-boss-mods", alternatives=[{"source": "wowinterface", "id": "8814"}])
        wowi.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertIn("WoWInterface's listing hasn't been updated since September 15, 2025", result["error"])
        self.assertIn("add the .zip", result["error"])

    def test_update_check_never_offers_an_older_version(self):
        make_addon(self.addons, "Questie", Version="v12.0.1", **{"X-WoWI-ID": "24994", "X-Curse-Project-ID": "334372"})
        with self.listings({("curseforge", "334372"): "2026-09-26", ("wowinterface", "24994"): "2021-03-26"},
                           {("curseforge", "334372"): "1.15.7", ("wowinterface", "24994"): "1.15.7"}), patch.object(catalog, "refresh"), \
                patch.object(catalog, "source_entries", return_value=[{"id": "24994", "version": "6.2.5", "updated": 1}]), \
                patch.object(sources, "curseforge_release", return_value=self.curse("v12.0.1", project="questie")):
            check = self.call(action="check")["checks"]["local:Questie"]
        self.assertEqual(check, {"state": "current", "latest": "v12.0.1", "source": "curseforge"})

    def install_curseforge(self, version, *folders):
        data = make_zip({f"{name}/{name}.toc": toc(name, Version=version) for name in folders})
        with patch.object(sources, "curseforge_release", return_value=self.curse(version, size=len(data), project="boss")), \
                patch.object(sources, "fetch", return_value=data):
            self.assertTrue(self.call(action="install", source="curseforge", id="boss")["ok"])

    def boss_on_both_sites(self, wowi_version):
        entries = [{"key": "curseforge:boss", "name": "Boss", "dirs": ["Boss"], "sources": [
            {"source": "curseforge", "id": "boss", "numericId": "2382"}, {"source": "wowinterface", "id": "77"}]}]
        details = {"id": "77", "name": "Boss", "version": wowi_version, "updated": 9, "download": "https://cdn.wowinterface.com/x", "md5": "", "author": "a"}
        return entries, details

    def test_other_sites_older_copy_is_never_an_update(self):
        self.install_curseforge("2.0", "Boss")
        entries, details = self.boss_on_both_sites("1.0")
        down = sources.Problem("CFWidget is down.")
        with self.catalog_with(*entries), patch.object(catalog, "refresh"), patch.object(sources, "curseforge_release", side_effect=down), \
                patch.object(catalog, "source_entries", return_value=[{"id": "77", "version": "1.0", "updated": 9}]), \
                self.listings(games={("wowinterface", "77"): "1.15.7"}):
            check = self.call(action="check")["checks"]["curseforge:boss"]
        self.assertEqual(check, {"state": "current", "latest": "1.0", "source": "wowinterface"})
        # Updating anyway (the check found 2.1 on CurseForge, whose download then failed) doesn't fall back to 1.0.
        with self.catalog_with(*entries), patch.object(sources, "curseforge_release", side_effect=down), \
                patch.object(sources, "wowi_details", return_value=details), patch.object(sources, "fetch") as fetch, \
                self.listings(games={("wowinterface", "77"): "1.15.7"}):
            result = self.call(action="update", ids=["curseforge:boss"], sources={"curseforge:boss": "curseforge"})["results"][0]
        fetch.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertIn("WoWInterface: its newest file (1.0) isn't newer than the installed 2.0.", result["message"])
        self.assertEqual(self.call(action="list")["addons"][0]["version"], "2.0")

    def test_a_release_candidate_is_not_newer_than_the_release(self):
        self.install_curseforge("2.0", "Boss")
        entries, details = self.boss_on_both_sites("2.0-rc1")
        down = sources.Problem("CFWidget is down.")
        listed = self.listings(games={("wowinterface", "77"): "1.15.7"})
        with self.catalog_with(*entries), patch.object(sources, "curseforge_release", side_effect=down), \
                patch.object(catalog, "source_entries", return_value=[{"id": "77", "version": "2.0-rc1", "updated": 9}]), listed:
            self.assertEqual(self.call(action="check")["checks"]["curseforge:boss"]["state"], "current")
        with self.catalog_with(*entries), patch.object(sources, "curseforge_release", side_effect=down), \
                patch.object(sources, "wowi_details", return_value=details), patch.object(sources, "fetch") as fetch, listed:
            result = self.call(action="update", ids=["curseforge:boss"])["results"][0]
        fetch.assert_not_called()
        self.assertIn("isn't newer than the installed 2.0", result["message"])

    def test_unclear_versions_are_not_offered_as_updates(self):
        make_addon(self.addons, "Boss", Version="2.0", **{"X-Curse-Project-ID": "2382"})
        listed = self.listings(games={("curseforge", "2382"): "1.15.7"})
        with patch.object(sources, "curseforge_release", return_value=self.curse("2.0-12-gabc123")), listed:
            check = self.call(action="check")["checks"]["local:Boss"]
        self.assertEqual(check["state"], "unknown")
        self.assertIn("isn't clear whether that's newer than yours (2.0)", check["message"])
        with patch.object(sources, "curseforge_release", return_value=self.curse("2.0-12-gabc123")), \
                patch.object(sources, "fetch") as fetch, listed:
            result = self.call(action="update", ids=["local:Boss"])["results"][0]
        fetch.assert_not_called()
        self.assertIn("can't tell whether its newest file (2.0-12-gabc123) is newer than the installed 2.0", result["message"])

    def test_sites_a_hand_install_names_must_list_this_game(self):
        # The TOC names both sites; WoWInterface only has a Retail build.
        make_addon(self.addons, "Boss", Version="1.0", **{"X-WoWI-ID": "77", "X-Curse-Project-ID": "2382"})
        details = {"id": "77", "name": "Boss", "version": "3.0", "updated": 9, "download": "https://cdn.wowinterface.com/x", "md5": "", "author": "a"}
        listed = self.listings(games={("wowinterface", "77"): "12.1.0", ("curseforge", "2382"): "1.15.7"})
        with patch.object(sources, "curseforge_release", side_effect=sources.Problem("CFWidget is down.")), \
                patch.object(sources, "wowi_details", return_value=details) as wowi, patch.object(sources, "fetch") as fetch, listed:
            check = self.call(action="check")["checks"]["local:Boss"]
            result = self.call(action="update", ids=["local:Boss"], sources={"local:Boss": "wowinterface"})["results"][0]
        self.assertEqual(check["state"], "error")
        self.assertNotIn("WoWInterface", check["message"])
        wowi.assert_not_called()
        fetch.assert_not_called()
        self.assertFalse(result["ok"])
        with self.listings(games={("wowinterface", "77"): "12.1.0"}):
            check = self.call(action="check")["checks"]["local:Boss"]
        self.assertEqual(check, {"state": "unknown", "message": "Neither site lists Boss for WoW Classic Era, so it isn't updated from them."})

    def test_curseforge_only_crosses_games_when_asked_and_not_listed_here(self):
        seen = {}
        def release(project, game, listed_updated=0, other_games=False):
            seen[project] = other_games
            return self.curse("1", project=project)
        listed = self.listings(games={("curseforge", "here"): "1.15.7", ("curseforge", "elsewhere"): "1.60.1"})
        with patch.object(sources, "curseforge_release", side_effect=release), listed:
            for project in ("here", "elsewhere", "unknown"):
                backend.curseforge_release(project, self.game, other_games=True)
            self.assertEqual(seen, {"here": False, "elsewhere": True, "unknown": False})
            backend.curseforge_release("elsewhere", self.game)
            self.assertFalse(seen["elsewhere"])

    def cfwidget_files(self, *files):
        """CFWidget's answer for project 'boss', with (id, version, game version) files."""
        data = {"title": "Boss", "id": 2382, "urls": {"curseforge": "https://www.curseforge.com/wow/addons/boss"},
                "files": [{"id": i, "name": f"Boss-{v}.zip", "display": v, "type": "release", "versions": [g],
                           "filesize": len(self.boss_zip(v)), "uploaded_at": f"2026-0{n + 1}-01T00:00:00Z"} for n, (i, v, g) in enumerate(files)]}
        return patch.object(sources, "cfwidget", return_value=data)

    def boss_zip(self, version):
        return make_zip({f"Boss/Boss.toc": toc("Boss", Version=version)})

    def fetch_boss(self, url, **kwargs):
        return self.boss_zip(url.rsplit("-", 1)[1].removesuffix(".zip"))

    def test_updates_never_switch_to_another_games_file(self):
        # Installed for Classic Era; later CurseForge only lists Boss for Forever, with a newer Forever file.
        with self.cfwidget_files((1001, "1.0", "1.15.7")), patch.object(sources, "fetch", side_effect=self.fetch_boss), \
                self.listings(games={("curseforge", "boss"): "1.15.7"}):
            self.assertTrue(self.call(action="install", source="curseforge", id="boss")["ok"])
        forever_only = self.listings(games={("curseforge", "boss"): "1.60.1", ("curseforge", "2382"): "1.60.1"})
        with self.cfwidget_files((1001, "1.0", "1.15.7"), (1002, "2.0", "1.60.1")), forever_only:
            self.assertEqual(self.call(action="check")["checks"]["curseforge:boss"]["state"], "current")
        with self.cfwidget_files((1002, "2.0", "1.60.1")), patch.object(sources, "fetch", side_effect=self.fetch_boss) as fetch, forever_only:
            check = self.call(action="check")["checks"]["curseforge:boss"]
            result = self.call(action="update", ids=["curseforge:boss"])["results"][0]
        self.assertEqual(check["state"], "error")
        self.assertIn("no release of Boss for this game version", check["message"])
        self.assertFalse(result["ok"])
        fetch.assert_not_called()
        self.assertEqual(self.call(action="list")["addons"][0]["version"], "1.0")

    def test_a_chosen_other_game_install_keeps_updating_from_that_game(self):
        forever_only = self.listings(games={("curseforge", "boss"): "1.60.1", ("curseforge", "2382"): "1.60.1"})
        with self.cfwidget_files((1002, "2.0", "1.60.1")), patch.object(sources, "fetch", side_effect=self.fetch_boss), forever_only:
            self.assertTrue(self.call(action="install", source="curseforge", id="boss")["ok"])
        self.assertTrue(library.packages(library.load_state(), self.game)[0]["otherGame"])
        with self.cfwidget_files((1002, "2.0", "1.60.1"), (1003, "2.1", "1.60.1")), patch.object(sources, "fetch", side_effect=self.fetch_boss), forever_only:
            self.assertEqual(self.call(action="check")["checks"]["curseforge:boss"]["state"], "available")
            self.assertTrue(self.call(action="update", ids=["curseforge:boss"])["results"][0]["ok"])
        self.assertEqual(self.call(action="list")["addons"][0]["version"], "2.1")

    def test_same_site_update_needs_a_newer_file(self):
        self.install_curseforge("2.0", "Boss")
        with patch.object(sources, "curseforge_release", return_value=self.curse("1.9", file_id=8939585, project="boss")):
            self.assertEqual(self.call(action="check")["checks"]["curseforge:boss"]["state"], "current")
        with patch.object(sources, "curseforge_release", return_value=self.curse("2.1", file_id=8939587, project="boss")):
            self.assertEqual(self.call(action="check")["checks"]["curseforge:boss"]["state"], "available")

    def test_update_from_the_other_site_retires_dropped_modules(self):
        self.install_curseforge("2.0", "Boss", "Boss_Old")
        entries, details = self.boss_on_both_sites("2.1")
        data = make_zip({"Boss/Boss.toc": toc("Boss", Version="2.1")})
        with self.catalog_with(*entries), patch.object(sources, "curseforge_release", side_effect=sources.Problem("CFWidget is down.")), \
                patch.object(sources, "wowi_details", return_value=details), patch.object(sources, "fetch", return_value=data), \
                self.listings(games={("wowinterface", "77"): "1.15.7"}):
            result = self.call(action="update", ids=["curseforge:boss"])["results"][0]
        self.assertTrue(result["ok"], result)
        self.assertFalse((self.addons / "Boss_Old").exists())
        addons = self.call(action="list")["addons"]
        self.assertEqual([(a["id"], [d["name"] for d in a["dirs"]]) for a in addons], [("wowi:77", ["Boss"])])

    def test_fallback_to_another_games_build_is_not_used(self):
        stale = sources.Problem("CFWidget's copy of BigWigs is out of date.")
        with patch.object(sources, "curseforge_release", side_effect=stale), patch.object(sources, "wowi_details") as wowi, \
                self.listings(games={("wowinterface", "5086"): "12.1.0"}):
            result = self.call(action="install", source="curseforge", id="bigwigs", alternatives=[{"source": "wowinterface", "id": "5086"}])
        wowi.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertIn("WoWInterface doesn't list it for WoW Classic Era, so it wasn't tried.", result["error"])
        self.assertNotIn("add the .zip", result["error"])

    def test_update_check_ignores_another_games_listing(self):
        self.install_curseforge("2.0", "Boss")
        entries, _ = self.boss_on_both_sites("3.0")
        with self.catalog_with(*entries), patch.object(catalog, "refresh"), \
                patch.object(sources, "curseforge_release", side_effect=sources.Problem("CFWidget is down.")), \
                patch.object(catalog, "source_entries", return_value=[{"id": "77", "version": "3.0", "updated": 9}]), \
                self.listings(games={("wowinterface", "77"): "12.1.0"}):
            data = self.call(action="check")
        self.assertEqual(data["checks"]["curseforge:boss"]["state"], "error")
        self.assertEqual(data["game"], str(self.addons))

    def test_requirements_of_an_installed_requirement_are_installed(self):
        make_addon(self.addons, "Core", Dependencies="LibThing")
        make_addon(self.addons, "Plugin", Dependencies="Core")
        self.call(action="disable", id="local:Core")
        lib = {"key": "curseforge:libthing", "name": "LibThing", "dirs": ["LibThing"],
               "sources": [{"source": "curseforge", "id": "libthing", "flavours": ["vanilla_classic"], "updated": 5, "downloads": 9}]}
        data = make_zip({"LibThing/LibThing.toc": toc("LibThing")})
        with patch.object(sources, "curseforge_release", return_value=self.curse("1", size=len(data), project="libthing")), \
                patch.object(sources, "fetch", return_value=data), patch.object(catalog, "refresh"), self.catalog_with(lib):
            message = self.call(action="requirements", id="local:Plugin")["message"]
        self.assertIn("Turned on Core, which Plugin requires.", message)
        self.assertIn("Also installed LibThing, which Core requires.", message)
        rows = {a["id"]: a for a in self.call(action="list")["addons"]}
        self.assertEqual((rows["local:Core"]["state"], rows["local:Core"]["missing"]), ("enabled", []))

    def test_bad_location(self):
        data = self.call(action="install", location="nothing here")
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
