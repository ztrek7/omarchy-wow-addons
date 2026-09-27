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


def resolve_source(request, game):
    """Work out what to install: (record, {"url", "md5", "size"} to download, or {"path"} of a local .zip).

    Only CurseForge and WoWInterface are downloaded from. Anything else must be
    a .zip the user already has.
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
        release = sources.curseforge_release(catalog.curseforge_id(project), game, catalog.curseforge_updated(project))
        record = {"key": f"curseforge:{release['project']}", "source": "curseforge", "sourceId": release["project"],
                  "projectId": release.get("projectId", ""), "name": release["title"], "version": release["version"],
                  "fileId": release["fileId"], "url": release["url"]}
        return record, {"url": release["download"], "size": release["size"]}
    path = Path(text).expanduser()
    if text and path.is_file():
        return {"key": f"file:{path.name}", "source": "file", "sourceId": path.name, "name": path.stem}, {"path": path}
    raise Problem("Paste a CurseForge or WoWInterface addon page, or the path of a .zip you downloaded.")


def install_one(request, game, state):
    """Install one addon. Returns (message, record key)."""
    record, fetch = resolve_source(request, game)
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
        result = library.install(game, staged, record, state)
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
    """Install the addons these ones require, and turn on required addons that are off. Returns notes."""
    notes, tried, keys, fetched = [], set(), set(keys), set()
    entries = None
    for _ in range(4):  # Requirements can have their own.
        rows = library.list_addons(game, state)
        wanting = [r for r in rows if r["id"] in keys]
        for row in wanting:
            for folder in row["requiresDisabled"]:
                owner = next((r for r in rows if any(d["name"].lower() == folder.lower() for d in r["dirs"])), None)
                if owner and owner["state"] != "enabled" and folder.lower() not in tried:
                    tried.add(folder.lower())
                    library.set_enabled(game, owner["id"], True, state)
                    notes.append(f"Turned on {owner['name']}, which {row['name']} requires.")
        missing = [(row, folder) for row in wanting for folder in row["missing"] if folder.lower() not in tried]
        if not missing:
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


def install_first(choices, game, state):
    """Install from the first site that works. Returns (message, key); raises the first site's problem if none do."""
    problems = []
    for choice in choices:
        try:
            message, key = install_one(choice, game, state)
        except Problem as error:
            problems.append((choice, error))
            continue
        if problems:
            first, error = problems[0]
            message += f" ({SOURCE_NAMES.get(first.get('source'), 'The first site')} didn't work: {error})"
        return message, key
    raise problems[0][1]


def install(request):
    """Install an addon. From Browse, the addon's other site is tried if the first one fails."""
    _, game = current_game()
    state = library.load_state()
    choices = [request] + [dict(alt) for alt in request.get("alternatives") or [] if alt.get("source") in SOURCE_NAMES]
    message, key = install_first(choices, game, state)
    return {"message": " ".join([message] + add_requirements(game, state, [key]))}


def requirements(request):
    _, game = current_game()
    notes = add_requirements(game, library.load_state(), [request["id"]])
    return {"message": " ".join(notes) or "Nothing else is needed."}


SOURCE_NAMES = {"wowinterface": "WoWInterface", "curseforge": "CurseForge"}


def newest(link, row, record, game, wowi):
    """(latest version, whether it's newer than the installed copy) from one source."""
    source, ident, installed = link["source"], link["id"], row["tocVersion"]
    if source == "wowinterface":
        entry = wowi.get(ident)
        if not entry:
            raise Problem("not listed in the WoWInterface catalog.")
        if record:
            return entry["version"], entry["updated"] > record.get("updated", 0) or entry["version"] != record.get("version")
        return entry["version"], not sources.same_version(entry["version"], installed)
    project = (record or {}).get("projectId") or ident
    release = sources.curseforge_release(catalog.curseforge_id(project), game, catalog.curseforge_updated(project))
    if record:
        return release["version"], release["fileId"] != record.get("fileId")
    # Hand installs have no record, so compare with the version in their TOC.
    return release["version"], not sources.same_version(release["version"], installed)


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


def with_fallbacks(row, index):
    """An addon's own site first, then the same addon on the other site, in case the first can't answer."""
    links = list(row["links"])
    for link in list(links):
        for other in index.get((link["source"], str(link["id"]).lower()), []):
            if all(other["source"] != l["source"] for l in links):
                links.append(other)
    return links


def check(request):
    """Look up the newest version of every installed addon with a known source.

    Addons installed here use their recorded source. Hand installs use the
    sources their TOC declares, trying each until one answers.
    """
    _, game = current_game()
    state = library.load_state()
    rows = [r for r in library.list_addons(game, state) if r["links"]]
    records = {r["key"]: r for r in library.packages(state, game)}
    index = other_sites(catalog.load_entries())
    wowi = {}
    if any(link["source"] == "wowinterface" for r in rows for link in with_fallbacks(r, index)):
        try:
            catalog.refresh(force=bool(request.get("force")), max_age=3600)
        except Problem:
            pass  # Each affected addon reports the catalog as missing.
        wowi = {e["id"]: e for e in catalog.source_entries("wowinterface")}
    checks = {}
    for row in rows:
        problems = []
        for link in with_fallbacks(row, index):
            # An install record only describes the site it came from; elsewhere, compare with the installed version.
            record = records.get(row["id"])
            record = record if record and record["source"] == link["source"] else None
            try:
                latest, newer = newest(link, row, record, game, wowi)
                checks[row["id"]] = {"state": "available" if newer else "current", "latest": latest, "source": link["source"]}
                break
            except Problem as error:
                problems.append(f"{SOURCE_NAMES[link['source']]}: {error}")
        else:
            checks[row["id"]] = {"state": "error", "message": " ".join(problems)}
    return {"checks": checks}


def update(request):
    _, game = current_game()
    state = library.load_state()
    rows = {r["id"]: r for r in library.list_addons(game, state)}
    index = other_sites(catalog.load_entries())
    preferred = request.get("sources") or {}
    results = []
    for key in request.get("ids", []):
        row = rows.get(key)
        if not row or not row["links"]:
            results.append({"id": key, "ok": False, "message": f"{row['name'] if row else key}: no source to update from."})
            continue
        # Start with the source whose check found the update.
        links = sorted(with_fallbacks(row, index), key=lambda link: link["source"] != preferred.get(key))
        problems = []
        for link in links:
            try:
                message, new_key = install_one({"source": link["source"], "id": link["id"]}, game, state)
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
