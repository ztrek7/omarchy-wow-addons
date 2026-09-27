import os
import unittest

from helpers import FakeInstall, make_addon, wowdir


class Detection(FakeInstall):
    def test_finds_install_and_prefers_flavor_with_addons(self):
        setup = wowdir.resolve(home=self.home)
        self.assertEqual(setup["root"], str(self.root))
        self.assertEqual([f["key"] for f in setup["flavors"]], ["_classic_era_", "_retail_"])
        self.assertEqual(setup["flavor"]["key"], "_classic_era_")
        self.assertEqual(setup["flavor"]["version"], "1.15.7")
        self.assertEqual(setup["flavor"]["interface"], 11507)
        self.assertEqual(setup["flavor"]["name"], "Classic Era")

    def test_configured_flavor_wins(self):
        setup = wowdir.resolve({"flavor": "_retail_"}, home=self.home)
        self.assertEqual(setup["flavor"]["interface"], 120100)

    def test_proton_self_link_is_not_listed_twice(self):
        os.symlink(".", self.home / "Games/battlenet/pfx")
        self.assertEqual(len(wowdir.candidate_roots(self.home)), 1)

    def test_interface_number(self):
        self.assertEqual(wowdir.interface_number("1.60.1.70009"), 16001)
        self.assertEqual(wowdir.interface_number("12.1.0"), 120100)
        self.assertIsNone(wowdir.interface_number("beta"))

    def test_product_dirs(self):
        self.assertEqual(wowdir.product_dir("wow_classic_beta"), "_classic_beta_")
        self.assertEqual(wowdir.product_dir("wow"), "_retail_")


class Toc(FakeInstall):
    def test_reads_metadata_and_strips_color_codes(self):
        folder = make_addon(self.addons, "Coords", "|cff00ff00Coords|r |TInterface\\Icon:0|t", Notes="Shows |cffffffffxy|r", Version="2.1",
                            SavedVariables="CoordsDB, CoordsCache")
        info = wowdir.read_addon(folder, self.game)
        self.assertEqual(info["title"], "Coords")
        self.assertEqual(info["notes"], "Shows xy")
        self.assertEqual(info["savedVariables"], ["CoordsDB", "CoordsCache"])
        self.assertFalse(info["outOfDate"])

    def test_multi_interface_list(self):
        folder = make_addon(self.addons, "Multi", interface="120100, 11507, 50504")
        self.assertFalse(wowdir.read_addon(folder, self.game)["outOfDate"])
        old = make_addon(self.addons, "Old", interface="11302")
        self.assertTrue(wowdir.read_addon(old, self.game)["outOfDate"])

    def test_prefers_flavor_toc(self):
        folder = make_addon(self.addons, "Split", interface="120100")
        (folder / "Split_Vanilla.toc").write_text("## Interface: 11507\n## Title: Split Classic\n")
        info = wowdir.read_addon(folder, self.game)
        self.assertEqual(info["title"], "Split Classic")
        self.assertFalse(info["outOfDate"])

    def test_other_flavor_only_is_not_loadable(self):
        folder = self.addons / "RetailOnly"
        folder.mkdir()
        (folder / "RetailOnly_Mainline.toc").write_text("## Interface: 120100\n")
        self.assertFalse(wowdir.read_addon(folder, self.game)["loadable"])

    def test_bom_and_missing_toc(self):
        folder = self.addons / "Bom"
        folder.mkdir()
        (folder / "Bom.toc").write_bytes("﻿## Title: Bom\n".encode("utf-8"))
        self.assertEqual(wowdir.read_addon(folder, self.game)["title"], "Bom")
        empty = self.addons / "Empty"
        empty.mkdir()
        self.assertFalse(wowdir.read_addon(empty, self.game)["hasToc"])


if __name__ == "__main__":
    unittest.main()
