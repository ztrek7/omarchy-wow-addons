# WoW Addons reference

[Back to the README](../README.md) · [Development](../CONTRIBUTING.md)

## Where the addons come from

Addon archives download from CurseForge and WoWInterface. When supplied by the site, the download size or checksum is checked. Arbitrary download links and GitHub addon downloads are not supported. You can also import a `.zip` you downloaded yourself; that file does not receive automatic updates.

WoWInterface supplies a public addon list. For CurseForge, the app uses the public [instawow catalog](https://github.com/layday/instawow-data), plus [CFWidget](https://www.cfwidget.com/) for logos, details, and file lists. This route does not require the user to supply a CurseForge API key.

CFWidget's copy of a project occasionally stops updating. The app checks each file list against the catalog's last-updated date and won't install an old version from a stale copy. If WoWInterface has an up-to-date copy of the same addon, listed for your game, it installs that instead and tells you. If not, it says so, and you can download the addon from its page and add the `.zip`. The app never swaps in an older version just because it's available.

[Wago](https://addons.wago.io) downloads aren't supported by this app. When an addon is also on Wago, its details link to the Wago page.

## Game detection and beta leftovers

WoW Forever's release client lives in `_forever_` and uses Battle.net product
code `wowf`. The manager reads its version from `.build.info`, including during
preinstallation before the game creates an `Interface` folder.

When build records are available, folders with neither a build record nor a WoW
executable are ignored. This keeps addons left by an uninstalled beta from being
mistaken for an installed game. Those files are not deleted or copied into the
release client; install fresh addons for the selected game through Browse.

## Files it keeps

| What | Where |
| --- | --- |
| Settings (game folder, game version, sites) | `~/.config/wow-addons/config.json` |
| Which site each addon was installed from | `~/.local/share/wow-addons/state.json` |
| Addon catalog, refreshed every 6 hours | `~/.cache/wow-addons/` |
| The app itself | `~/.local/share/wow-addons/app` |

The paths above are defaults. `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and
`XDG_CACHE_HOME` override their respective base directories.
