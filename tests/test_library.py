from pathlib import Path
import unittest

from helpers import FakeInstall, library, make_addon


class Listing(FakeInstall):
    def test_groups_modules_under_their_core(self):
        make_addon(self.addons, "DBM-Core")
        make_addon(self.addons, "DBM-Raids", Dependencies="DBM-Core")
        make_addon(self.addons, "Details")
        make_addon(self.addons, "Skada_Plugin", Dependencies="DBM-Core")  # Different prefix: not grouped.
        rows = {r["id"]: r for r in library.list_addons(self.game)}
        self.assertEqual(sorted(rows), ["local:DBM-Core", "local:Details", "local:Skada_Plugin"])
        self.assertEqual([d["name"] for d in rows["local:DBM-Core"]["dirs"]], ["DBM-Core", "DBM-Raids"])
        self.assertFalse(rows["local:Details"]["managed"])

    def test_group_field_folds_modules(self):
        make_addon(self.addons, "Suite")
        make_addon(self.addons, "Suite_Options", Group="Suite")
        self.assertEqual(len(library.list_addons(self.game)), 1)

    def test_hidden_folders_and_files_are_ignored(self):
        (self.addons / ".git").mkdir()
        (self.addons / "readme.txt").write_text("x")
        self.assertEqual(library.list_addons(self.game), [])


class EnableDisable(FakeInstall):
    def test_disable_and_enable_move_folders(self):
        make_addon(self.addons, "Bags")
        message = library.set_enabled(self.game, "local:Bags", False)
        self.assertIn("Disabled Bags", message)
        disabled = self.addons.parent / "AddOns.disabled"
        self.assertTrue((disabled / "Bags").is_dir())
        self.assertFalse((self.addons / "Bags").exists())
        row = library.list_addons(self.game)[0]
        self.assertEqual(row["state"], "disabled")
        library.set_enabled(self.game, "local:Bags", True)
        self.assertTrue((self.addons / "Bags").is_dir())
        self.assertEqual(library.list_addons(self.game)[0]["state"], "enabled")

    def test_refuses_to_overwrite_duplicate(self):
        make_addon(self.addons, "Bags")
        make_addon(self.addons.parent / "AddOns.disabled", "Bags")
        # Enabled copy wins in the listing; disabling would clobber the disabled copy.
        with self.assertRaises(library.Problem):
            library.set_enabled(self.game, "local:Bags", False)
        self.assertTrue((self.addons / "Bags").is_dir())

    def test_unknown_addon(self):
        with self.assertRaises(library.Problem):
            library.set_enabled(self.game, "local:Nope", False)


class RemoveAndInstall(FakeInstall):
    def stage(self, *names, version="1"):
        workspace = library.staging_dir(self.game)
        return {name: make_addon(workspace, name, Version=version) for name in names}

    def test_remove_moves_to_trash(self):
        make_addon(self.addons, "Mail", SavedVariables="MailDB")
        message = library.remove(self.game, "local:Mail")
        self.assertIn("trash", message)
        self.assertIn("saved settings", message)
        self.assertFalse((self.addons / "Mail").exists())
        trash = self.home / ".local/share/Trash"
        self.assertTrue((trash / "files/Mail/Mail.toc").is_file())
        info = (trash / "info/Mail.trashinfo").read_text()
        self.assertIn("Path=", info)
        self.assertIn("AddOns/Mail", info)

    def test_trash_names_do_not_collide(self):
        make_addon(self.addons, "Mail")
        library.remove(self.game, "local:Mail")
        make_addon(self.addons, "Mail")
        library.remove(self.game, "local:Mail")
        self.assertTrue((self.home / ".local/share/Trash/files/Mail.2").is_dir())

    def test_install_records_package_and_replaces_manual_copy(self):
        make_addon(self.addons, "Quest", Version="old")
        record = {"key": "wowi:1", "source": "wowinterface", "sourceId": "1", "name": "Quest Helper", "version": "2"}
        result = library.install(self.game, self.stage("Quest", "Quest_Options", version="2"), record)
        self.assertEqual(result["replaced"], ["Quest"])
        rows = library.list_addons(self.game)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "wowi:1")
        self.assertEqual(rows[0]["name"], "Quest Helper")
        self.assertEqual(len(rows[0]["dirs"]), 2)
        self.assertTrue(rows[0]["managed"])

    def test_update_keeps_disabled_state_and_retires_dropped_folders(self):
        record = {"key": "github:a/b", "source": "github", "sourceId": "a/b", "name": "B", "version": "v1"}
        library.install(self.game, self.stage("B", "B_Old"), record)
        library.set_enabled(self.game, "github:a/b", False)
        result = library.install(self.game, self.stage("B", version="2"), dict(record, version="v2"))
        self.assertEqual(result["retired"], ["B_Old"])
        disabled = self.addons.parent / "AddOns.disabled"
        self.assertTrue((disabled / "B").is_dir())
        self.assertFalse((disabled / "B_Old").exists())
        row = library.list_addons(self.game)[0]
        self.assertEqual((row["version"], row["state"]), ("v2", "disabled"))

    def test_folders_deleted_outside_app_drop_record(self):
        record = {"key": "wowi:9", "source": "wowinterface", "sourceId": "9", "name": "Gone"}
        library.install(self.game, self.stage("Gone"), record)
        library.trash(self.addons / "Gone")
        state = library.load_state()
        self.assertEqual(library.list_addons(self.game, state), [])
        self.assertEqual(library.packages(state, self.game), [])

    def test_staging_is_beside_addons(self):
        path = library.staging_dir(self.game)
        self.assertEqual(Path(path).parent, self.addons.parent)
        self.assertTrue(Path(path).name.startswith(library.STAGING_PREFIX))


if __name__ == "__main__":
    unittest.main()
