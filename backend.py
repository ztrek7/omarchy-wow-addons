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
    wowdir.save_config(config)
    return {"message": "Settings saved."}


def toggle(request):
    _, game = current_game()
    return {"message": library.set_enabled(game, request["id"], request["action"] == "enable")}


def remove(request):
    _, game = current_game()
    return {"message": library.remove(game, request["id"])}


def catalog(request):
    return sources.refresh_catalog(force=bool(request.get("force")))


def details(request):
    return {"details": sources.wowi_details(request["id"])}


def resolve_source(request, game):
    """Describe what to download for a request, as (record, download url, md5, local archive)."""
    kind = request.get("source")
    if kind == "wowinterface":
        info = sources.wowi_details(request["id"])
        if not info["download"]:
            raise Problem("WoWInterface has no download for that addon right now.")
        record = {"key": f"wowi:{info['id']}", "source": "wowinterface", "sourceId": info["id"], "name": info["name"],
                  "version": info["version"], "updated": info["updated"], "author": info["author"],
                  "url": f"https://www.wowinterface.com/downloads/info{info['id']}"}
        return record, info["download"], info["md5"], None
    text = (request.get("location") or "").strip()
    path = Path(text).expanduser()
    if text and path.is_file():
        return {"key": f"file:{path.name}", "source": "file", "sourceId": path.name, "name": path.stem}, "", "", path
    repo = sources.github_repo(text or request.get("id", "")) if kind in ("github", None, "") else None
    if repo:
        release = sources.github_release(repo, game)
        record = {"key": f"github:{repo.lower()}", "source": "github", "sourceId": repo, "name": repo.split("/")[1],
                  "version": release["tag"], "releaseId": release["releaseId"], "asset": release["asset"],
                  "url": f"https://github.com/{repo}"}
        return record, release["download"], "", None
    if text.startswith("https://"):
        name = Path(text.split("?")[0]).name
        return {"key": f"url:{text}", "source": "url", "sourceId": text, "name": Path(name).stem or "Addon", "url": text}, text, "", None
    raise Problem("Enter a GitHub repository, an https:// link to a .zip, or the path of a .zip file on this computer.")


def install_one(request, game, state):
    record, url, md5, archive = resolve_source(request, game)
    workspace = library.staging_dir(game)
    try:
        if not archive:
            archive = workspace / "download.zip"
            sources.download(url, archive, md5)
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


def check(request):
    """Compare installed WoWInterface and GitHub addons with their sources."""
    _, game = current_game()
    state = library.load_state()
    records = library.packages(state, game)
    catalog = None
    if any(r["source"] == "wowinterface" for r in records):
        sources.refresh_catalog(force=True)
        catalog = {e["id"]: e for e in (sources.load_catalog() or {}).get("entries", [])}
    checks = {}
    for record in records:
        try:
            if record["source"] == "wowinterface":
                entry = catalog.get(record["sourceId"])
                if not entry:
                    checks[record["key"]] = {"state": "error", "message": "No longer listed on WoWInterface."}
                elif entry["updated"] > record.get("updated", 0) or entry["version"] != record.get("version"):
                    checks[record["key"]] = {"state": "available", "latest": entry["version"]}
                else:
                    checks[record["key"]] = {"state": "current", "latest": entry["version"]}
            elif record["source"] == "github":
                release = sources.github_release(record["sourceId"], game)
                newer = release["releaseId"] != record.get("releaseId")
                checks[record["key"]] = {"state": "available" if newer else "current", "latest": release["tag"]}
        except Problem as error:
            checks[record["key"]] = {"state": "error", "message": str(error)}
    return {"checks": checks}


def update(request):
    _, game = current_game()
    state = library.load_state()
    records = {r["key"]: r for r in library.packages(state, game)}
    results = []
    for key in request.get("ids", []):
        record = records.get(key)
        if not record or record["source"] not in ("wowinterface", "github"):
            results.append({"id": key, "ok": False, "message": f"{key}: can't be updated automatically."})
            continue
        try:
            message = install_one({"source": record["source"], "id": record["sourceId"]}, game, state)
            results.append({"id": key, "ok": True, "message": message})
        except Problem as error:
            results.append({"id": key, "ok": False, "message": f"{record['name']}: {error}"})
    return {"results": results}


ACTIONS = {"list": overview, "configure": configure, "enable": toggle, "disable": toggle, "remove": remove,
           "catalog": catalog, "details": details, "install": install, "check": check, "update": update}


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
