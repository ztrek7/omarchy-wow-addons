import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from helpers import FakeInstall, sources
import catalog


def cf(slug, name, dirs, numeric, same=(), downloads=100):
    return {"id": slug, "numericId": numeric, "name": name, "url": f"https://www.curseforge.com/wow/addons/{slug}", "flavours": ["vanilla_classic"],
            "downloads": downloads, "updated": 1000, "dirs": list(dirs), "sameAs": [list(x) for x in same]}


def wowi(uid, name, dirs, downloads=50):
    return {"id": uid, "name": name, "author": "someone", "category": "Map", "version": "1", "updated": 2000, "downloads": downloads,
            "monthly": 1, "favorites": 2, "gameVersions": ["1.15.7"], "dirs": list(dirs), "thumb": "", "url": "https://www.wowinterface.com/"}


def names(merged):
    return sorted(sorted(f"{r['source']}:{r['id']}" for r in e["sources"]) for e in merged)


class Merge(unittest.TestCase):
    def test_linked_listings_merge(self):
        merged = catalog.merge({"curseforge": {"entries": [cf("tomtom", "TomTom", ["TomTom"], "1", same=[("wowinterface", "7"), ("wago", "abc123")])]},
                                "wowinterface": {"entries": [wowi("7", "TomTom (Classic)", ["TomTomX"])]}})
        self.assertEqual(names(merged), [["curseforge:tomtom", "wago:abc123", "wowinterface:7"]])
        self.assertEqual(merged[0]["author"], "someone")
        self.assertEqual(merged[0]["sources"][0]["source"], "curseforge")

    def test_name_and_folder_match_across_sites(self):
        merged = catalog.merge({"curseforge": {"entries": [cf("dbm", "DBM - Deadly Boss Mods (DBM-Core)", ["DBM-Core", "DBM-GUI"], "2")]},
                                "wowinterface": {"entries": [wowi("8", "Deadly Boss Mods", ["DBM-Core"]), wowi("9", "GatherLite", ["GatherLite-6.0.0"])]},
                                "tukui": {"entries": []}})
        merged += catalog.merge({"curseforge": {"entries": [cf("gatherlite", "GatherLite", ["GatherLite"], "3")]},
                                 "wowinterface": {"entries": [wowi("9", "GatherLite", ["GatherLite-6.0.0"])]}})
        self.assertIn(["curseforge:dbm", "wowinterface:8"], names(merged))
        self.assertIn(["curseforge:gatherlite", "wowinterface:9"], names(merged))

    def test_forks_stay_apart(self):
        merged = catalog.merge({
            "curseforge": {"entries": [cf("auctionator", "Auctionator", ["Auctionator"], "4")]},
            "wowinterface": {"entries": [wowi("10", "Auctionator ClassicFix", ["Auctionator"]),
                                         wowi("11", "Styler - Slim", ["Styler"]), wowi("12", "Styler - Xsai", ["Styler"])]}})
        self.assertEqual(len(merged), 4)

    def test_one_listing_per_site_from_heuristics(self):
        merged = catalog.merge({"curseforge": {"entries": [cf("bags", "Bags", ["Bags"], "5")]},
                                "wowinterface": {"entries": [wowi("13", "Bags", ["Bags"]), wowi("14", "Bags", ["Bags"])]}})
        self.assertEqual(len(merged), 2)

    def test_github_listing_links_two_sites(self):
        merged = catalog.merge({"curseforge": {"entries": [cf("keyui", "KeyUI", ["KeyUI"], "6")], "links": [[["curseforge", "6"], ["wowinterface", "15"]]]},
                                "wowinterface": {"entries": [wowi("15", "Key UI Viewer", ["KeyViewer"])]}})
        self.assertEqual(len(merged), 1)

    def test_wowinterface_versions_name_their_game(self):
        ref = catalog.source_ref("wowinterface", dict(wowi("16", "Old Shaman", ["OldShaman"]), gameVersions=["1.13.2", "12.1.0", "1.60.1"]))
        self.assertEqual(ref["flavours"], ["forever_classic", "mainline", "vanilla_classic"])
        ref = catalog.source_ref("wowinterface", dict(wowi("17", "Old", ["Old"]), gameVersions=["1.13.2"]))
        self.assertEqual(ref["flavours"], ["vanilla_classic"])

    def test_downloads_sort_and_totals(self):
        merged = catalog.merge({"curseforge": {"entries": [cf("a", "A", ["A"], "7", downloads=5), cf("b", "B", ["B"], "8", downloads=500)]}})
        self.assertEqual([e["name"] for e in merged], ["B", "A"])


class Refresh(FakeInstall):
    INSTAWOW = {"version": 8, "entries": [
        {"source": "curse", "slug": "tomtom", "id": "1", "name": "TomTom", "url": "https://www.curseforge.com/wow/addons/tomtom",
         "folders": [["TomTom"]], "same_as": [{"source": "wowi", "id": "7"}], "game_flavours": ["vanilla_classic"],
         "download_count": 9, "last_updated": "2026-09-01T00:00:00+00:00"},
        {"source": "github", "slug": "x/y", "id": "99", "name": "Y", "folders": [], "same_as": [{"source": "curse", "id": "1"}, {"source": "wago", "id": "q1w2e3r4"}],
         "game_flavours": [], "download_count": 0, "last_updated": "2026-09-01T00:00:00+00:00"}]}
    FILELIST = [{"UID": "7", "UICATID": "1", "UIVersion": "1", "UIDate": 1, "UIName": "TomTom", "UIAuthorName": "a", "UIDir": ["TomTom"]}]

    def fake(self, url):
        if "instawow" in url:
            return self.INSTAWOW
        if "filelist" in url:
            return self.FILELIST
        if "categorylist" in url:
            return [{"UICATID": "1", "UICATTitle": "Map"}]
        raise AssertionError(url)

    def test_refresh_merges_and_caches(self):
        with patch.object(sources, "fetch_json", side_effect=self.fake) as fetch:
            result = catalog.refresh()
            catalog.refresh()
        self.assertEqual(fetch.call_count, 3)  # Cached the second time.
        self.assertEqual(result["count"], 1)
        self.assertEqual({k: v["count"] for k, v in result["sources"].items()}, {"curseforge": 1, "wowinterface": 1})
        entries = json.loads(Path(result["path"]).read_text())["entries"]
        tomtom = next(e for e in entries if e["name"] == "TomTom")
        # The GitHub listing only links the others; it's never offered as a source.
        self.assertEqual([r["source"] for r in tomtom["sources"]], ["curseforge", "wowinterface", "wago"])
        self.assertEqual(tomtom["sources"][0]["updated"], 1788220800000)

    def test_unreachable_source_keeps_saved_list(self):
        with patch.object(sources, "fetch_json", side_effect=self.fake):
            catalog.refresh()
        def offline_curse(url):
            if "instawow" in url:
                raise sources.Problem("offline")
            return self.fake(url)
        with patch.object(sources, "fetch_json", side_effect=offline_curse):
            result = catalog.refresh(force=True)
        self.assertEqual(result["sources"]["curseforge"]["error"], "offline")
        self.assertEqual(result["sources"]["curseforge"]["count"], 1)
        self.assertEqual(result["count"], 1)

    def test_merge_is_rebuilt_when_rules_change(self):
        with patch.object(sources, "fetch_json", side_effect=self.fake):
            catalog.refresh()
        stale = json.loads(catalog.merged_file().read_text())
        stale["builtBy"]["format"] = 0
        stale["entries"].append({"name": "Leftover"})
        catalog.merged_file().write_text(json.dumps(stale))
        with patch.object(sources, "fetch_json", side_effect=self.fake) as fetch:
            result = catalog.refresh()
        fetch.assert_not_called()  # Rebuilt from the saved source lists.
        self.assertEqual(result["count"], 1)

    def test_nothing_loaded(self):
        with patch.object(sources, "fetch_json", side_effect=sources.Problem("offline")):
            with self.assertRaises(sources.Problem):
                catalog.refresh()


if __name__ == "__main__":
    unittest.main()
