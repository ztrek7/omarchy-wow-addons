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


def details(request):
    return {"details": sources.details(request.get("source", "wowinterface"), request["id"])}


def resolve_source(request, game):
    """Work out what to install: (record, {"url", "md5", "size"} to download, or {"path"} of a local .zip)."""
    kind = request.get("source")
    text = (request.get("location") or "").strip()
    if kind == "wowinterface":
        info = sources.wowi_details(request["id"])
        if not info["download"]:
            raise Problem("WoWInterface has no download for that addon right now.")
        record = {"key": f"wowi:{info['id']}", "source": "wowinterface", "sourceId": info["id"], "name": info["name"],
                  "version": info["version"], "updated": info["updated"], "author": info["author"],
                  "url": f"https://www.wowinterface.com/downloads/info{info['id']}"}
        return record, {"url": info["download"], "md5": info["md5"]}
    if kind == "tukui":
        release = sources.tukui_release(request["id"])
        record = {"key": f"tukui:{release['id']}", "source": "tukui", "sourceId": release["id"], "name": release["name"],
                  "version": release["version"], "author": release["author"], "url": release["url"]}
        return record, {"url": release["download"]}
    project = request.get("id") if kind == "curseforge" else sources.curseforge_project(text)
    if project:
        release = sources.curseforge_release(project, game)
        record = {"key": f"curseforge:{release['project']}", "source": "curseforge", "sourceId": release["project"],
                  "name": release["title"], "version": release["version"], "fileId": release["fileId"], "url": release["url"]}
        return record, {"url": release["download"], "size": release["size"]}
    path = Path(text).expanduser()
    if text and path.is_file():
        return {"key": f"file:{path.name}", "source": "file", "sourceId": path.name, "name": path.stem}, {"path": path}
    repo = sources.github_repo(text or request.get("id", "")) if kind in ("github", None, "") else None
    if repo:
        release = sources.github_release(repo, game)
        record = {"key": f"github:{repo.lower()}", "source": "github", "sourceId": repo, "name": repo.split("/")[1],
                  "version": release["tag"], "releaseId": release["releaseId"], "asset": release["asset"],
                  "url": f"https://github.com/{repo}"}
        return record, {"url": release["download"]}
    if text.startswith("https://"):
        name = Path(text.split("?")[0]).name
        return {"key": f"url:{text}", "source": "url", "sourceId": text, "name": Path(name).stem or "Addon", "url": text}, {"url": text}
    raise Problem("Enter a GitHub repository, a CurseForge addon page, an https:// link to a .zip, or the path of a .zip on this computer.")


def install_one(request, game, state):
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
        if record["source"] in ("url", "file"):
            # No catalog identity: name it after the main folder so reinstalling replaces it.
            main = sorted(staged, key=lambda n: (len(n), n.lower()))[0]
            record.update(key=f"{record['source']}:{main.lower()}", name=main)
        result = library.install(game, staged, record, state)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    folders = ", ".join(result["record"]["dirs"])
    extra = f" Replaced existing folders: {', '.join(result['replaced'])} (moved to trash)." if result["replaced"] else ""
    return f"Installed {record['name']} {record.get('version', '')}".rstrip() + f" · {folders}.{extra}"


def install(request):
    _, game = current_game()
    return {"message": install_one(request, game, library.load_state())}


SOURCE_NAMES = {"wowinterface": "WoWInterface", "curseforge": "CurseForge", "tukui": "Tukui", "github": "GitHub"}


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
    if source == "tukui":
        latest = sources.tukui_release(ident)["version"]
        return latest, not sources.same_version(latest, record.get("version") if record else installed)
    if source == "curseforge":
        release = sources.curseforge_release(ident, game)
        latest, newer = release["version"], record and release["fileId"] != record.get("fileId")
    else:
        release = sources.github_release(ident, game)
        latest, newer = release["tag"], record and release["releaseId"] != record.get("releaseId")
    # Hand installs have no record, so compare with the version in their TOC.
    return latest, bool(newer) if record else not sources.same_version(latest, installed)


def check(request):
    """Look up the newest version of every installed addon with a known source.

    Addons installed here use their recorded source. Hand installs use the
    sources their TOC declares, trying each until one answers.
    """
    _, game = current_game()
    state = library.load_state()
    rows = [r for r in library.list_addons(game, state) if r["links"]]
    records = {r["key"]: r for r in library.packages(state, game)}
    wowi = {}
    if any(link["source"] == "wowinterface" for r in rows for link in r["links"]):
        try:
            catalog.refresh(force=bool(request.get("force")), max_age=3600)
        except Problem:
            pass  # Each affected addon reports the catalog as missing.
        wowi = {e["id"]: e for e in catalog.source_entries("wowinterface")}
    checks = {}
    for row in rows:
        problems = []
        for link in row["links"]:
            try:
                latest, newer = newest(link, row, records.get(row["id"]), game, wowi)
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
    preferred = request.get("sources") or {}
    results = []
    for key in request.get("ids", []):
        row = rows.get(key)
        if not row or not row["links"]:
            results.append({"id": key, "ok": False, "message": f"{row['name'] if row else key}: no source to update from."})
            continue
        # Start with the source whose check found the update.
        links = sorted(row["links"], key=lambda link: link["source"] != preferred.get(key))
        problems = []
        for link in links:
            try:
                message = install_one({"source": link["source"], "id": link["id"]}, game, state)
                results.append({"id": key, "ok": True, "message": message})
                break
            except Problem as error:
                problems.append(f"{SOURCE_NAMES[link['source']]}: {error}")
        else:
            results.append({"id": key, "ok": False, "message": f"{row['name']}: {' '.join(problems)}"})
    return {"results": results}


ACTIONS = {"list": overview, "configure": configure, "enable": toggle, "disable": toggle, "remove": remove,
           "catalog": browse_catalog, "details": details, "install": install, "check": check, "update": update}


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
