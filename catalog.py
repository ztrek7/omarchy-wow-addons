"""The Browse catalog: CurseForge's and WoWInterface's lists, cached separately, merged so an addon appears once.

Neither needs an API key:
- CurseForge: the daily community catalog published by the instawow project
  (https://github.com/layday/instawow-data), which lists active addons with
  download counts, game flavours, folders, and links to the same addon on other
  sites. Details and files come from CFWidget and CurseForge's CDN.
- WoWInterface: its official public file list.
"""
from collections import defaultdict
import datetime
import json
import re
import time

from library import Problem
import sources

SOURCES = ("curseforge", "wowinterface")
# Bump when merge rules or entry fields change, so a cached merge is rebuilt.
FORMAT = 2
TTL = 6 * 3600
INSTAWOW = "https://raw.githubusercontent.com/layday/instawow-data/data/base-catalogue-v8.compact.json"
# instawow's source names -> ours.
ALIASES = {"curse": "curseforge", "wowi": "wowinterface", "wago": "wago", "github": "github"}
PREFERENCE = {"curseforge": 0, "wowinterface": 1, "wago": 2}


def cache_file(name):
    return sources.CACHE / f"source-{name}.json"


def merged_file():
    return sources.CACHE / "catalog.json"


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, separators=(",", ":")))
    temporary.replace(path)


def iso_ms(value):
    try:
        return int(datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return 0


# --- Fetching each source ----------------------------------------------------

def fetch_wowinterface():
    files = sources.fetch_json(f"{sources.WOWI}/filelist.json")
    categories = sources.fetch_json(f"{sources.WOWI}/categorylist.json")
    if not isinstance(files, list) or not isinstance(categories, list):
        raise Problem("WoWInterface returned an unexpected catalog format.")
    return {"entries": sources.compact_wowinterface(files, categories)}


def fetch_curseforge():
    data = sources.fetch_json(INSTAWOW)
    items = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise Problem("The CurseForge catalog has an unexpected format.")
    entries, links = [], []
    for item in items:
        if not isinstance(item, dict):
            continue
        same = [[ALIASES.get(s.get("source")), str(s.get("id"))] for s in item.get("same_as") or [] if ALIASES.get(s.get("source"))]
        if item.get("source") == "curse" and item.get("slug"):
            folders = sorted({f for group in item.get("folders") or [] for f in group if isinstance(f, str)}, key=str.lower)
            entries.append({
                "id": item["slug"], "numericId": str(item.get("id", "")), "name": item.get("name") or item["slug"],
                "url": item.get("url") or f"https://www.curseforge.com/wow/addons/{item['slug']}",
                "flavours": item.get("game_flavours") or [], "downloads": int(item.get("download_count") or 0),
                "updated": iso_ms(item.get("last_updated")), "dirs": folders, "sameAs": same,
            })
        elif len(same) >= 2:
            # A listing elsewhere that names the same addon on two sites links
            # those two. It's only used to match them, never shown or installed.
            links.append(same)
    return {"entries": entries, "links": links}


FETCHERS = {"curseforge": fetch_curseforge, "wowinterface": fetch_wowinterface}


def load_entries():
    """The merged catalog as last built."""
    return (read(merged_file()) or {}).get("entries", [])


def source_entries(name):
    """One source's cached entries, e.g. for update checks."""
    return (read(cache_file(name)) or {}).get("entries", [])


# --- Merging -----------------------------------------------------------------

def norm(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def name_keys(name):
    """The full name plus its parts without extras: "DBM - Deadly Boss Mods (DBM-Core)" also matches "Deadly Boss Mods"."""
    core = re.sub(r"\s*[(\[][^)\]]*[)\]]", "", name or "")
    parts = re.split(r"\s+[-|–:]\s+", core)
    return {k for k in [norm(name), norm(core)] + [norm(p) for p in parts] if len(k) >= 3}


def folder_key(folder):
    """Some uploads name their folder after the release, e.g. GatherLite-6.0.0."""
    return re.sub(r"[-_ ]v?\d+(\.\d+)+$", "", folder).lower()


def merge(data):
    """Combine source lists into entries with one or more sources each.

    Two listings are the same addon when the CurseForge catalog links them
    (directly or through a GitHub listing), or when they share both a
    normalized name and an addon folder. Name or folder alone isn't enough:
    forks often reuse the original's folder under another name.
    """
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a, b):
        parent[find(a)] = find(b)

    listed = {}
    for source in SOURCES:
        for entry in data.get(source, {}).get("entries", []):
            node = (source, entry["numericId"] if source == "curseforge" else entry["id"])
            listed[node] = (source, entry)
            find(node)
    for entry in data.get("curseforge", {}).get("entries", []):
        for other in entry["sameAs"]:
            union(("curseforge", entry["numericId"]), tuple(other))
    for group in data.get("curseforge", {}).get("links", []):
        for other in group[1:]:
            union(tuple(group[0]), tuple(other))
    # Heuristic matches only join listings from different sites, and never a
    # group that already has a listing from that site, so forks on one site
    # stay apart. Full names are tried before core names.
    kinds = {node: {node[0]} for node in listed}

    def join(a, b):
        ra, rb = find(a), find(b)
        if ra == rb or kinds.get(ra, set()) & kinds.get(rb, set()):
            return
        union(ra, rb)
        kinds[find(rb)] = kinds.get(ra, set()) | kinds.get(rb, set())

    for root in list(kinds):
        if find(root) != root:
            kinds.setdefault(find(root), set()).update(kinds.pop(root))
    for keys in (lambda e: {norm(e["name"])}, lambda e: name_keys(e["name"])):
        index = defaultdict(list)
        for node, (source, entry) in listed.items():
            for name in keys(entry):
                for folder in {folder_key(f) for f in entry["dirs"]}:
                    index[(name, folder)].append(node)
        for nodes in index.values():
            for i, a in enumerate(nodes):
                for b in nodes[i + 1:]:
                    if a[0] != b[0]:
                        join(a, b)

    groups = defaultdict(list)
    for node in list(parent):
        groups[find(node)].append(node)
    merged = []
    for nodes in groups.values():
        members = [listed[n] for n in nodes if n in listed]
        if not members:
            continue
        refs = [source_ref(source, entry) for source, entry in members]
        # Wago can't be used without a key, but its page is worth linking.
        refs += [{"source": "wago", "id": n[1], "url": f"https://addons.wago.io/addons/{n[1]}"} for n in nodes if n[0] == "wago"]
        refs.sort(key=lambda r: (PREFERENCE[r["source"]], -r.get("downloads", 0)))
        lead = max(members, key=lambda m: m[1].get("downloads", 0))[1]
        wowi = next((e for s, e in members if s == "wowinterface"), {})
        merged.append({
            "key": f"{refs[0]['source']}:{refs[0]['id']}",
            "name": lead["name"],
            "author": wowi.get("author", ""),
            "category": wowi.get("category", ""),
            "thumb": wowi.get("thumb", ""),
            "dirs": sorted({d for _, e in members for d in e["dirs"]}, key=str.lower),
            "sources": refs,
        })
    merged.sort(key=lambda e: -sum(r.get("downloads", 0) for r in e["sources"]))
    return merged


def source_ref(source, entry):
    ref = {"source": source, "id": entry["id"], "url": entry["url"], "updated": entry.get("updated", 0),
           "downloads": entry.get("downloads", 0)}
    if source == "curseforge":
        ref.update(flavours=entry["flavours"], numericId=entry["numericId"])
    else:
        ref["gameVersions"] = entry.get("gameVersions", [])
        ref["version"] = entry.get("version", "")
    if source == "wowinterface":
        ref.update(monthly=entry.get("monthly", 0), favorites=entry.get("favorites", 0))
    return ref


# --- Refreshing ----------------------------------------------------------------

def refresh(force=False, max_age=TTL):
    """Bring each source up to date, merge, and describe the result.

    A source that can't be reached keeps its last saved list and reports why.
    """
    status, data, changed = {}, {}, False
    for name in SOURCES:
        cached = read(cache_file(name))
        error = ""
        if force or not cached or time.time() - cached.get("fetchedAt", 0) >= max_age:
            try:
                fresh = dict(FETCHERS[name](), fetchedAt=int(time.time()))
                write(cache_file(name), fresh)
                cached, changed = fresh, True
            except Problem as problem:
                error = str(problem)
        data[name] = cached or {}
        status[name] = {"count": len((cached or {}).get("entries", [])), "fetchedAt": (cached or {}).get("fetchedAt", 0), "error": error}
    merged = read(merged_file())
    built_by = {"format": FORMAT, "sources": list(SOURCES)}
    if changed or not merged or merged.get("builtBy") != built_by:
        merged = {"builtBy": built_by, "entries": merge(data)}
        write(merged_file(), merged)
    if not merged["entries"]:
        raise Problem("No catalog could be loaded. " + " ".join(s["error"] for s in status.values() if s["error"]))
    return {"path": str(merged_file()), "count": len(merged["entries"]), "sources": status,
            "fetchedAt": max((s["fetchedAt"] for s in status.values()), default=0)}
