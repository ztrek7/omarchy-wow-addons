"""Check the manager's published releases and install one into the launcher copy."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from library import Problem
import sources

REPO = "ztrek7/omarchy-wow-addons"
GIT_URL = f"https://github.com/{REPO}.git"
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"


def installed_copy():
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return Path(__file__).resolve().parent == (data / "wow-addons/app").resolve()


def check():
    try:
        release = json.loads(sources.fetch(RELEASE_API, limit=1024**2, hosts=("api.github.com",)))
    except ValueError:
        raise Problem("GitHub returned an unreadable release.")
    tag = release.get("tag_name", "") if isinstance(release, dict) else ""
    if not isinstance(tag, str) or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise Problem("GitHub did not list a stable WoW Addons version.")
    version = tag[1:]
    available = tuple(map(int, version.split("."))) > tuple(map(int, sources.VERSION.split(".")))
    return {"latest": version, "available": available, "installedCopy": installed_copy()}


def apply(version):
    if not installed_copy():
        raise Problem("Open WoW Addons from the app launcher to update the installed copy.")
    result = check()
    if not result["available"] or result["latest"] != version:
        raise Problem("The available release changed. Check for a manager update again.")
    with tempfile.TemporaryDirectory(prefix="wow-addons-update-") as folder:
        source = Path(folder)
        git = [["git", "init", "--quiet"],
               ["git", "fetch", "--quiet", "--depth", "1", GIT_URL, f"refs/tags/v{version}"],
               ["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"]]
        try:
            for command in git:
                subprocess.run(command, cwd=source, check=True, capture_output=True, timeout=120,
                               env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
            subprocess.run([sys.executable, str(source / "scripts/install.py")], check=True, capture_output=True, timeout=120)
        except FileNotFoundError:
            raise Problem("Git is required to install a manager update.")
        except subprocess.TimeoutExpired:
            raise Problem("Updating WoW Addons timed out. Check your connection and try again.")
        except subprocess.CalledProcessError as error:
            detail = error.stderr.decode(errors="replace").strip().splitlines()
            raise Problem("Could not install the manager update. " + (detail[-1] if detail else "Try again."))
    return {"message": f"WoW Addons {version} is installed. Reopen it from the app launcher."}
