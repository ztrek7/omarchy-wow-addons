"""Addon sources: CurseForge and WoWInterface, plus .zip files the user downloaded.

Only these two moderated sites are used, so nothing installs from arbitrary
repositories or links. Neither needs an API key: WoWInterface publishes an
open API, and CurseForge projects are read from CFWidget, a public mirror of
CurseForge's data, with files downloaded from CurseForge's own CDN.
"""
import datetime
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
import zlib

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
    # Ask for compressed JSON: CurseForge project data shrinks about tenfold.
    headers = {"User-Agent": USER_AGENT, "Accept": accept, "Accept-Encoding": "gzip"}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            if urllib.parse.urlsplit(response.geturl()).scheme != "https":
                raise Problem("The download redirected away from HTTPS.")
            data = response.read(limit + 1)
            if response.headers.get("Content-Encoding", "").lower() == "gzip" and len(data) <= limit:
                try:
                    # Cap the unpacked size too, so a small response can't expand without bound.
                    data = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(data, limit + 1)
                except zlib.error:
                    raise Problem(f"{urllib.parse.urlsplit(url).hostname} sent a damaged response.")
    except urllib.error.HTTPError as error:
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

def compact_wowinterface(files, categories):
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


HTML_BREAK = re.compile(r"<\s*(br|/p|/div|/h[1-6]|/tr)\b[^>]*>", re.IGNORECASE)
HTML_ITEM = re.compile(r"<\s*li\b[^>]*>", re.IGNORECASE)
HTML_TAG = re.compile(r"<[^>]+>")


def html_text(value):
    text = HTML_ITEM.sub("\n  •  ", HTML_BREAK.sub("\n", value or ""))
    text = html.unescape(HTML_TAG.sub("", text))
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n\s*\n(  •  )", r"\n\1", text)  # List items wrapped in paragraphs.
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:8000]


# --- Details for Browse ---------------------------------------------------------

def details(source, ident):
    """A description, screenshots, and credits for the Browse details view."""
    if source == "wowinterface":
        info = wowi_details(ident)
        return {"source": source, "id": str(ident), "name": info["name"], "author": info["author"], "description": info["description"],
                "changelog": info["changelog"], "images": info["images"], "version": info["version"]}
    if source == "curseforge":
        data = cfwidget(ident)
        members = [m.get("username") for m in data.get("members") or [] if isinstance(m, dict) and m.get("username")]
        thumbnail = data.get("thumbnail")
        return {"source": source, "id": str(ident), "name": data.get("title") or str(ident), "author": ", ".join(members[:3]),
                "description": html_text(data.get("description")) or data.get("summary") or "", "changelog": "",
                "images": [thumbnail] if isinstance(thumbnail, str) and thumbnail.startswith("https://") else [],
                "version": ((data.get("download") or {}).get("display") or ""), "categories": data.get("categories") or []}
    raise Problem("Details aren't available for that source.")


# --- CurseForge (through CFWidget) -----------------------------------------

CURSEFORGE_PAGE = re.compile(r"^https://(?:www\.)?curseforge\.com/wow/addons/([a-z0-9][a-z0-9-]*)/?(?:[?#].*)?$", re.IGNORECASE)
CFWIDGET = "https://api.cfwidget.com"


WOWI_PAGE = re.compile(r"^https://(?:www\.)?wowinterface\.com/downloads/(?:info|download)(\d+)", re.IGNORECASE)


def wowinterface_page(text):
    match = WOWI_PAGE.match((text or "").strip())
    return match.group(1) if match else None


def curseforge_project(text):
    match = CURSEFORGE_PAGE.match((text or "").strip())
    return match.group(1).lower() if match else None


def choose_curseforge_file(files, game):
    """Newest release .zip for this client: its exact version, else the same game (e.g. any WoW Forever
    patch), else the same major version for addons not listed for this game at all."""
    releases = [f for f in files if isinstance(f, dict) and f.get("type") == "release" and isinstance(f.get("id"), int)
                and str(f.get("name", "")).lower().endswith(".zip")]
    version, major, flavour = game.get("version"), str(game.get("major")), game.get("flavour")
    exact = [f for f in releases if version and version in (f.get("versions") or [])]
    same_game = [f for f in releases if flavour and any(wowdir.game_flavour(str(v)) == flavour for v in f.get("versions") or [])]
    related = [f for f in releases if any(str(v).split(".")[0] == major for v in f.get("versions") or [])]
    pool = exact or same_game or related
    return max(pool, key=lambda f: f.get("uploaded_at") or "") if pool else None


def iso_ms(value):
    try:
        return int(datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return 0


def cfwidget(project):
    project = str(project).lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", project):
        raise Problem("Unknown CurseForge project.")
    path = project if project.isdigit() else f"wow/addons/{project}"
    try:
        data = fetch_json(f"{CFWIDGET}/{path}")
    except Problem as error:
        raise Problem(f"Couldn't look up CurseForge project {project}: {error}")
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise Problem("CFWidget is still gathering that CurseForge project. Try again in a minute.")
    return data


STALE_AFTER = 3 * 86400 * 1000


def curseforge_release(project, game, listed_updated=0):
    """The file to install from a CurseForge project.

    listed_updated is when the catalog last saw the project change. CFWidget's
    copy of a few projects stops updating; if its newest file is well behind
    that date, refuse rather than install an old version.
    """
    project = str(project).lower()
    data = cfwidget(project)
    files = data["files"]
    title = data.get("title") or project
    newest = max((iso_ms(f.get("uploaded_at")) for f in files if isinstance(f, dict)), default=0)
    if listed_updated and newest < listed_updated - STALE_AFTER:
        seen = time.strftime("%B %-d, %Y", time.localtime(newest / 1000)) if newest else "never"
        raise Problem(f"CFWidget's copy of {title} is out of date (its newest file is from {seen}), so it can't be installed from CurseForge right now.")
    chosen = choose_curseforge_file(files, game)
    if not chosen:
        raise Problem(f"CurseForge has no release of {title} for this game version.")
    page = (data.get("urls") or {}).get("curseforge") or ""
    slug = CURSEFORGE_PAGE.match(page)
    file_id = chosen["id"]
    return {
        "project": slug.group(1).lower() if slug else project,
        "projectId": str(data.get("id") or ""),
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
