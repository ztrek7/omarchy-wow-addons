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

`backend.py` is what the window calls for anything that touches files or the network. `wowdir.py` finds game installs and reads `.toc` files, `library.py` changes the AddOns folder, `sources.py` talks to CurseForge and WoWInterface, and `catalog.py` builds the Browse list.
