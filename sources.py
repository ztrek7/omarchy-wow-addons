"""Addon sources: the WoWInterface catalog, GitHub releases, and .zip archives.

WoWInterface publishes its catalog without an API key. CurseForge's own API
needs one, so single CurseForge projects are looked up through CFWidget, a
public read-only mirror, and downloaded from CurseForge's CDN. Wago needs a
key and isn't used.
"""
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import wowdir
from library import Problem

CACHE = Path(os.environ.get("XDG_CACHE_HOME") or wowdir.HOME / ".cache") / "wow-addons"
WOWI = "https://api.mmoui.com/v3/game/WOW"
USER_AGENT = "omarchy-wow-addons/0.1 (+https://github.com/ztrek7/omarchy-wow-addons)"
CATALOG_TTL = 6 * 3600
MAX_DOWNLOAD = 300 * 1024 * 1024
MAX_UNPACKED = 1024 * 1024 * 1024
MAX_FILES = 40000


def fetch(url, limit=64 * 1024 * 1024, accept="application/json"):
    if urllib.parse.urlsplit(url).scheme != "https":
        raise Problem("Only HTTPS downloads are allowed.")
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    token = os.environ.get("GITHUB_TOKEN")
    if token and urllib.parse.urlsplit(url).hostname == "api.github.com":
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            if urllib.parse.urlsplit(response.geturl()).scheme != "https":
                raise Problem("The download redirected away from HTTPS.")
            data = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        if error.code == 403 and "github" in url:
            raise Problem("GitHub's hourly limit for anonymous requests was reached. Try again later, or set GITHUB_TOKEN.")
        raise Problem(f"{urllib.parse.urlsplit(url).hostname} answered {error.code} {error.reason}.")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise Problem(f"Couldn't reach {urllib.parse.urlsplit(url).hostname}: {getattr(error, 'reason', error)}")
    if len(data) > limit:
        raise Problem("The download is larger than this app accepts.")
    return data


def fetch_json(url):
    try:
        return json.loads(fetch(url))
    except ValueError:
        raise Problem(f"{urllib.parse.urlsplit(url).hostname} returned something other than JSON.")


# --- WoWInterface -----------------------------------------------------------

def compact_catalog(files, categories):
    names = {c.get("UICATID"): c.get("UICATTitle", "") for c in categories}
    entries = []
    for item in files:
        try:
            uid = int(item["UID"])
        except (KeyError, TypeError, ValueError):
            continue
        compat = item.get("UICompatibility") or []
        thumbs = item.get("UIIMG_Thumbs") or []
        entries.append({
            "id": str(uid),
            "name": html.unescape(item.get("UIName") or "").strip(),
            "author": html.unescape(item.get("UIAuthorName") or ""),
            "category": names.get(item.get("UICATID"), "Other"),
            "version": item.get("UIVersion") or "",
            "updated": int(item.get("UIDate") or 0),
            "downloads": int(item.get("UIDownloadTotal") or 0),
            "monthly": int(item.get("UIDownloadMonthly") or 0),
            "favorites": int(item.get("UIFavoriteTotal") or 0),
            "gameVersions": sorted({c.get("version", "") for c in compat if c.get("version")}, key=version_key, reverse=True),
            "dirs": item.get("UIDir") or [],
            "thumb": thumbs[0] if thumbs else "",
            "url": item.get("UIFileInfoURL") or f"https://www.wowinterface.com/downloads/info{uid}",
        })
    return entries


def same_version(a, b):
    """Compare versions as authors write them: 'v1.2' and '1.2' match."""
    def norm(v):
        return str(v or "").strip().lower().removeprefix("v")
    return norm(a) == norm(b) and norm(a) != ""


def version_key(value):
    return [int(part) if part.isdigit() else 0 for part in value.split(".")]


def catalog_path():
    return CACHE / "wowinterface.json"


def load_catalog():
    try:
        return json.loads(catalog_path().read_text())
    except (OSError, ValueError):
        return None


def refresh_catalog(force=False, max_age=CATALOG_TTL):
    """Return catalog metadata, downloading a fresh copy when the cache is older than max_age seconds."""
    cached = load_catalog()
    if cached and not force and time.time() - cached.get("fetchedAt", 0) < max_age:
        return describe(cached, "")
    try:
        files = fetch_json(f"{WOWI}/filelist.json")
        categories = fetch_json(f"{WOWI}/categorylist.json")
        if not isinstance(files, list) or not isinstance(categories, list):
            raise Problem("WoWInterface returned an unexpected catalog format.")
    except Problem as error:
        if cached:
            return describe(cached, f"Showing the saved catalog. {error}")
        raise
    data = {"fetchedAt": int(time.time()), "entries": compact_catalog(files, categories)}
    CACHE.mkdir(parents=True, exist_ok=True)
    temporary = catalog_path().with_suffix(".tmp")
    temporary.write_text(json.dumps(data, separators=(",", ":")))
    temporary.replace(catalog_path())
    return describe(data, "")


def describe(data, message):
    return {"path": str(catalog_path()), "count": len(data["entries"]), "fetchedAt": data["fetchedAt"], "message": message}


BBCODE_LINK = re.compile(r"\[url=\"?([^\]\"]*)\"?\](.*?)\[/url\]", re.IGNORECASE | re.DOTALL)
BBCODE_MEDIA = re.compile(r"\[(img|video|youtube|media)[^\]]*\].*?\[/\1\]", re.IGNORECASE | re.DOTALL)
BBCODE_TAG = re.compile(r"\[/?[a-zA-Z*][^\]]{0,80}\]")


def bbcode_text(value):
    text = html.unescape(value or "").replace("\r\n", "\n")
    text = BBCODE_MEDIA.sub("", text)
    text = BBCODE_LINK.sub(lambda m: m.group(2) if m.group(2).strip() else m.group(1), text)
    text = re.sub(r"\[\*\]\s*", "\n  •  ", text)
    text = BBCODE_TAG.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:8000]


def wowi_details(addon_id):
    if not str(addon_id).isdigit():
        raise Problem("Unknown WoWInterface addon.")
    data = fetch_json(f"{WOWI}/filedetails/{addon_id}.json")
    item = data[0] if isinstance(data, list) and data else None
    if not isinstance(item, dict):
        raise Problem("WoWInterface has no details for that addon.")
    return {
        "id": str(addon_id),
        "name": html.unescape(item.get("UIName") or ""),
        "version": item.get("UIVersion") or "",
        "updated": int(item.get("UIDate") or 0),
        "description": bbcode_text(item.get("UIDescription")),
        "changelog": bbcode_text(item.get("UIChangeLog"))[:3000],
        "images": [u for u in (item.get("UIIMGs") or []) if isinstance(u, str) and u.startswith("https://")][:6],
        "download": item.get("UIDownload") or "",
        "md5": (item.get("UIMD5") or "").lower(),
        "fileName": item.get("UIFileName") or "",
        "author": html.unescape(item.get("UIAuthorName") or ""),
        "pending": item.get("UIPending") == "1",
    }


# --- GitHub releases --------------------------------------------------------

GITHUB_REPO = re.compile(r"^(?:https://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
FLAVOR_WORDS = {1: ("vanilla", "classic_era", "era", "classic"), 2: ("tbc", "bcc", "classic"), 3: ("wrath", "wotlk", "classic"),
                4: ("cata", "classic"), 5: ("mists", "mop", "classic")}


def github_repo(text):
    match = GITHUB_REPO.match((text or "").strip())
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def choose_asset(release, game, fetch_release_json=None):
    """Pick the packaged .zip for this game from a GitHub release, or None."""
    assets = [a for a in release.get("assets") or [] if a.get("browser_download_url", "").startswith("https://")]
    zips = [a for a in assets if a["name"].lower().endswith(".zip")]
    if not zips:
        return None
    manifest = next((a for a in assets if a["name"] == "release.json"), None)
    interface, major = game.get("interface"), game.get("major")
    if manifest and fetch_release_json:
        try:
            entries = fetch_release_json(manifest["browser_download_url"]).get("releases", [])
        except (Problem, AttributeError):
            entries = []
        ranked = []
        for entry in entries:
            interfaces = [m.get("interface") for m in entry.get("metadata", []) if isinstance(m, dict)]
            score = 0 if interface in interfaces else 1 if any(i and i // 10000 == major for i in interfaces) else 2
            ranked.append((score, bool(entry.get("nolib")), entry.get("filename")))
        for score, _, filename in sorted(ranked, key=lambda r: (r[0], r[1])):
            if score < 2:
                chosen = next((a for a in zips if a["name"] == filename), None)
                if chosen:
                    return chosen
    # Without release.json, go by the packager's file names: Name-v1.zip, Name-v1-classic.zip, ...
    ours = FLAVOR_WORDS.get(major, ("mainline", "retail"))
    flavored = {w for group in FLAVOR_WORDS.values() for w in group} | {"mainline", "retail"}
    full = [a for a in zips if "nolib" not in a["name"].lower()] or zips

    def rank(asset):
        name = asset["name"].lower()
        return (0 if any(w in name for w in ours) else 1 if not any(w in name for w in flavored) else 2, len(name))
    best = min(full, key=rank)
    return best if rank(best)[0] < 2 else None


def github_release(repo, game):
    data = fetch_json(f"https://api.github.com/repos/{repo}/releases?per_page=10")
    releases = [r for r in data if isinstance(r, dict) and not r.get("draft")] if isinstance(data, list) else []
    stable = [r for r in releases if not r.get("prerelease")] or releases
    if not stable:
        raise Problem(f"{repo} has no GitHub releases. Download a packaged .zip from the author and install that file.")
    release = stable[0]
    asset = choose_asset(release, game, fetch_json)
    if not asset:
        packaged = any(a.get("name", "").lower().endswith(".zip") for a in release.get("assets") or [])
        raise Problem(f"The latest {repo} release has no .zip for this game version." if packaged else
                      f"The latest {repo} release has no packaged .zip. The author may publish on another site; install a downloaded .zip instead.")
    return {
        "repo": repo,
        "tag": release.get("tag_name") or release.get("name") or "",
        "releaseId": release.get("id"),
        "published": release.get("published_at") or "",
        "asset": asset["name"],
        "download": asset["browser_download_url"],
        "url": release.get("html_url") or f"https://github.com/{repo}",
    }


# --- CurseForge (through CFWidget) -----------------------------------------

CURSEFORGE_PAGE = re.compile(r"^https://(?:www\.)?curseforge\.com/wow/addons/([a-z0-9][a-z0-9-]*)/?(?:[?#].*)?$", re.IGNORECASE)
CFWIDGET = "https://api.cfwidget.com"


def curseforge_project(text):
    match = CURSEFORGE_PAGE.match((text or "").strip())
    return match.group(1).lower() if match else None


def choose_curseforge_file(files, game):
    """Newest release .zip listing this client's version, else one for the same major version."""
    releases = [f for f in files if isinstance(f, dict) and f.get("type") == "release" and isinstance(f.get("id"), int)
                and str(f.get("name", "")).lower().endswith(".zip")]
    version, major = game.get("version"), str(game.get("major"))
    exact = [f for f in releases if version and version in (f.get("versions") or [])]
    related = [f for f in releases if any(str(v).split(".")[0] == major for v in f.get("versions") or [])]
    pool = exact or related
    return max(pool, key=lambda f: f.get("uploaded_at") or "") if pool else None


def curseforge_release(project, game):
    project = str(project).lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", project):
        raise Problem("Unknown CurseForge project.")
    path = project if project.isdigit() else f"wow/addons/{project}"
    try:
        data = fetch_json(f"{CFWIDGET}/{path}")
    except Problem as error:
        raise Problem(f"Couldn't look up CurseForge project {project}: {error}")
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list):
        raise Problem("CFWidget is still gathering that CurseForge project. Try again in a minute.")
    title = data.get("title") or project
    chosen = choose_curseforge_file(files, game)
    if not chosen:
        raise Problem(f"CurseForge has no release of {title} for this game version.")
    page = (data.get("urls") or {}).get("curseforge") or ""
    slug = CURSEFORGE_PAGE.match(page)
    file_id = chosen["id"]
    return {
        "project": slug.group(1).lower() if slug else project,
        "title": title,
        "fileId": file_id,
        "version": chosen.get("display") or chosen["name"],
        "size": chosen.get("filesize") or 0,
        # CurseForge's CDN path: files/<id without last 3 digits>/<last 3 digits, unpadded>/<name>.
        "download": f"https://edge.forgecdn.net/files/{file_id // 1000}/{file_id % 1000}/{urllib.parse.quote(chosen['name'])}",
        "url": page or f"https://www.curseforge.com/wow/addons/{project}",
    }


# --- Archives ---------------------------------------------------------------

def download(url, destination, md5="", size=0):
    data = fetch(url, limit=MAX_DOWNLOAD, accept="application/octet-stream, application/zip, */*")
    if md5 and hashlib.md5(data).hexdigest() != md5.lower():
        raise Problem("The download didn't match WoWInterface's checksum. Nothing was installed.")
    if size and len(data) != size:
        raise Problem("The download isn't the size CurseForge lists. Nothing was installed.")
    Path(destination).write_bytes(data)
    return destination


def addon_roots(names):
    """Find addon folders inside an archive: directories holding a TOC named after them."""
    tocs = [PurePosixPath(n) for n in names if n.lower().endswith(".toc") and len(PurePosixPath(n).parts) >= 2]
    found = {}
    for toc in tocs:
        folder = toc.parent
        if wowdir.toc_suffix(folder.name, Path(toc.name)) is not False:
            found.setdefault(len(folder.parts), set()).add(folder)
    if found:
        # Addons sit side by side at one depth; deeper matches are bundled sub-folders.
        depth = min(found)
        return {folder.name: folder for folder in found[depth]}
    # A GitHub source archive: repo-sha/Name.toc. Name the folder after its TOC.
    shallow = [t for t in tocs if len(t.parts) == 2]
    stems = {re.sub(r"[-_](mainline|classic|vanilla|tbc|bcc|wrath|wotlkc|cata|mists)$", "", t.stem, flags=re.I) for t in shallow}
    if len(stems) == 1:
        return {stems.pop(): shallow[0].parent}
    return {}


def extract_addons(archive, workspace):
    """Safely unpack only the addon folders from archive into workspace. Returns {name: path}."""
    try:
        bundle = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError):
        raise Problem("That file isn't a readable .zip archive.")
    with bundle:
        members = bundle.infolist()
        if len(members) > MAX_FILES or sum(m.file_size for m in members) > MAX_UNPACKED:
            raise Problem("The archive is too large to be an addon.")
        for member in members:
            path = PurePosixPath(member.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise Problem("The archive contains unsafe paths or links. Nothing was installed.")
        roots = addon_roots([m.filename.replace("\\", "/") for m in members])
        if not roots:
            raise Problem("No addon folders were found in the archive. An addon folder contains a .toc file named after it.")
        for name in roots:
            if not re.fullmatch(r"[^/\\:*?\"<>|]{1,120}", name) or name.startswith("."):
                raise Problem(f"The archive contains an invalid addon folder name: {name}")
        workspace = Path(workspace)
        placed = {}
        for name, root in roots.items():
            target = workspace / name
            target.mkdir()
            placed[name] = target
            for member in members:
                path = PurePosixPath(member.filename.replace("\\", "/"))
                try:
                    relative = path.relative_to(root)
                except ValueError:
                    continue
                if member.is_dir() or not relative.parts:
                    continue
                destination = target.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, open(destination, "wb") as out:
                    shutil.copyfileobj(source, out)
        return placed
