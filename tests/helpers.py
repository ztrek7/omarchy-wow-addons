"""Synthetic WoW installs for tests. No real accounts, characters, or paths."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import library  # noqa: E402
import sources  # noqa: E402
import wowdir  # noqa: E402

BUILD_INFO = ("Branch!STRING:0|Active!DEC:1|Build Key!HEX:16|Version!STRING:0|Product!STRING:0\n"
              "us|1|aaaa|1.15.7.61582|wow_classic_era\n"
              "us|1|bbbb|12.1.0.70001|wow\n")


def toc(title, interface="11507", **fields):
    lines = [f"## Interface: {interface}", f"## Title: {title}"]
    lines += [f"## {key}: {value}" for key, value in fields.items()]
    return "\n".join(lines) + "\nmain.lua\n"


def make_addon(base, name, title=None, interface="11507", **fields):
    folder = Path(base) / name
    folder.mkdir(parents=True)
    (folder / f"{name}.toc").write_text(toc(title or name, interface, **fields))
    (folder / "main.lua").write_text("-- test\n")
    return folder


def make_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class FakeInstall(unittest.TestCase):
    """A home directory with a Battle.net-style Wine prefix and a classic era client."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.root = self.home / "Games/battlenet/drive_c/Program Files (x86)/World of Warcraft"
        self.flavor = self.root / "_classic_era_"
        self.addons = self.flavor / "Interface/AddOns"
        self.addons.mkdir(parents=True)
        (self.root / "_retail_/Interface").mkdir(parents=True)
        (self.root / ".build.info").write_text(BUILD_INFO)
        for target, name, value in (
            (wowdir, "HOME", self.home),
            (wowdir, "CONFIG", self.home / ".config/wow-addons/config.json"),
            (library, "STATE", self.home / ".local/share/wow-addons/state.json"),
            (library, "TRASH", self.home / ".local/share/Trash"),
            (sources, "CACHE", self.home / ".cache/wow-addons"),
        ):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # Tests never touch the network; anything not mocked fails loudly.
        offline = patch("urllib.request.urlopen", side_effect=AssertionError("network access in a test"))
        offline.start()
        self.addCleanup(offline.stop)
        self.game = wowdir.resolve()["flavor"]
