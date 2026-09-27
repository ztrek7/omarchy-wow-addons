"""Installed addons: list, enable, disable, remove, and place new folders.

Disabling moves folders to Interface/AddOns.disabled so the change applies to
every character and survives the game rewriting WTF/.../AddOns.txt on logout.
Nothing is deleted outright: replaced and removed folders go to the trash.
"""
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import urllib.parse

import wowdir

DATA = Path(os.environ.get("XDG_DATA_HOME") or wowdir.HOME / ".local/share")
STATE = DATA / "wow-addons" / "state.json"
TRASH = DATA / "Trash"
STAGING_PREFIX = ".wow-addons-staging-"
UPDATABLE = ("wowinterface", "curseforge", "github")


class Problem(Exception):
    """A failure the user can act on; its message is shown as-is."""


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def load_state():
    try:
        data = json.loads(STATE.read_text())
        return data if isinstance(data, dict) and isinstance(data.get("installs"), dict) else {"installs": {}}
    except (OSError, ValueError):
        return {"installs": {}}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(STATE)


def packages(state, game):
    return state["installs"].setdefault(game["addons"], [])


def locations(game):
    addons = Path(game["addons"])
    return addons, addons.parent / wowdir.DISABLED_DIR


def folders(game):
    """{folder name: (path, enabled)} across enabled and disabled locations; enabled wins on duplicates."""
    enabled, disabled = locations(game)
    found = {}
    for base, is_enabled in ((disabled, False), (enabled, True)):
        try:
            children = list(base.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and not child.name.startswith("."):
                found[child.name] = (child, is_enabled)
    return found


def prefix(name):
    return re.split(r"[-_ ]", name, maxsplit=1)[0].lower()


def group_unmanaged(names, meta):
    """Fold module folders (DBM-Raids depends on DBM-Core) into the addon they extend."""
    parent = {}
    for name in names:
        info = meta[name]
        candidates = [info["group"]] if info["group"] in names and info["group"] != name else []
        candidates += [d for d in info["dependencies"] if d in names and d != name and prefix(d) == prefix(name)]
        if candidates:
            parent[name] = candidates[0]

    def root(name, seen=()):
        up = parent.get(name)
        return name if not up or up in seen else root(up, seen + (name,))

    groups = {}
    for name in sorted(names, key=str.lower):
        groups.setdefault(root(name), []).append(name)
    return groups


def state_label(dirs):
    states = {d["enabled"] for d in dirs}
    return "enabled" if states == {True} else "disabled" if states == {False} else "partial"


def list_addons(game, state=None):
    state = load_state() if state is None else state
    present = folders(game)
    meta = {name: wowdir.read_addon(path, game) for name, (path, _) in present.items()}
    rows, owned = [], set()
    records = packages(state, game)
    for record in list(records):
        dirs = [d for d in record["dirs"] if d in present]
        if not dirs:
            records.remove(record)  # Deleted outside the app.
            continue
        owned.update(dirs)
        rows.append(row(record["key"], dirs, present, meta, record))
    unmanaged = [name for name in present if name not in owned]
    for main, members in group_unmanaged(unmanaged, meta).items():
        rows.append(row("local:" + main, members, present, meta, None))
    rows.sort(key=lambda r: r["name"].lower())
    return rows


def row(key, dirs, present, meta, record):
    # Name the addon after its main folder: the shortest name, or the one the record says.
    main = sorted(dirs, key=lambda d: (len(d), d.lower()))[0]
    info = meta[main]
    entries = [{"name": d, "title": meta[d]["title"], "enabled": present[d][1], "outOfDate": meta[d]["outOfDate"],
                "loadable": meta[d]["loadable"], "path": str(present[d][0])} for d in sorted(dirs, key=str.lower)]
    record = record or {}
    if record.get("source") in UPDATABLE:
        links = [{"source": record["source"], "id": record["sourceId"]}]
    elif record:
        links = []  # A .zip install: the user chose that exact file.
    else:
        links = info["links"]
    return {
        "id": key,
        "name": record.get("name") or info["title"],
        "version": record.get("version") or info["version"],
        "tocVersion": info["version"],
        "author": record.get("author") or info["author"],
        "notes": info["notes"],
        "website": record.get("url") or info["website"],
        "category": record.get("category") or info["category"],
        "interfaces": info["interfaces"],
        "savedVariables": sorted({v for d in dirs for v in meta[d]["savedVariables"]}),
        "dirs": entries,
        "state": state_label(entries),
        "outOfDate": any(e["outOfDate"] for e in entries),
        "loadable": any(e["loadable"] for e in entries),
        "managed": bool(record),
        "source": record.get("source", "manual"),
        "sourceId": record.get("sourceId", ""),
        "updated": record.get("updated", 0),
        "installedAt": record.get("installedAt", ""),
        "path": entries[[e["name"] for e in entries].index(main)]["path"],
        # Where updates are checked, in order of preference. Hand installs use what their TOC declares.
        "links": links,
    }


def find_row(game, key, state):
    match = next((r for r in list_addons(game, state) if r["id"] == key), None)
    if not match:
        raise Problem("That addon is no longer installed. Refresh to see the current folder.")
    return match


def set_enabled(game, key, enable, state=None):
    state = load_state() if state is None else state
    target = find_row(game, key, state)
    enabled, disabled = locations(game)
    source, destination = (disabled, enabled) if enable else (enabled, disabled)
    moving = [d["name"] for d in target["dirs"] if d["enabled"] != enable]
    clashes = [name for name in moving if (destination / name).exists()]
    if clashes:
        raise Problem(f"Both {enabled.name} and {disabled.name} contain {', '.join(clashes)}. Remove one copy first.")
    destination.mkdir(exist_ok=True)
    for name in moving:
        os.rename(source / name, destination / name)
    save_state(state)
    verb = "Enabled" if enable else "Disabled"
    return f"{verb} {target['name']} ({len(moving)} folder{'s' if len(moving) != 1 else ''})."


def trash(path):
    """Move a path to the freedesktop trash so a mistaken removal can be undone."""
    path = Path(path)
    files, info = TRASH / "files", TRASH / "info"
    files.mkdir(parents=True, exist_ok=True)
    info.mkdir(parents=True, exist_ok=True)
    name, counter = path.name, 1
    while (files / name).exists() or (info / f"{name}.trashinfo").exists():
        counter += 1
        name = f"{path.name}.{counter}"
    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    (info / f"{name}.trashinfo").write_text(
        f"[Trash Info]\nPath={urllib.parse.quote(str(path.absolute()))}\nDeletionDate={stamp}\n")
    shutil.move(str(path), str(files / name))
    return files / name


def remove(game, key, state=None):
    state = load_state() if state is None else state
    target = find_row(game, key, state)
    records = packages(state, game)
    for d in target["dirs"]:
        trash(d["path"])
    records[:] = [r for r in records if r["key"] != key]
    save_state(state)
    note = " Its saved settings stay in WTF." if target["savedVariables"] else ""
    count = len(target["dirs"])
    return f"Moved {target['name']} to the trash ({count} folder{'s' if count != 1 else ''}).{note}"


def install(game, staged, record, state=None):
    """Move staged addon folders into place.

    staged maps folder name -> extracted path on the same filesystem as AddOns.
    Folders keep their current enabled/disabled location; existing copies go to
    the trash. Folders the previous version had but this one doesn't are trashed too.
    """
    state = load_state() if state is None else state
    records = packages(state, game)
    enabled, disabled = locations(game)
    enabled.mkdir(parents=True, exist_ok=True)
    present = folders(game)
    previous = next((r for r in records if r["key"] == record["key"]), None)
    replaced = []
    for name, source in staged.items():
        destination = enabled
        if name in present:
            path, is_enabled = present[name]
            destination = enabled if is_enabled else disabled
            trash(path)
            replaced.append(name)
        os.rename(source, destination / name)
    retired = [d for d in (previous or {}).get("dirs", []) if d not in staged and d in present]
    for name in retired:
        trash(present[name][0])
    # A folder belongs to one package; the newest install takes it over.
    for other in records:
        if other["key"] != record["key"]:
            other["dirs"] = [d for d in other["dirs"] if d not in staged]
    records[:] = [r for r in records if r["key"] != record["key"] and r["dirs"]]
    record = dict(record, dirs=sorted(staged, key=str.lower), installedAt=(previous or {}).get("installedAt") or now())
    if previous:
        record["updatedAt"] = now()
    records.append(record)
    save_state(state)
    return {"replaced": replaced, "retired": retired, "record": record}


def staging_dir(game):
    """A scratch folder beside AddOns, so moving extracted folders into place is a rename."""
    parent = Path(game["addons"]).parent
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=parent))
