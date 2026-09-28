#!/usr/bin/env python3
"""JSON bridge for the QML window: one request in argv, one JSON response on stdout.

Standard library only. Never needs root.
"""
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog  # noqa: E402
import library  # noqa: E402
from library import Problem  # noqa: E402
import sources  # noqa: E402
import wowdir  # noqa: E402


def current_game():
    setup = wowdir.resolve()
    if not setup["flavor"]:
        raise Problem("No World of Warcraft install was found. Choose its folder in Settings.")
    return setup, setup["flavor"]


def overview(request):
    setup = wowdir.resolve()
    game = setup["flavor"]
    state = library.load_state()
    addons = library.list_addons(game, state) if game else []
    if game:
        library.save_state(state)  # Drops records for folders deleted outside the app.
    enabled = wowdir.load_config().get("sources", {})
    setup["sources"] = {name: enabled.get(name, True) is not False for name in catalog.SOURCES}
    setup["gameNames"] = wowdir.GAME_NAMES
    setup["appVersion"] = sources.VERSION
    return {"setup": setup, "addons": addons, "gameRunning": wowdir.game_running(), "downloads": recent_zips()}


def recent_zips(limit=5, days=14):
    """Recently downloaded archives, offered as quick picks in the Add dialog."""
    cutoff = time.time() - days * 86400
    try:
        found = [(p.stat().st_mtime, p) for p in (wowdir.HOME / "Downloads").glob("*.zip") if p.is_file()]
    except OSError:
        return []
    return [{"name": p.name, "path": str(p)} for mtime, p in sorted(found, reverse=True)[:limit] if mtime >= cutoff]


def configure(request):
    config = wowdir.load_config()
    root = (request.get("root") or "").strip()
    if root:
        path = Path(root).expanduser()
        if not wowdir.flavors(path):
            raise Problem("That folder doesn't look like a World of Warcraft install. Pick the folder containing _retail_ or _classic_ folders.")
        config["root"] = str(path)
    elif "root" in request:
        config.pop("root", None)
    if request.get("flavor"):
        config["flavor"] = request["flavor"]
    if isinstance(request.get("sources"), dict):
        config["sources"] = {name: bool(request["sources"].get(name, True)) for name in catalog.SOURCES}
    wowdir.save_config(config)
    return {"message": "Settings saved."}


def toggle(request):
    _, game = current_game()
    return {"message": library.set_enabled(game, request["id"], request["action"] == "enable")}


def remove(request):
    _, game = current_game()
    return {"message": library.remove(game, request["id"])}


def browse_catalog(request):
    return catalog.refresh(force=bool(request.get("force")))


def logos(request):
    return {"logos": catalog.logos(request.get("slugs") or [], everything=bool(request.get("all")))}


def details(request):
    source, ident = request.get("source", "wowinterface"), request["id"]
    info = sources.details(source, catalog.curseforge_id(ident) if source == "curseforge" else ident)
    # Keep the id the window asked for, so it can match the answer.
    return {"details": dict(info, id=str(ident))}


def resolve_source(request, game, other_games=False):
    """Work out what to install: (record, {"url", "md5", "size"} to download, or {"path"} of a local .zip).

    Only CurseForge and WoWInterface are downloaded from. Anything else must be
    a .zip the user already has. other_games is as in curseforge_release.
    """
    kind = request.get("source")
    text = (request.get("location") or "").strip()
    wowi = request.get("id") if kind == "wowinterface" else sources.wowinterface_page(text)
    if wowi:
        info = sources.wowi_details(wowi)
        if not info["download"]:
            raise Problem("WoWInterface has no download for that addon right now.")
        record = {"key": f"wowi:{info['id']}", "source": "wowinterface", "sourceId": info["id"], "name": info["name"],
                  "version": info["version"], "updated": info["updated"], "author": info["author"],
                  "url": f"https://www.wowinterface.com/downloads/info{info['id']}"}
        return record, {"url": info["download"], "md5": info["md5"]}
    project = request.get("id") if kind == "curseforge" else sources.curseforge_project(text)
    if project:
        release = curseforge_release(project, game, other_games)
        record = {"key": f"curseforge:{release['project']}", "source": "curseforge", "sourceId": release["project"],
                  "projectId": release.get("projectId", ""), "name": release["title"], "version": release["version"],
                  "fileId": release["fileId"], "url": release["url"]}
        if release.get("otherGame"):
            record["otherGame"] = True  # Its updates may keep coming from that game's files.
        return record, {"url": release["download"], "size": release["size"]}
    path = Path(text).expanduser()
    if text and path.is_file():
        return {"key": f"file:{path.name}", "source": "file", "sourceId": path.name, "name": path.stem}, {"path": path}
    raise Problem("Paste a CurseForge or WoWInterface addon page, or the path of a .zip you downloaded.")


def curseforge_release(project, game, other_games=False):
    """The CurseForge file for this game.

    other_games lets another game's file with the same major version stand in, and is only passed
    when the user chose to install the addon (or an addon that was installed that way is updated).
    Even then it only applies while the catalog says CurseForge doesn't list the addon for this game,
    as with an addon picked under "Any game version". Checks and updates of anything else never cross
    games, even if the catalog later stops listing the addon for this game.
    """
    listed = catalog.listing("curseforge", project) if other_games else {}
    elsewhere = bool(listed) and game.get("flavour") not in catalog.listed_games("curseforge", listed)
    return sources.curseforge_release(catalog.curseforge_id(project), game, catalog.curseforge_updated(project), other_games=elsewhere)


def install_one(request, game, state, replaces=None, installed=None, other_games=False):
    """Install one addon. Returns (message, record key).

    replaces is the installed addon's id when this takes it over. installed is
    (row, record) for an update, which refuses a file that isn't newer.
    other_games is as in curseforge_release.
    """
    record, fetch = resolve_source(request, game, other_games)
    newer = is_newer(record["source"], record, *installed) if installed else True
    if not newer:
        latest, current = record.get("version") or "no version", installed[0]["version"] or "unknown"
        raise Problem(f"its newest file ({latest}) isn't newer than the installed {current}." if newer is False
                      else f"can't tell whether its newest file ({latest}) is newer than the installed {current}, so it wasn't installed.")
    workspace = library.staging_dir(game)
    try:
        archive = fetch.get("path")
        if not archive:
            archive = workspace / "download.zip"
            sources.download(fetch["url"], archive, fetch.get("md5", ""), fetch.get("size", 0))
        unpacked = workspace / "unpacked"
        unpacked.mkdir()
        staged = sources.extract_addons(archive, unpacked)
        if record["source"] == "file":
            # No catalog identity: name it after the main folder so reinstalling replaces it.
            main = sorted(staged, key=lambda n: (len(n), n.lower()))[0]
            record.update(key=f"file:{main.lower()}", name=main)
        result = library.install(game, staged, record, state, replaces)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    dirs = result["record"]["dirs"]
    folders = ", ".join(dirs) if len(dirs) <= 4 else f"{len(dirs)} folders"
    extra = f" Replaced existing folders: {', '.join(result['replaced'])} (moved to trash)." if result["replaced"] else ""
    return f"Installed {record['name']} {record.get('version', '')}".rstrip() + f" · {folders}.{extra}", record["key"]


def fits(ref, game):
    """Whether the site lists this addon for exactly this game (WoW Forever, Classic Era, Retail, ...)."""
    return game.get("flavour") in ref.get("flavours", [])


def requirement_source(folder, entries, game):
    """The catalog listing that provides an addon folder, and its sites, best first."""
    wanted = folder.lower()
    candidates = [e for e in entries if wanted in (d.lower() for d in e["dirs"])]
    refs = lambda e: [r for r in e["sources"] if r["source"] in catalog.SOURCES]
    candidates = [e for e in candidates if refs(e)]
    if not candidates:
        return None, None
    # Prefer the listing named after the folder (DBM-Core -> "Deadly Boss Mods (DBM-Core)"), then one for this game, then the most used.
    entry = max(candidates, key=lambda e: (catalog.norm(folder) in catalog.norm(e["name"]) or e["dirs"][0].lower() == wanted,
                                           any(fits(r, game) for r in refs(e)), sum(r.get("downloads", 0) for r in refs(e))))
    return entry, sorted(refs(entry), key=lambda r: (fits(r, game), r.get("updated", 0)), reverse=True)


def add_requirements(game, state, keys):
    """Install the addons these ones require, and turn on required addons that are off. Returns notes.

    Requirements already installed are followed too: a plugin can't load if its core is missing a library.
    """
    notes, tried, keys, fetched = [], set(), set(keys), set()
    entries = None
    for _ in range(8):  # Requirements can have their own.
        rows = library.list_addons(game, state)
        owners = {d["name"].lower(): r for r in rows for d in r["dirs"]}
        wanting = [r for r in rows if r["id"] in keys]
        followed = False
        for row in wanting:
            for folder in row["requires"]:
                owner = owners.get(folder.lower())
                if not owner:
                    continue
                if owner["id"] not in keys:
                    keys.add(owner["id"])
                    followed = True
                if folder in row["requiresDisabled"] and owner["state"] != "enabled" and folder.lower() not in tried:
                    tried.add(folder.lower())
                    library.set_enabled(game, owner["id"], True, state)
                    owner["state"] = "enabled"
                    notes.append(f"Turned on {owner['name']}, which {row['name']} requires.")
        missing = [(row, folder) for row in wanting for folder in row["missing"] if folder.lower() not in tried]
        if not missing:
            if followed:
                continue
            break
        if entries is None:
            try:
                catalog.refresh()
            except Problem:
                pass
            entries = catalog.load_entries()
        for row, folder in missing:
            tried.add(folder.lower())
            entry, ranked = requirement_source(folder, entries, game)
            if not entry:
                notes.append(f"{row['name']} needs {folder}, which isn't on CurseForge or WoWInterface.")
                continue
            if entry["key"] in fetched:
                continue  # One listing often provides several required folders.
            fetched.add(entry["key"])
            try:
                _, key = install_first([{"source": r["source"], "id": r["id"]} for r in ranked], game, state)
                keys.add(key)
                notes.append(f"Also installed {entry['name']}, which {row['name']} requires.")
            except Problem as error:
                notes.append(f"{row['name']} needs {entry['name']}, but it couldn't be installed: {error}")
    return notes


FALLBACK_WINDOW = 30 * 86400 * 1000


def listed_updated(choice):
    """When the catalog last saw this site's listing change (ms), or 0 if unknown."""
    return catalog.listing(choice.get("source") or choice.get("site") or "", choice.get("id") or "").get("updated", 0)


def current_choices(choices):
    """Drop sites whose listing is far behind the addon's newest one: another site's
    year-old copy is no substitute for this week's release. Returns (kept, notes)."""
    newest = max((listed_updated(c) for c in choices), default=0)
    kept, notes = [], []
    for choice in choices:
        updated = listed_updated(choice)
        if newest and updated and updated < newest - FALLBACK_WINDOW:
            name = SOURCE_NAMES.get(choice.get("source") or choice.get("site"), "Another site")
            notes.append(f"{name}'s listing hasn't been updated since {time.strftime('%B %-d, %Y', time.localtime(updated / 1000))}, so it wasn't used.")
        else:
            kept.append(choice)
    return kept, notes


def listed_for(choice, game):
    """Whether the catalog says this site lists the addon for exactly this game."""
    source = choice.get("source") or choice.get("site") or ""
    return game.get("flavour") in catalog.listed_games(source, catalog.listing(source, choice.get("id") or ""))


def for_this_game(choices, game):
    """Keep sites that list the addon for this game, so a fallback never brings another game's build. Returns (kept, notes)."""
    kept = [c for c in choices if listed_for(c, game)]
    notes = [f"{SOURCE_NAMES.get(c.get('source') or c.get('site'), 'Another site')} doesn't list it for {game.get('name', 'this game')}, so it wasn't tried."
             for c in choices if c not in kept]
    return kept, notes


def install_first(choices, game, state, replaces=None, other_games=False):
    """Install from the first site that works. Returns (message, key); raises the first site's problem if none do.

    The first site is the one chosen. The others are fallbacks, used only if they list the addon for this game.
    """
    first, rest = choices[:1], choices[1:]
    rest, skipped = current_choices(first + rest)
    rest = [c for c in rest if c is not first[0]] if first else rest
    rest, other_game = for_this_game(rest, game)
    problems = []
    for choice in first + rest:
        try:
            message, key = install_one(choice, game, state, replaces, other_games=other_games)
        except Problem as error:
            problems.append((choice, error))
            continue
        if problems:
            failed, error = problems[0]
            message += f" ({SOURCE_NAMES.get(failed.get('source') or failed.get('site'), 'The first site')} didn't work: {error})"
        return message, key
    advice = " You can download it from the addon's page and add the .zip." if skipped else ""
    raise Problem(" ".join([str(problems[0][1])] + skipped + other_game) + advice)


def install(request):
    """Install an addon. From Browse, the addon's other site is tried if the first one fails."""
    _, game = current_game()
    state = library.load_state()
    choices = [request] + [dict(alt) for alt in request.get("alternatives") or [] if alt.get("source") in SOURCE_NAMES]
    if "alternatives" not in request:
        # A pasted page link: the same addon's listing on the other site is the fallback.
        text = request.get("location") or ""
        wowi, project = sources.wowinterface_page(text), sources.curseforge_project(text)
        site = ("wowinterface", wowi) if wowi else ("curseforge", project) if project else (None, None)
        if site[1]:
            choices = [dict(request, site=site[0], id=site[1])] + other_sites(catalog.load_entries()).get((site[0], str(site[1]).lower()), [])
    replaces = request.get("replaces") if isinstance(request.get("replaces"), str) else None
    # The user chose this addon, so an addon CurseForge only lists for another game may use that game's file.
    message, key = install_first(choices, game, state, replaces, other_games=True)
    return {"message": " ".join([message] + add_requirements(game, state, [key]))}


def requirements(request):
    _, game = current_game()
    notes = add_requirements(game, library.load_state(), [request["id"]])
    return {"message": " ".join(notes) or "Nothing else is needed."}


SOURCE_NAMES = {"wowinterface": "WoWInterface", "curseforge": "CurseForge"}


def is_newer(source, latest, row, record):
    """Whether a site's newest file is newer than the installed copy: True, False, or None when
    the versions can't be ordered. Only True counts as an update, so one never goes back a version.

    latest has the file's "version", plus "fileId" from CurseForge or "updated" from WoWInterface.
    """
    if record and record["source"] == source:
        if source == "curseforge" and record.get("fileId") and latest.get("fileId"):
            return latest["fileId"] > record["fileId"]  # CurseForge numbers files in upload order.
        if source == "wowinterface" and record.get("updated") and latest.get("updated"):
            return latest["updated"] > record["updated"]
        installed = record.get("version") or row["tocVersion"]
    else:
        # A hand install, or another site's copy of the addon: only the version says which is newer.
        installed = row["tocVersion"]
    order = sources.compare_versions(latest.get("version"), installed)
    return None if order is None else order > 0


def newest(link, row, record, game, wowi):
    """(latest version, whether it's newer than the installed copy, per is_newer) from one source."""
    source, ident = link["source"], link["id"]
    if source == "wowinterface":
        entry = wowi.get(ident)
        if not entry:
            raise Problem("not listed in the WoWInterface catalog.")
        return entry["version"], is_newer(source, entry, row, record)
    own = record if (record or {}).get("source") == source else {}
    release = curseforge_release(own.get("projectId") or ident, game, other_games=bool(own.get("otherGame")))
    return release["version"], is_newer(source, release, row, record)


def other_sites(entries):
    """(source, id) -> the same addon's listings on the other site, from the catalog."""
    index = {}
    for entry in entries:
        refs = [r for r in entry["sources"] if r["source"] in SOURCE_NAMES]
        for r in refs:
            others = [{"source": o["source"], "id": o["id"]} for o in refs if o["source"] != r["source"]]
            for ident in (r["id"], r.get("numericId")):
                if ident:
                    index[(r["source"], str(ident).lower())] = others
    return index


def with_fallbacks(row, index, game):
    """An addon's own site first, then the same addon on the other site, in case the first can't answer.

    Only the site this app installed the addon from is trusted as is. Any other site, including
    ones a hand install's TOC names, must list the addon for this game, so an update never brings
    another game's build. A site whose listing is far behind the newest one is left out too, so
    it can't offer an older version.
    """
    links = list(row["links"])
    for link in list(links):
        for other in index.get((link["source"], str(link["id"]).lower()), []):
            if all(other["source"] != l["source"] for l in links):
                links.append(other)
    own = links[:1] if row["managed"] else []
    return current_choices(own + [l for l in links[len(own):] if listed_for(l, game)])[0]


def unlisted(row, game):
    return f"Neither site lists {row['name']} for {game.get('name', 'this game')}, so it isn't updated from them."


def check(request):
    """Look up the newest version of every installed addon with a known source.

    Addons installed here use their recorded source. Hand installs use the
    sources their TOC declares, trying each until one answers.
    """
    _, game = current_game()
    state = library.load_state()
    rows = [r for r in library.list_addons(game, state) if r["links"]]
    records = {r["key"]: r for r in library.packages(state, game)}
    if rows:
        # Which game each site lists an addon for comes from the catalog, and WoWInterface's versions too.
        try:
            catalog.refresh(force=bool(request.get("force")), max_age=3600)
        except Problem:
            pass  # Each affected addon reports the catalog as missing.
    index = other_sites(catalog.load_entries())
    wowi = {e["id"]: e for e in catalog.source_entries("wowinterface")}
    checks = {}
    for row in rows:
        links = with_fallbacks(row, index, game)
        if not links:
            checks[row["id"]] = {"state": "unknown", "message": unlisted(row, game)}
            continue
        problems = []
        for link in links:
            try:
                latest, newer = newest(link, row, records.get(row["id"]), game, wowi)
                checks[row["id"]] = {"state": {True: "available", False: "current"}.get(newer, "unknown"), "latest": latest, "source": link["source"]}
                if newer is None:
                    checks[row["id"]]["message"] = (f"{SOURCE_NAMES[link['source']]} has {latest}, but it isn't clear whether that's newer than "
                                                    f"yours ({row['version'] or 'no version'}), so it isn't offered as an update.")
                break
            except Problem as error:
                problems.append(f"{SOURCE_NAMES[link['source']]}: {error}")
        else:
            checks[row["id"]] = {"state": "error", "message": " ".join(problems)}
    # The window may have switched games while this ran; this says which game the results are for.
    return {"checks": checks, "game": game["addons"]}


def update(request):
    _, game = current_game()
    state = library.load_state()
    rows = {r["id"]: r for r in library.list_addons(game, state)}
    records = {r["key"]: r for r in library.packages(state, game)}
    index = other_sites(catalog.load_entries())
    preferred = request.get("sources") or {}
    results = []
    for key in request.get("ids", []):
        row = rows.get(key)
        if not row or not row["links"]:
            results.append({"id": key, "ok": False, "message": f"{row['name'] if row else key}: no source to update from."})
            continue
        # Start with the source whose check found the update.
        links = sorted(with_fallbacks(row, index, game), key=lambda link: link["source"] != preferred.get(key))
        if not links:
            results.append({"id": key, "ok": False, "message": unlisted(row, game)})
            continue
        problems = []
        for link in links:
            try:
                record = records.get(key) or {}
                message, new_key = install_one({"source": link["source"], "id": link["id"]}, game, state, replaces=key,
                                               installed=(row, records.get(key)), other_games=bool(record.get("otherGame")))
                results.append({"id": key, "ok": True, "message": " ".join([message] + add_requirements(game, state, [new_key]))})
                break
            except Problem as error:
                problems.append(f"{SOURCE_NAMES[link['source']]}: {error}")
        else:
            results.append({"id": key, "ok": False, "message": f"{row['name']}: {' '.join(problems)}"})
    return {"results": results}


ACTIONS = {"list": overview, "configure": configure, "enable": toggle, "disable": toggle, "remove": remove,
           "catalog": browse_catalog, "details": details, "logos": logos, "install": install, "requirements": requirements, "check": check, "update": update}


def main():
    try:
        request = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {"action": "list"}
        handler = ACTIONS.get(request.get("action"))
        if not handler:
            raise Problem(f"Unknown action: {request.get('action')}")
        response = dict(handler(request), ok=True)
    except Problem as error:
        response = {"ok": False, "error": str(error)}
    except (OSError, KeyError, ValueError) as error:
        traceback.print_exc()
        response = {"ok": False, "error": f"Unexpected problem: {error}"}
    print(json.dumps(response))


if __name__ == "__main__":
    main()
