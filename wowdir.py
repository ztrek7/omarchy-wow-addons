"""Find World of Warcraft installs and read addon metadata. Never writes to the game folder."""
import json
import os
from pathlib import Path
import re
import tempfile

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

# The TOC files each game looks for before the plain Name.toc, in order
# (https://warcraft.wiki.gg/wiki/TOC_format). WoW Forever's code name is Camelot, and it
# belongs to the Mainline family; Titan Reforged is a Wrath game. _Mainline and _Classic
# rank below the game's own suffix. -BCC and -WOTLKC are legacy names. Wrath Classic (3.4)
# predates _Classic loading outside Classic Era, so it doesn't read it.
TOC_SUFFIXES = {
    "mainline": ("Standard", "Mainline"), "vanilla_classic": ("Vanilla", "Classic"), "forever_classic": ("Camelot", "Mainline"),
    "tbc_classic": ("TBC", "BCC", "Classic"), "wrath_classic": ("Wrath", "WOTLKC"), "titan_classic": ("Wrath", "WOTLKC", "Classic"),
    "cata_classic": ("Cata", "Classic"), "mists_classic": ("Mists", "Classic"),
}
# Suffixes a game only reads from a patch on (Standard came in 12.1.5; TBC Anniversary 2.5.5
# started reading _Classic) or only before one (2.5.5 dropped -BCC), per the wiki's patch changes.
SUFFIX_FROM = {("mainline", "Standard"): (12, 1, 5), ("tbc_classic", "Classic"): (2, 5, 5)}
SUFFIX_UNTIL = {("tbc_classic", "BCC"): (2, 5, 5)}
# Every suffix a client reads, including modes this app doesn't manage.
ALL_TOC_SUFFIXES = {suffix.lower() for suffixes in TOC_SUFFIXES.values() for suffix in suffixes} | {"plunderstorm", "wowlabs", "wowhack"}
# Every game type a client recognizes in ## AllowLoadGameType. A list naming none of them is ignored.
KNOWN_GAME_TYPES = {"standard", "mists", "cata", "wrath", "tbc", "camelot", "vanilla", "plunderstorm", "wowlabs", "wowhack",
                    "mainline", "classic"}
# The names each game answers to in ## AllowLoadGameType: its own game type and its family.
GAME_TYPES = {
    "mainline": {"mainline", "standard"}, "vanilla_classic": {"vanilla", "classic"}, "forever_classic": {"camelot", "mainline"},
    "tbc_classic": {"tbc", "classic"}, "wrath_classic": {"wrath", "classic"}, "titan_classic": {"wrath", "classic"},
    "cata_classic": {"cata", "classic"}, "mists_classic": {"mists", "classic"},
}
CURSEFORGE_URL = re.compile(r"curseforge\.com/wow/addons/([a-z0-9][a-z0-9-]*)", re.IGNORECASE)
WOWI_URL = re.compile(r"wowinterface\.com/downloads/(?:info|download|fileinfo\.php\?id=)(\d+)", re.IGNORECASE)
ESCAPES = re.compile(r"\|c(?:[0-9a-fA-F]{8}|n[^:|]*:)|\|r|\|T[^|]*\|t|\|A[^|]*\|a")
LINE_BREAK = re.compile(r"\s*\|n\s*")


def load_config():
    try:
        data = json.loads(CONFIG.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_atomic(path, text):
    """Replace a file in one step. Each writer gets its own temporary file, so two helpers
    running at once (a catalog load and an update check) can't trip over each other."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w") as out:
            out.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def save_config(data):
    write_atomic(CONFIG, json.dumps(data, indent=2) + "\n")


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


def game_flavour(version, key=""):
    """The catalog name for a client line: 1.60.1 -> forever_classic, 1.15.7 -> vanilla_classic."""
    parts = [int(p) if p.isdigit() else 0 for p in (version or "").split(".")[:2]] + [0, 0]
    major, minor = parts[0], parts[1]
    if not major:
        return {"_retail_": "mainline", "_ptr_": "mainline", "_xptr_": "mainline", "_beta_": "mainline",
                "_classic_era_": "vanilla_classic", "_classic_era_ptr_": "vanilla_classic"}.get(key)
    if major >= 6:
        return "mainline"
    if major == 1:
        return "forever_classic" if minor >= 60 else "vanilla_classic"
    if major == 3:
        return "titan_classic" if minor >= 80 else "wrath_classic"
    return {2: "tbc_classic", 4: "cata_classic", 5: "mists_classic"}[major]


GAME_NAMES = {
    "mainline": "WoW Retail", "vanilla_classic": "WoW Classic Era", "forever_classic": "WoW Forever",
    "tbc_classic": "WoW Burning Crusade Classic", "wrath_classic": "WoW Wrath Classic", "titan_classic": "WoW Titan Reforged",
    "cata_classic": "WoW Cataclysm Classic", "mists_classic": "WoW Mists of Pandaria Classic",
}


def flavor_name(key, flavour=None):
    """_classic_beta_ running 1.60.1 -> "WoW Forever Beta"; _retail_ -> "WoW Retail"."""
    base = GAME_NAMES.get(flavour) or "WoW " + " ".join(w.capitalize() for w in key.strip("_").split("_") if w not in ("ptr", "xptr", "beta"))
    words = key.strip("_").split("_")
    branch = " Beta" if "beta" in words else " PTR" if "ptr" in words or "xptr" in words else ""
    return base + branch


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
        flavour = game_flavour(version, child.name)
        result.append({
            "key": child.name,
            "name": flavor_name(child.name, flavour),
            "path": str(child),
            "version": ".".join(version.split(".")[:3]),
            "interface": interface,
            "major": interface // 10000 if interface else None,
            "flavour": flavour,
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
    """Strip WoW's color, texture, and line-break codes from TOC text."""
    return LINE_BREAK.sub(" ", ESCAPES.sub("", text or "")).strip()


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


def toc_suffixes(game):
    """The suffixes this client reads, best first. An unknown version counts as the newest client."""
    flavour = (game or {}).get("flavour")
    number = tuple(int(n) for n in re.findall(r"\d+", str((game or {}).get("version") or ""))[:3])
    def reads(suffix):
        start, end = SUFFIX_FROM.get((flavour, suffix)), SUFFIX_UNTIL.get((flavour, suffix))
        if not number:
            return not end  # The newest client: it reads added suffixes, not retired ones.
        return (not start or number >= start) and (not end or number < end)
    return tuple(s for s in TOC_SUFFIXES.get(flavour, ()) if reads(s))


def pick_toc(folder, game):
    """The TOC this game would load, and whether it loads the folder at all."""
    tocs = {}
    for toc in Path(folder).glob("*.toc"):
        suffix = toc_suffix(Path(folder).name, toc)
        if suffix is not False:
            tocs[(suffix or "").lower()] = toc
    if not tocs:
        return None, False
    for suffix in toc_suffixes(game):
        if suffix.lower() in tocs:
            return tocs[suffix.lower()], True
    if "" in tocs:
        return tocs[""], True
    # Only other flavors' TOCs: the client skips this folder, but show its metadata anyway.
    return sorted(tocs.values())[0], False


def update_links(fields):
    """Where an addon says it's published on WoWInterface or CurseForge, from packager fields or its website."""
    website = fields.get("x-website", "")
    links = []
    wowi = fields.get("x-wowi-id", "") or (WOWI_URL.search(website) or [None, ""])[1]
    if wowi.isdigit():
        links.append({"source": "wowinterface", "id": wowi})
    curse = fields.get("x-curse-project-id", "")
    slug = CURSEFORGE_URL.search(website)
    if curse.isdigit() or slug:
        links.append({"source": "curseforge", "id": curse if curse.isdigit() else slug.group(1).lower()})
    return links


def split_list(value):
    return [item.strip() for item in re.split(r"[,\s]+", value or "") if item.strip()]


def read_addon(folder, game):
    folder = Path(folder)
    flavour = game.get("flavour") if game else None
    toc, loadable = pick_toc(folder, game)
    fields = parse_toc(toc) if toc else {}
    # "## AllowLoadGameType: standard" marks a part that only loads in those games, like
    # BigWigs' Retail raid modules. The game skips it here on purpose; it isn't out of date.
    allowed = {t.lower() for t in split_list(fields.get("allowloadgametype"))} & KNOWN_GAME_TYPES
    if allowed and flavour in GAME_TYPES and not allowed & GAME_TYPES[flavour]:
        loadable = False
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
