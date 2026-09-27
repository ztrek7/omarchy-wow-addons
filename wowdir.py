"""Find World of Warcraft installs and read addon metadata. Never writes."""
import json
import os
from pathlib import Path
import re

HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "wow-addons" / "config.json"

# Where Wine-based launchers usually put the Battle.net install, relative to $HOME.
CANDIDATE_GLOBS = (
    "Games/*/drive_c/Program Files (x86)/World of Warcraft",
    "Games/*/drive_c/Program Files/World of Warcraft",
    "Games/*/*/drive_c/Program Files (x86)/World of Warcraft",
    ".wine/drive_c/Program Files (x86)/World of Warcraft",
    ".wine/drive_c/Program Files/World of Warcraft",
    ".local/share/wineprefixes/*/drive_c/Program Files (x86)/World of Warcraft",
    ".local/share/Steam/steamapps/compatdata/*/pfx/drive_c/Program Files (x86)/World of Warcraft",
    ".steam/steam/steamapps/compatdata/*/pfx/drive_c/Program Files (x86)/World of Warcraft",
)

FLAVOR_DIR = re.compile(r"^_[a-z0-9]+(?:_[a-z0-9]+)*_$")
DISABLED_DIR = "AddOns.disabled"

# Flavor-specific TOC suffixes the client prefers over the plain .toc, by game major version.
TOC_SUFFIXES = {1: ("Vanilla", "Classic"), 2: ("TBC", "BCC", "Classic"), 3: ("Wrath", "WOTLKC", "Classic"),
                4: ("Cata", "Classic"), 5: ("Mists", "Classic")}
ALL_TOC_SUFFIXES = {"mainline", "classic", "vanilla", "tbc", "bcc", "wrath", "wotlkc", "cata", "mists", "standard"}
CURSEFORGE_URL = re.compile(r"curseforge\.com/wow/addons/([a-z0-9][a-z0-9-]*)", re.IGNORECASE)
WOWI_URL = re.compile(r"wowinterface\.com/downloads/(?:info|download|fileinfo\.php\?id=)(\d+)", re.IGNORECASE)
GITHUB_URL = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?(?:[/#?]|$)", re.IGNORECASE)
ESCAPES = re.compile(r"\|c(?:[0-9a-fA-F]{8}|n[^:|]*:)|\|r|\|T[^|]*\|t|\|A[^|]*\|a")


def load_config():
    try:
        data = json.loads(CONFIG.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(data):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(CONFIG)


def candidate_roots(home=None):
    home = home or HOME
    found, seen = [], set()
    for pattern in CANDIDATE_GLOBS:
        for path in sorted(home.glob(pattern)):
            # Proton prefixes link pfx -> ., so one install matches several patterns.
            real = path.resolve()
            if path.is_dir() and real not in seen:
                seen.add(real)
                found.append(path)
    return found


def read_build_info(root):
    """Map product code to client version from the launcher's .build.info."""
    try:
        lines = (Path(root) / ".build.info").read_text(errors="replace").splitlines()
    except OSError:
        return {}
    if not lines:
        return {}
    header = [column.split("!")[0] for column in lines[0].split("|")]
    versions = {}
    for line in lines[1:]:
        row = dict(zip(header, line.split("|")))
        if row.get("Product") and row.get("Version"):
            versions[row["Product"]] = row["Version"]
    return versions


def product_dir(product):
    """wow_classic_era -> _classic_era_, wow -> _retail_, wowt -> _ptr_."""
    special = {"wow": "_retail_", "wowt": "_ptr_", "wowxptr": "_xptr_", "wowz": "_ptr2_"}
    if product in special:
        return special[product]
    return "_" + product.removeprefix("wow_") + "_" if product.startswith("wow_") else None


def interface_number(version):
    """Client 1.60.1.70009 -> 16001, the value addons list in ## Interface."""
    parts = (version or "").split(".")
    try:
        major, minor, patch = (int(parts[i]) if i < len(parts) else 0 for i in range(3))
    except ValueError:
        return None
    return major * 10000 + minor * 100 + patch


def flavor_name(key):
    return " ".join(word.upper() if word in ("ptr", "xptr") else word.capitalize() for word in key.strip("_").split("_"))


def flavors(root):
    root = Path(root)
    versions = {product_dir(product): version for product, version in read_build_info(root).items()}
    result = []
    try:
        children = sorted(root.iterdir())
    except OSError:
        return result
    for child in children:
        if not child.is_dir() or not FLAVOR_DIR.match(child.name):
            continue
        if not (child / "Interface").is_dir() and not (child / "WTF").is_dir() and not any(child.glob("Wow*.exe")):
            continue
        version = versions.get(child.name, "")
        interface = interface_number(version)
        result.append({
            "key": child.name,
            "name": flavor_name(child.name),
            "path": str(child),
            "version": ".".join(version.split(".")[:3]),
            "interface": interface,
            "major": interface // 10000 if interface else None,
            "addons": str(child / "Interface" / "AddOns"),
        })
    return result


def resolve(config=None, home=None):
    """Pick the configured install and flavor, falling back to the first detected ones."""
    config = load_config() if config is None else config
    roots = candidate_roots(home)
    configured = Path(config["root"]).expanduser() if config.get("root") else None
    root = configured if configured and configured.is_dir() else (roots[0] if roots else None)
    if configured and configured not in roots and configured.is_dir():
        roots.insert(0, configured)
    available = flavors(root) if root else []
    flavor = next((f for f in available if f["key"] == config.get("flavor")), None)
    if not flavor and available:
        # Prefer a flavor that already has addons, then one with a known version.
        flavor = sorted(available, key=lambda f: (not Path(f["addons"]).is_dir(), not f["version"]))[0]
    return {
        "roots": [str(r) for r in roots],
        "root": str(root) if root else "",
        "configuredRoot": config.get("root", ""),
        "flavors": available,
        "flavor": flavor,
    }


def clean(text):
    return ESCAPES.sub("", text or "").strip()


def parse_toc(path):
    fields = {}
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            for line in handle:
                if not line.startswith("##"):
                    continue
                key, sep, value = line[2:].partition(":")
                if sep:
                    fields.setdefault(key.strip().lower(), value.strip())
    except OSError:
        pass
    return fields


def toc_suffix(folder, toc):
    """None for Folder.toc, 'Vanilla' for Folder_Vanilla.toc, False if the file isn't this folder's TOC."""
    stem = toc.stem
    if stem.lower() == folder.lower():
        return None
    for separator in ("_", "-"):
        prefix = folder + separator
        if stem.lower().startswith(prefix.lower()) and stem[len(prefix):].lower() in ALL_TOC_SUFFIXES:
            return stem[len(prefix):]
    return False


def pick_toc(folder, major):
    """Return the TOC the client would load for this game version, plus whether any TOC exists."""
    tocs = {}
    for toc in Path(folder).glob("*.toc"):
        suffix = toc_suffix(Path(folder).name, toc)
        if suffix is not False:
            tocs[(suffix or "").lower()] = toc
    if not tocs:
        return None, False
    preferred = TOC_SUFFIXES.get(major, ("Mainline",)) if major else ()
    for suffix in preferred:
        if suffix.lower() in tocs:
            return tocs[suffix.lower()], True
    if "" in tocs:
        return tocs[""], True
    # Only other flavors' TOCs: the client skips this folder, but show its metadata anyway.
    return sorted(tocs.values())[0], False


def update_links(fields):
    """Where an addon says it's published, from packager fields or its website. Preferred source first."""
    website = fields.get("x-website", "")
    links = []
    wowi = fields.get("x-wowi-id", "") or (WOWI_URL.search(website) or [None, ""])[1]
    if wowi.isdigit():
        links.append({"source": "wowinterface", "id": wowi})
    curse = fields.get("x-curse-project-id", "")
    slug = CURSEFORGE_URL.search(website)
    if curse.isdigit() or slug:
        links.append({"source": "curseforge", "id": curse if curse.isdigit() else slug.group(1).lower()})
    repo = GITHUB_URL.search(website)
    if repo:
        links.append({"source": "github", "id": repo.group(1)})
    return links


def split_list(value):
    return [item.strip() for item in re.split(r"[,\s]+", value or "") if item.strip()]


def read_addon(folder, game):
    folder = Path(folder)
    toc, loadable = pick_toc(folder, game.get("major") if game else None)
    fields = parse_toc(toc) if toc else {}
    interfaces = []
    for item in split_list(fields.get("interface")):
        if item.isdigit():
            interfaces.append(int(item))
    title = clean(fields.get("title")) or folder.name
    dependencies = split_list(fields.get("dependencies") or fields.get("requireddeps") or fields.get("dep") or "")
    for key, value in fields.items():
        if key.startswith("dep") and key not in ("dependencies",) and key[3:].isdigit():
            dependencies += split_list(value)
    target = game.get("interface") if game else None
    return {
        "folder": folder.name,
        "title": title,
        "notes": clean(fields.get("notes")),
        "version": clean(fields.get("version")),
        "author": clean(fields.get("author")),
        "website": fields.get("x-website", ""),
        "category": clean(fields.get("category") or fields.get("x-category")),
        "group": fields.get("group", ""),
        "dependencies": dependencies,
        "savedVariables": split_list(fields.get("savedvariables")) + split_list(fields.get("savedvariablespercharacter")),
        "interfaces": interfaces,
        "hasToc": toc is not None,
        # A folder without a TOC for this client, or whose TOC doesn't list this client's interface.
        "loadable": loadable,
        "outOfDate": bool(loadable and target and interfaces and target not in interfaces),
        "loadOnDemand": fields.get("loadondemand", "") == "1",
        "links": update_links(fields),
    }


def game_running():
    """True when a WoW client (Wow.exe, WowClassic.exe, WowB.exe, ...) is running under Wine."""
    pattern = re.compile(rb"(?:^|[\\/])wow[a-z0-9-]*\.exe$", re.IGNORECASE)
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv0 = (proc / "cmdline").read_bytes().split(b"\0", 1)[0]
        except OSError:
            continue
        if pattern.search(argv0):
            return True
    return False
