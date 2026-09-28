import hashlib
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


class Text(FakeInstall):
    def test_compacts_wowinterface(self):
        entry = sources.compact_wowinterface(FILELIST, CATEGORIES)
        self.assertEqual(len(entry), 1)
        entry = entry[0]
        self.assertEqual(entry["name"], "Bar & Co")
        self.assertEqual(entry["category"], "Action Bar Mods")
        self.assertEqual(entry["gameVersions"], ["12.1.0", "1.15.7"])
        self.assertEqual((entry["downloads"], entry["monthly"], entry["favorites"]), (500, 5, 7))

    def test_html_and_markdown(self):
        self.assertEqual(sources.html_text("<p>Hi &amp; bye</p><ul><li>One</li><li>Two</li></ul>"), "Hi & bye\n  •  One\n  •  Two")

    def test_bbcode(self):
        text = sources.bbcode_text('[SIZE="4"][B]Hi[/B][/SIZE]\r\n[LIST][*]One[*]Two[/LIST] [url="https://x"]link[/url] [img]https://i[/img] &amp;')
        self.assertEqual(text, "Hi\n\n  •  One\n  •  Two link  &")

    def test_only_https(self):
        with self.assertRaises(sources.Problem):
            sources.fetch("http://example.invalid/x.zip")

    def test_only_trusted_hosts(self):
        self.assertTrue(sources.trusted("https://mediafilez.forgecdn.net/files/1/2/a.zip", sources.DOWNLOAD_HOSTS))
        self.assertTrue(sources.trusted("https://cdn.wowinterface.com/downloads/getfile.php?id=1", sources.DOWNLOAD_HOSTS))
        for url in ("https://evilforgecdn.net/a.zip", "https://forgecdn.net.example/a.zip", "http://cdn.wowinterface.com/a.zip",
                    "https://api.cfwidget.com/wow/addons/x"):
            self.assertFalse(sources.trusted(url, sources.DOWNLOAD_HOSTS), url)
        # Refused before any request is made; the test install fails on network access.
        with self.assertRaises(sources.Problem):
            sources.download("https://example.invalid/a.zip", self.home / "a.zip")
        with self.assertRaises(sources.Problem):
            sources.fetch("https://edge.forgecdn.net/files/1/2/a.zip")  # A download host isn't an API host.

    def test_redirects_must_stay_on_trusted_hosts(self):
        import urllib.request
        handler = sources.TrustedRedirects(sources.DOWNLOAD_HOSTS)
        request = urllib.request.Request("https://edge.forgecdn.net/files/1/2/a.zip")
        followed = handler.redirect_request(request, None, 302, "Found", {}, "https://mediafilez.forgecdn.net/files/1/2/a.zip")
        self.assertEqual(followed.full_url, "https://mediafilez.forgecdn.net/files/1/2/a.zip")

        class Body:
            closed = False
            def close(self):
                self.closed = True
        body = Body()
        with self.assertRaises(sources.Problem) as caught:
            handler.redirect_request(request, body, 302, "Found", {}, "https://example.invalid/a.zip")
        self.assertIn("example.invalid", str(caught.exception))
        self.assertTrue(body.closed)


class CurseForge(FakeInstall):
    def test_wowinterface_page(self):
        self.assertEqual(sources.wowinterface_page("https://www.wowinterface.com/downloads/info7032-TomTom.html"), "7032")
        self.assertIsNone(sources.wowinterface_page("https://evil.example/downloads/info7032"))
        self.assertEqual(sources.wowinterface_page("wowinterface.com/downloads/info7032-TomTom.html"), "7032")

    def test_project_parsing(self):
        self.assertEqual(sources.curseforge_project("https://www.curseforge.com/wow/addons/Auctionator/"), "auctionator")
        self.assertIsNone(sources.curseforge_project("https://www.curseforge.com/minecraft/mc-mods/x"))
        # Links are only parsed for their ID, so http:// or no scheme is fine; other sites aren't.
        self.assertEqual(sources.curseforge_project("curseforge.com/wow/addons/x"), "x")
        self.assertEqual(sources.curseforge_project("http://www.curseforge.com/wow/addons/x/files"), "x")
        self.assertIsNone(sources.curseforge_project("https://evilcurseforge.com/wow/addons/x"))
        self.assertIsNone(sources.curseforge_project("https://curseforge.com.example/wow/addons/x"))

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
        self.assertEqual(sources.choose_curseforge_file(files, dict(self.game, version="5.5.4", major=5, flavour="mists_classic")), None)
        # A later Forever patch still gets a Forever file before any Classic Era one.
        files.append({"id": 5, "name": "A-5.zip", "type": "release", "versions": ["1.15.9"], "uploaded_at": "2026-05-01"})
        later_forever = dict(self.game, version="1.60.2", major=1, flavour="forever_classic")
        self.assertEqual(sources.choose_curseforge_file(files, later_forever)["id"], 1)

    def test_other_games_file_only_when_asked(self):
        # Classic Era and Forever share major version 1; Wrath and Titan Reforged share 3.
        files = [{"id": 1, "name": "A-forever.zip", "type": "release", "versions": ["1.60.1"], "uploaded_at": "2026-01-01"},
                 {"id": 2, "name": "A-titan.zip", "type": "release", "versions": ["3.80.2"], "uploaded_at": "2026-01-01"}]
        wrath = dict(self.game, version="3.4.5", major=3, flavour="wrath_classic")
        self.assertIsNone(sources.choose_curseforge_file(files, self.game))
        self.assertIsNone(sources.choose_curseforge_file(files, wrath))
        self.assertEqual(sources.choose_curseforge_file(files, self.game, other_games=True)["id"], 1)
        self.assertEqual(sources.choose_curseforge_file(files, wrath, other_games=True)["id"], 2)

    def test_release_download_path(self):
        data = {"title": "Auctionator", "urls": {"curseforge": "https://www.curseforge.com/wow/addons/auctionator"},
                "files": [{"id": 8939005, "name": "Auctionator 339.zip", "display": "339", "type": "release", "versions": ["1.15.7"],
                           "filesize": 10, "uploaded_at": "2026-09-21"}]}
        with patch.object(sources, "fetch_json", return_value=data) as lookup:
            release = sources.curseforge_release("6124", self.game)
        self.assertEqual(lookup.call_args[0][0], "https://api.cfwidget.com/6124")
        self.assertEqual(release["download"], "https://edge.forgecdn.net/files/8939/5/Auctionator%20339.zip")
        self.assertEqual((release["project"], release["version"], release["size"]), ("auctionator", "339", 10))

    def test_stale_mirror_is_refused(self):
        data = {"title": "BigWigs", "urls": {}, "files": [{"id": 1, "name": "B.zip", "display": "v38", "type": "release",
                                                           "versions": ["1.14.3"], "uploaded_at": "2022-05-12T12:00:00Z"}]}
        with patch.object(sources, "fetch_json", return_value=data):
            self.assertEqual(sources.curseforge_release("2382", self.game)["version"], "v38")  # No catalog date to compare.
            with self.assertRaises(sources.Problem) as caught:
                sources.curseforge_release("2382", self.game, listed_updated=sources.iso_ms("2026-09-25T00:00:00Z"))
        self.assertIn("May 12, 2022", str(caught.exception))

    def test_project_still_loading(self):
        with patch.object(sources, "fetch_json", return_value={"error": "in_queue"}):
            with self.assertRaises(sources.Problem):
                sources.curseforge_release("auctionator", self.game)

    def test_size_check(self):
        with patch.object(sources, "fetch", return_value=b"12345"):
            sources.download("https://example.invalid/a.zip", self.home / "ok.zip", size=5)
            with self.assertRaises(sources.Problem):
                sources.download("https://example.invalid/a.zip", self.home / "bad.zip", size=6)

    def test_compare_versions(self):
        for newer, older in (("v12.0.1", "6.2.5"), ("2.0", "1.0"), ("2.0", "2.0-rc1"), ("2.0-rc1", "2.0-beta3"), ("2.0-beta10", "2.0-beta2"),
                             ("2.0b3", "2.0a5"), ("1.2b", "1.2a"), ("1.15.7-r45", "1.15.7-r44"), ("2.1-beta", "2.0"), ("2.0", "1.9-beta")):
            self.assertEqual(sources.compare_versions(newer, older), 1, (newer, older))
            self.assertEqual(sources.compare_versions(older, newer), -1, (older, newer))
        self.assertEqual(sources.compare_versions("2.0", "v2.0.0-release"), 0)
        # A guess could offer an older file, so these can't be ordered: 1.2a is a fix after 1.2, not an alpha.
        for a, b in (("1.2a", "1.2"), ("1.15.7-r45", "1.15.7"), ("339-1-g23f0261", "339"), ("@project-version@", "1.0"), ("1.0", "")):
            self.assertIsNone(sources.compare_versions(a, b), (a, b))

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

    def test_source_archive_with_newer_game_tocs(self):
        for suffix in ("Camelot", "Standard", "Mainline", "Wrath", "Classic"):
            placed = self.extract({"owner-Bar-abc123/Bar.toc": toc("Bar"), f"owner-Bar-abc123/Bar_{suffix}.toc": "",
                                   "owner-Bar-abc123/core.lua": ""})
            self.assertEqual(list(placed), ["Bar"], suffix)
            import shutil
            shutil.rmtree(self.home / "out")

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
