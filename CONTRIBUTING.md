# Contributing

Bug reports, ideas, and pull requests are all welcome. Everything is reviewed by hand, so it may take a few days to hear back.

## Reporting a problem

Open an issue and pick **Something isn't working**. The form asks for the details the app can copy for you (Settings → Copy details for a report). Please leave out anything personal, like account or character names.

If you think you've found a security problem, don't open an issue. See [SECURITY.md](SECURITY.md).

## Pull requests

Small, focused changes are the easiest to review. For anything bigger, open an issue first so we can agree on the approach before you spend time on it.

A few things this project sticks to:

- **Only CurseForge and WoWInterface.** The app downloads addons from those two sites and nowhere else. Changes that add other download sources (GitHub repositories, links to arbitrary files, sites that need API keys) won't be merged.
- **No new dependencies.** The app uses Quickshell, Qt Quick, and the Python standard library, all of which come with Omarchy.
- **Tests don't use the network.** They use example data, and any real network call makes them fail.
- **Write like the code around you.** Short functions, plain comments that explain why, and plain wording in anything a user reads.

## Running it from a checkout

```bash
./run                                                  # the app, without installing it
python3 -m unittest discover -s tests                  # Python tests
WOW_ADDONS_DEMO=1 quickshell -n -p "$PWD/Smoke.qml"    # UI test with example data
```

`WOW_ADDONS_DEMO=1 ./run` opens the app with made-up example data and changes turned off, which is handy for trying the interface without touching your game. Screenshots for the README should come from the real app.

The `Commons` symlink exposes Omarchy's system theme module as `qs.Commons`,
including its internal imports. Keep the symlink when copying a checkout; the
installer creates it in the installed app too. Do not edit files through it:
they belong to the system's Omarchy package.

`backend.py` is what the window calls for anything that touches files or the network. `wowdir.py` finds game installs and reads `.toc` files, `library.py` changes the AddOns folder, `sources.py` talks to CurseForge and WoWInterface, and `catalog.py` builds the Browse list.

## Check installer behavior without replacing your app

Read [scripts/install.py](scripts/install.py) before changing it. It stages a
copy of the listed runtime files, replaces the installed app directory, and
writes the launcher entry and icon under `XDG_DATA_HOME`. It does not update
the original checkout or touch game addons, settings, or state.

```bash
python3 -m unittest discover -s tests -p 'test_installer.py' -v
```

This test redirects `XDG_DATA_HOME` into a temporary directory. It installs
twice to check replacement, verifies the copied files and launcher, then
uninstalls and checks that the test state file survives. It does not replace
your installed app or launch the UI. It requires Quickshell and Omarchy's theme
module; without the theme module it is skipped, which is not a passing install test.

The full Python suite uses temporary game folders and blocks real network
calls. The demo UI commands above are separate visual checks; passing Python
tests alone does not establish visual behavior or live addon downloads.
