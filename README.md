# WoW Addons for Omarchy

A native Omarchy app for World of Warcraft addons on Linux. Browse, install, disable, and remove addons without the CurseForge app. It follows your active Omarchy theme and uses only Quickshell, Qt Quick, and the Python standard library.

![WoW Addons showing installed addons with filters and a details panel](assets/preview.png)

*Preview rendered from built-in example data.*

- **Installed**: every addon in your AddOns folder, including ones you copied in by hand. Filter by status (enabled, disabled, update available, out of date) and source, then sort by name, install date, what needs attention, or folder count. Modules such as `DBM-Raids` are grouped under their core addon.
- **Browse**: the WoWInterface catalog of about 8,000 addons. Search by name, author, or folder, and filter by category, game version, and last update. You can also hide what's installed. Sort by all-time downloads, downloads this month, favorites, recent updates, or name. Details show screenshots, the description, and the changelog.
- **Add addon**: install the packaged release from a GitHub repository (`owner/repo`), an `https://` link to a .zip, or a .zip you downloaded. Recent downloads are offered as one-click picks.
- **Updates**: check addons installed from WoWInterface or GitHub, then update one or all.
- **Disable and enable** in one click; **remove** to the trash.
- Finds Battle.net installs in Wine and Proton prefixes, and every game version inside them (`_retail_`, `_classic_`, `_classic_era_`, betas, and PTRs).

## Install

Requires Omarchy (for its Quickshell theme module), `quickshell`, and Python 3.11 or later. No pip or npm packages.

```bash
git clone https://github.com/ztrek7/omarchy-wow-addons
cd omarchy-wow-addons
python3 scripts/install.py
```

Then open **WoW Addons** from the app launcher (`Super` + `Space`). To try it without installing, run `./run` from the checkout. To remove the app and its launcher, run `python3 scripts/install.py --uninstall`. That leaves your addons alone.

Shortcuts: `Ctrl+F` search, `Ctrl+N` add an addon, `Ctrl+R` refresh, `Ctrl+1`/`Ctrl+2` switch between Installed and Browse, `Escape` close.

## How it changes your game folder

- **Disable** moves an addon's folders from `Interface/AddOns` to `Interface/AddOns.disabled`, so it's off for every character. The game rewrites `WTF/…/AddOns.txt` on logout, which would undo edits to that file. Moving folders survives that. **Enable** moves them back. The in-game AddOns list still handles per-character choices among enabled addons.
- **Remove** moves the folders to the desktop trash (`~/.local/share/Trash`), so you can restore them. Anything an install replaces goes to the trash too. SavedVariables in `WTF` are never touched.
- **Install** unpacks only real addon folders, meaning folders holding a `.toc` named after them. It refuses archives with absolute paths, `..`, or links. WoWInterface downloads are checked against their published MD5.
- The game reads addons at startup. When a WoW client is running, the app reminds you to `/reload` or restart.

An addon counts as **out of date** when its `## Interface` list doesn't include your client's interface number, for example 16001 for client 1.60.1. The app reads the flavor-specific `.toc` (`_Vanilla`, `_Classic`, `_Mainline`, and so on) that your client would load.

## Where things live

| What | Where |
| --- | --- |
| Chosen install folder and game version | `~/.config/wow-addons/config.json` |
| Which addons came from which source | `~/.local/share/wow-addons/state.json` |
| WoWInterface catalog cache (6 hours) | `~/.cache/wow-addons/wowinterface.json` |
| The installed app | `~/.local/share/wow-addons/app` |

Game folders are detected under `~/Games/*/drive_c`, `~/.wine`, and Steam's Proton prefixes. Pick another folder in **Settings**.

## Sources and privacy

The app only contacts these hosts: `api.mmoui.com` and `cdn.wowinterface.com` (the public WoWInterface catalog and downloads), and `api.github.com`/`github.com` when you install from GitHub. It uses no accounts, API keys, analytics, or root. CurseForge and Wago aren't browsable because their APIs require keys. You can still install their downloads with **Add addon → .zip**. For many GitHub update checks, set `GITHUB_TOKEN` to raise GitHub's anonymous limit of 60 requests an hour.

## Development

```bash
python3 -m unittest discover -s tests                        # backend tests, synthetic data only
WOW_ADDONS_DEMO=1 quickshell -n -p "$PWD/Smoke.qml"          # UI filters and sorting on example data
quickshell -n -p "$PWD/Verify.qml"                           # read-only check against your install
```

`backend.py` is the JSON bridge the window calls. `wowdir.py` finds installs and reads `.toc` files, `library.py` changes the AddOns folder, and `sources.py` talks to WoWInterface and GitHub and unpacks archives.

Not affiliated with Blizzard Entertainment or WoWInterface. World of Warcraft is a trademark of Blizzard Entertainment, Inc.
