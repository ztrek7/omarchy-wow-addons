#!/usr/bin/env python3
"""Install this checkout as an Omarchy app launcher entry. Never needs sudo.

Copies the app to ~/.local/share/wow-addons/app (replacing an older copy there),
adds "WoW Addons" to the application launcher, and installs its icon.
Pass --uninstall to remove all three. Your addons, settings, and state are untouched.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

source = Path(__file__).resolve().parents[1]
data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
target = data / "wow-addons" / "app"
desktop = data / "applications" / "wow-addons.desktop"
icon = data / "icons/hicolor/scalable/apps/wow-addons.svg"
RUNTIME = ["App.qml", "InstalledView.qml", "BrowseView.qml", "SettingsView.qml", "backend.py", "catalog.py", "library.py",
           "sources.py", "wowdir.py", "run", "LICENSE", "README.md"]


def refresh_launcher():
    for command in (["update-desktop-database", str(desktop.parent)], ["gtk-update-icon-cache", "-q", "-t", str(data / "icons/hicolor")]):
        if shutil.which(command[0]):
            subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def uninstall():
    shutil.rmtree(target, ignore_errors=True)
    for path in (desktop, icon):
        path.unlink(missing_ok=True)
    refresh_launcher()
    print("Removed the WoW Addons app and launcher. Your addons and settings were not touched.")


def install():
    for command in ("quickshell", "python3"):
        if not shutil.which(command):
            raise SystemExit(f"Required command not found: {command}")
    if not Path("/usr/share/omarchy/shell/Commons").is_dir():
        raise SystemExit("Omarchy's shell theme module was not found at /usr/share/omarchy/shell/Commons.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".app-", dir=target.parent) as stage_dir:
        stage = Path(stage_dir) / "app"
        stage.mkdir()
        for name in RUNTIME:
            shutil.copy2(source / name, stage / name)
        shutil.copytree(source / "ui", stage / "ui", ignore=shutil.ignore_patterns("__pycache__"))
        if target.exists():
            shutil.rmtree(target)
        stage.rename(target)
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "assets/wow-addons.svg", icon)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    # Freedesktop Exec quoting is distinct from shell quoting.
    executable = str(target / "run").replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    desktop.write_text("[Desktop Entry]\nType=Application\nName=WoW Addons\n"
                       "Comment=Install, browse, and manage World of Warcraft addons\n"
                       f'Exec="{executable}"\nIcon=wow-addons\nTerminal=false\n'
                       "Categories=Game;Utility;\nKeywords=warcraft;addons;wowinterface;\n")
    refresh_launcher()
    print(f"Installed WoW Addons to {target}\nOpen it from the app launcher (Super + Space).")


if __name__ == "__main__":
    uninstall() if "--uninstall" in sys.argv[1:] else install()
