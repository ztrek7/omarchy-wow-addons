import hashlib
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from helpers import FakeInstall, make_zip, sources, toc

FILELIST = [
    {"UID": "10", "UICATID": "19", "UIVersion": "1.2", "UIDate": 1700000000000, "UIName": "Bar &amp; Co",
     "UIAuthorName": "someone", "UIFileInfoURL": "https://www.wowinterface.com/downloads/info10-Bar.html",
     "UIDownloadTotal": "500", "UIDownloadMonthly": "5", "UIFavoriteTotal": "7",
     "UICompatibility": [{"version": "1.15.7", "name": "Classic"}, {"version": "12.1.0", "name": "Retail"}],
     "UIDir": ["Bar"], "UIIMG_Thumbs": ["https://cdn.example/t.jpg"], "UIIMGs": None, "UISiblings": None},
    {"UID": "bad"},
]
CATEGORIES = [{"UICATID": "19", "UICATTitle": "Action Bar Mods"}]


class Catalog(FakeInstall):
    def test_compacts_catalog(self):
        entry = sources.compact_catalog(FILELIST, CATEGORIES)
        self.assertEqual(len(entry), 1)
        entry = entry[0]
        self.assertEqual(entry["name"], "Bar & Co")
        self.assertEqual(entry["category"], "Action Bar Mods")
        self.assertEqual(entry["gameVersions"], ["12.1.0", "1.15.7"])
        self.assertEqual((entry["downloads"], entry["monthly"], entry["favorites"]), (500, 5, 7))

    def test_refresh_uses_fresh_cache_and_falls_back_to_stale(self):
        calls = []

        def fake(url):
            calls.append(url)
            return FILELIST if "filelist" in url else CATEGORIES
        with patch.object(sources, "fetch_json", side_effect=fake):
            first = sources.refresh_catalog()
            again = sources.refresh_catalog()
        self.assertEqual(first["count"], 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(again["count"], 1)
        data = json.loads(Path(first["path"]).read_text())
        data["fetchedAt"] = time.time() - sources.CATALOG_TTL - 1
        Path(first["path"]).write_text(json.dumps(data))
        with patch.object(sources, "fetch_json", side_effect=sources.Problem("offline")):
            stale = sources.refresh_catalog()
        self.assertIn("saved catalog", stale["message"])

    def test_bbcode(self):
        text = sources.bbcode_text('[SIZE="4"][B]Hi[/B][/SIZE]\r\n[LIST][*]One[*]Two[/LIST] [url="https://x"]link[/url] [img]https://i[/img] &amp;')
        self.assertEqual(text, "Hi\n\n  •  One\n  •  Two link  &")

    def test_only_https(self):
        with self.assertRaises(sources.Problem):
            sources.fetch("http://example.invalid/x.zip")


class GitHub(FakeInstall):
    def test_repo_parsing(self):
        self.assertEqual(sources.github_repo("https://github.com/Owner/Addon.git"), "Owner/Addon")
        self.assertEqual(sources.github_repo("owner/addon"), "owner/addon")
        self.assertIsNone(sources.github_repo("https://github.com/o/r/releases/download/v1/x.zip"))
        self.assertIsNone(sources.github_repo("not a repo"))

    def release(self, *names):
        return {"assets": [{"name": n, "browser_download_url": f"https://example.invalid/{n}"} for n in names]}

    def test_release_json_picks_matching_interface(self):
        release = self.release("A-v1.zip", "A-v1-classic.zip", "A-v1-nolib.zip", "release.json")
        manifest = {"releases": [
            {"filename": "A-v1.zip", "nolib": False, "metadata": [{"flavor": "mainline", "interface": 120100}]},
            {"filename": "A-v1-nolib.zip", "nolib": True, "metadata": [{"flavor": "vanilla", "interface": 11507}]},
            {"filename": "A-v1-classic.zip", "nolib": False, "metadata": [{"flavor": "vanilla", "interface": 11507}]}]}
        chosen = sources.choose_asset(release, self.game, lambda url: manifest)
        self.assertEqual(chosen["name"], "A-v1-classic.zip")

    def test_file_names_without_manifest(self):
        release = self.release("A-v1.zip", "A-v1-classic.zip", "A-v1-bcc.zip")
        self.assertEqual(sources.choose_asset(release, self.game)["name"], "A-v1-classic.zip")
        retail = dict(self.game, interface=120100, major=12)
        self.assertEqual(sources.choose_asset(release, retail)["name"], "A-v1.zip")
        self.assertIsNone(sources.choose_asset(self.release("A-v1-bcc.zip"), self.game))
        self.assertIsNone(sources.choose_asset(self.release("notes.txt"), self.game))


class CurseForge(FakeInstall):
    def test_project_parsing(self):
        self.assertEqual(sources.curseforge_project("https://www.curseforge.com/wow/addons/Auctionator/"), "auctionator")
        self.assertIsNone(sources.curseforge_project("https://www.curseforge.com/minecraft/mc-mods/x"))
        self.assertIsNone(sources.curseforge_project("http://www.curseforge.com/wow/addons/x"))

    def test_picks_newest_release_for_client_version(self):
        files = [
            {"id": 1, "name": "A-1.zip", "type": "release", "versions": ["1.60.1"], "uploaded_at": "2026-01-01"},
            {"id": 2, "name": "A-2.zip", "type": "alpha", "versions": ["1.60.1", "1.15.7"], "uploaded_at": "2026-03-01"},
            {"id": 3, "name": "A-3.zip", "type": "release", "versions": ["1.15.7"], "uploaded_at": "2026-02-01"},
            {"id": 4, "name": "A-4.zip", "type": "release", "versions": ["12.1.0"], "uploaded_at": "2026-04-01"},
        ]
        forever = dict(self.game, version="1.60.1", major=1)
        self.assertEqual(sources.choose_curseforge_file(files, forever)["id"], 1)
        self.assertEqual(sources.choose_curseforge_file(files, self.game)["id"], 3)
        self.assertEqual(sources.choose_curseforge_file(files, dict(self.game, version="5.5.4", major=5)), None)

    def test_release_download_path(self):
        data = {"title": "Auctionator", "urls": {"curseforge": "https://www.curseforge.com/wow/addons/auctionator"},
                "files": [{"id": 8939005, "name": "Auctionator 339.zip", "display": "339", "type": "release", "versions": ["1.15.7"],
                           "filesize": 10, "uploaded_at": "2026-09-21"}]}
        with patch.object(sources, "fetch_json", return_value=data) as lookup:
            release = sources.curseforge_release("6124", self.game)
        self.assertEqual(lookup.call_args[0][0], "https://api.cfwidget.com/6124")
        self.assertEqual(release["download"], "https://edge.forgecdn.net/files/8939/5/Auctionator%20339.zip")
        self.assertEqual((release["project"], release["version"], release["size"]), ("auctionator", "339", 10))

    def test_project_still_loading(self):
        with patch.object(sources, "fetch_json", return_value={"error": "in_queue"}):
            with self.assertRaises(sources.Problem):
                sources.curseforge_release("auctionator", self.game)

    def test_size_check(self):
        with patch.object(sources, "fetch", return_value=b"12345"):
            sources.download("https://example.invalid/a.zip", self.home / "ok.zip", size=5)
            with self.assertRaises(sources.Problem):
                sources.download("https://example.invalid/a.zip", self.home / "bad.zip", size=6)

    def test_same_version(self):
        self.assertTrue(sources.same_version("v1.2", "1.2 "))
        self.assertFalse(sources.same_version("", ""))
        self.assertFalse(sources.same_version("339", "340"))


class Archives(FakeInstall):
    def extract(self, files):
        archive = self.home / "a.zip"
        archive.write_bytes(make_zip(files))
        out = self.home / "out"
        out.mkdir()
        return sources.extract_addons(archive, out)

    def test_packaged_archive(self):
        placed = self.extract({"Bar/Bar.toc": toc("Bar"), "Bar/Libs/LibStub/LibStub.toc": "", "Bar/x.lua": "",
                               "Bar_Config/Bar_Config.toc": toc("Cfg"), "readme.txt": "ignored"})
        self.assertEqual(sorted(placed), ["Bar", "Bar_Config"])
        self.assertTrue((placed["Bar"] / "Libs/LibStub/LibStub.toc").is_file())
        self.assertFalse((self.home / "out/readme.txt").exists())

    def test_nested_repo_folder(self):
        placed = self.extract({"Bar-main/Bar/Bar.toc": toc("Bar"), "Bar-main/Bar/x.lua": ""})
        self.assertEqual(list(placed), ["Bar"])

    def test_github_source_archive_is_named_after_toc(self):
        placed = self.extract({"owner-Bar-abc123/Bar.toc": toc("Bar"), "owner-Bar-abc123/Bar_Vanilla.toc": "",
                               "owner-Bar-abc123/core.lua": ""})
        self.assertEqual(list(placed), ["Bar"])
        self.assertTrue((placed["Bar"] / "core.lua").is_file())

    def test_rejects_traversal(self):
        with self.assertRaises(sources.Problem):
            self.extract({"Bar/Bar.toc": toc("Bar"), "../evil.lua": ""})
        self.assertFalse((self.home / "evil.lua").exists())

    def test_rejects_non_addon(self):
        with self.assertRaises(sources.Problem):
            self.extract({"docs/readme.md": "x"})

    def test_checksum(self):
        data = make_zip({"Bar/Bar.toc": toc("Bar")})
        with patch.object(sources, "fetch", return_value=data):
            sources.download("https://example.invalid/a.zip", self.home / "ok.zip", hashlib.md5(data).hexdigest())
            with self.assertRaises(sources.Problem):
                sources.download("https://example.invalid/a.zip", self.home / "bad.zip", "0" * 32)


if __name__ == "__main__":
    unittest.main()
