"""Nimble Notes storage. Everything is a plain file:

  notes/<Name>/            one folder per entry, named after the entry so it can be found by eye. It holds:
    <Name>.txt             the notes. Open text comes first (a line ticked off with Ctrl+D starts with
                           "[x] "). Each finished revision follows under a line like
                           "--- Revision 3 | 10-10-26 20:31 ---", newest first. A revision reopened with
                           Undo has "| open" before the closing dashes. Pictures and videos that belong
                           to a block are listed at its end, one "[image] file name" or
                           "[video] file name" line each.
    ideas.txt              the Ideas pane, when anything is in it
  images/<Name>/           a copy of every picture and video added to that entry's notes. Taking one off
                           a note only drops its line from the notes file: the file here is never deleted
                           by the app.
  data/apps.json           the sections and the list, in order: name, section, stage, family, folder,
                           launch file, notes file name, TL;DR
  data/removed/            removed entries (their notes folder), kept so Remove can be undone
  data/state.json          window size, pane sizes, last entry, cursor places, sort choices, text size, model file
"""

import filecmp
import json
import os
import re
import shutil
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("NIMBLE_NOTES_DATA") or os.path.join(APP_DIR, "data")
NOTES_DIR = os.path.join(os.path.dirname(os.path.normpath(DATA_DIR)), "notes")
IMAGES_DIR = os.path.join(os.path.dirname(os.path.normpath(DATA_DIR)), "images")  # pictures and videos, by entry
OLD_NOTES_DIR = os.path.join(DATA_DIR, "notes")  # where notes lived up to 1.2, named by internal id
REMOVED_DIR = os.path.join(DATA_DIR, "removed")
APPS_PATH = os.path.join(DATA_DIR, "apps.json")
STATE_PATH = os.path.join(DATA_DIR, "state.json")
REMOVED_PATH = os.path.join(REMOVED_DIR, "removed.json")

# the categories a new list starts with. Incoming holds High Priority, which holds Medium, which holds Low,
# to show that categories nest. Incoming is pinned to the top.
DEFAULT_SECTIONS = [
    {"key": "incoming", "title": "Incoming", "parent": "", "pinned": True},
    {"key": "high", "title": "High Priority", "parent": "incoming"},
    {"key": "medium", "title": "Medium", "parent": "high"},
    {"key": "low", "title": "Low", "parent": "medium"},
    {"key": "work", "title": "Work"},
    {"key": "projects", "title": "Projects"},
    {"key": "calls", "title": "Calls"},
    {"key": "team", "title": "Team"},
    {"key": "vibe", "title": "Vibe Coded"},
    {"key": "other", "title": "Other"},
]
OLD_INTO_VIBE = {"apps", "nodes", "docs"}  # 1.x categories whose notes went to Vibe Coded in 2.0

# key, label, what it means (shown as the tooltip)
STAGES = [
    ("finished", "Finished", "Full build: installer, launcher and docs are in place."),
    ("working", "Working", "Runs and does its job, but it is an older or rougher build."),
    ("early", "Early", "Started, alpha, or only partly built."),
    ("replaced", "Replaced", "An older revision. A newer app does this job now."),
    ("empty", "Empty", "The folder has no app in it yet."),
    ("thirdparty", "Not mine", "A third-party tool that is kept here."),
]
STAGE_KEYS = [s[0] for s in STAGES]
STAGE_LABEL = {s[0]: s[1] for s in STAGES}
STAGE_HELP = {s[0]: s[2] for s in STAGES}

LAUNCH_EXT = (".bat", ".cmd")
NOT_A_LAUNCHER = re.compile(r"^(un)?install|^setup|^update|^upgrade|^stop|^kill|^report|^build|^test|^render|^clean",
                            re.I)
NOT_APP_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git", ".claude", "models", "output", "outputs",
                "data", "logs", "cache", "backups", "static", "templates", "assets", "llm", "locales", "resources"}

# "last code change" looks at these file types, at the top of the folder and one folder down
CODE_EXT = (".py", ".pyw", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css", ".bat", ".cmd", ".ps1",
            ".md", ".toml", ".yaml", ".yml", ".ipynb")
NOT_CODE_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git", ".claude", "models", "output", "outputs",
                 "data", "logs", "cache", "backups", "llm", "hf_cache", "locales", "resources", "datasets", "grabs",
                 "work", "incoming", "chats", "notes"}

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".jfif", ".webp", ".bmp", ".gif", ".tif", ".tiff")
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".wmv")
MEDIA_EXT = IMAGE_EXT + VIDEO_EXT

BAD_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}


def expand_dir(p):
    return os.path.expanduser(p) if isinstance(p, str) and p[:1] == "~" else p


def contract_dir(p):
    if not isinstance(p, str) or not p or not os.path.isabs(p):
        return p
    home = os.path.expanduser("~")
    ap = os.path.normpath(p)
    return "~" + ap[len(home):].replace("\\", "/") if ap.lower().startswith(home.lower()) else p


def _plain(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _natural(name):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name.lower())]


def safe_file_name(name):
    """An entry name made safe to use as a Windows file name (without the .txt)."""
    s = re.sub(r"\s+", " ", BAD_FILE_CHARS.sub("_", name)).strip()[:80].rstrip(". ") or "note"
    return "_" + s if s.lower() in RESERVED_NAMES else s


def find_launcher(folder, look_down=True):
    """Best guess at the file that starts the app living in this folder, or ''.

    Tried in this order, skipping installers, updaters and the like:
      launch_<name>.bat, launch.bat, run.bat / run_<name>.bat, start*.bat (.cmd counts too),
      a .bat named after the folder, the only .bat there is, an .exe named after the folder,
      then the same launch / run / start names one folder down, newest version folder first."""
    try:
        entries = sorted(os.scandir(folder), key=lambda d: d.name.lower())
        files = [d.name for d in entries if d.is_file()]
    except OSError:
        return ""
    bats = [n for n in files if n.lower().endswith(LAUNCH_EXT) and not NOT_A_LAUNCHER.match(n)]
    base = _plain(os.path.basename(os.path.normpath(folder)))

    def first(test):
        hits = sorted((n for n in bats if test(os.path.splitext(n)[0].lower())),
                      key=lambda n: (_plain(os.path.splitext(n)[0])[-len(base):] != base, n.lower()))
        return hits[0] if hits else ""

    pick = (first(lambda s: s.startswith(("launch_", "launch-")))
            or first(lambda s: s == "launch")
            or first(lambda s: s == "run" or s.startswith(("run_", "run-")))
            or first(lambda s: s.startswith("start")))
    if not pick and look_down:
        pick = first(lambda s: len(_plain(s)) >= 3 and (_plain(s) in base or base in _plain(s)))
        if not pick and len(bats) == 1:
            pick = bats[0]
        if not pick:
            exes = [n for n in files if n.lower().endswith(".exe") and _plain(os.path.splitext(n)[0]) == base]
            pick = exes[0] if exes else ""
    if pick:
        return os.path.join(folder, pick)
    if look_down:
        subs = [d for d in entries if d.is_dir() and d.name.lower() not in NOT_APP_DIRS
                and not d.name.startswith((".", "_"))]
        for d in sorted(subs, key=lambda d: _natural(d.name), reverse=True):
            deep = find_launcher(d.path, look_down=False)
            if deep:
                return deep
    return ""


def folder_dates(folder):
    """(created, last code change) for an app folder as timestamps, 0 where unknown.
    Last code change is the newest source file at the top of the folder or one folder down, so using
    an app (logs, outputs, settings) does not count as changing it."""
    try:
        created = os.path.getctime(folder)
    except OSError:
        return 0, 0
    newest = 0

    def scan(path, deeper):
        nonlocal newest
        try:
            with os.scandir(path) as it:
                for i, d in enumerate(it):
                    if i > 3000:
                        break
                    name = d.name.lower()
                    try:
                        if d.is_file():
                            if name.endswith(CODE_EXT) or name == "requirements.txt":
                                newest = max(newest, d.stat().st_mtime)
                        elif deeper and name not in NOT_CODE_DIRS and not name.startswith("."):
                            scan(d.path, False)
                    except OSError:
                        pass
        except OSError:
            pass

    scan(folder, True)
    return created, newest


def atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


REV_RE = re.compile(r"^--- Revision (\d+) \| (.*?)( \| open)? ---$")
IMG_RE = re.compile(r"^\[(?:image|video)\] (.+)$")


def _take_images(block):
    """Split a block of note text into its text and the "[image] name" / "[video] name" lines that end it."""
    lines = block.split("\n")
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    core, images = lines[:end], []
    while core and IMG_RE.match(core[-1]):
        images.insert(0, IMG_RE.match(core.pop()).group(1).strip())
    return ("\n".join(core), images) if images else (block, [])


def _with_images(text, images):
    if not images:
        return text
    lines = [f"[{'video' if name.lower().endswith(VIDEO_EXT) else 'image'}] {name}" for name in images]
    return text + ("\n" if text else "") + "\n".join(lines)


def parse_note(text):
    """A notes file as (open text, pictures of the open text, revisions newest first).
    Everything above the first revision line is open text; each revision runs to the next one.
    A revision whose line ends in "| open" was reopened with Undo and is being edited again.
    A revision that has pictures carries their file names under "images"."""
    lines = text.split("\n")
    first = next((i for i, ln in enumerate(lines) if REV_RE.match(ln)), None)
    work, images = _take_images(text if first is None else "\n".join(lines[:first]))
    found = []
    for ln in (lines[first:] if first is not None else []):
        m = REV_RE.match(ln)
        if m:
            found.append({"n": int(m.group(1)), "stamp": m.group(2), "open": bool(m.group(3)), "lines": []})
        else:
            found[-1]["lines"].append(ln)
    revs = []
    for r in found:
        body, pics = _take_images("\n".join(r["lines"]).strip("\n"))
        rev = {"n": r["n"], "stamp": r["stamp"], "text": body.strip("\n")}
        if r["open"]:
            rev["open"] = True
        if pics:
            rev["images"] = pics
        revs.append(rev)
    return work, images, revs


def parse_notes(text):
    """The open text and the revisions of a notes file (parse_note gives the open text's pictures too)."""
    work, _images, revs = parse_note(text)
    return work, revs


def join_notes(work, revs, images=()):
    """The file text for an entry: the open text and its pictures, then each revision under its header line."""
    top = _with_images(work, list(images))
    if not revs:
        return top
    parts = [top] if top else []
    for r in revs:
        text = _with_images(r["text"].strip("\n"), r.get("images") or [])
        parts.append(f"--- Revision {r['n']} | {r['stamp']}{' | open' if r.get('open') else ''} ---\n{text}\n")
    return "\n".join(parts)


def readable_notes(name, work, revs, images=(), folder=""):
    """A whole note as plain text for the clipboard: the name, the open text, then every revision under
    its stamp, with one blank line between the parts. Pictures are listed by their full path."""
    def with_pictures(text, names):
        if not names:
            return text
        listed = "\n".join(os.path.join(folder, n) if folder else n for n in names)
        label = "Pictures and videos:" if any(n.lower().endswith(VIDEO_EXT) for n in names) else "Pictures:"
        return (text + "\n" if text else "") + label + "\n" + listed

    parts = [name]
    top = with_pictures(work.strip("\n") if work.strip() else "", list(images))
    if top:
        parts.append(top)
    for r in revs:
        mark = "  \u00b7  reopened, not complete" if r.get("open") else ""
        body = with_pictures(r["text"].rstrip("\n"), r.get("images") or [])
        parts.append(f"Revision {r['n']}  \u00b7  {r['stamp']}{mark}\n{body}".rstrip("\n"))
    return "\n\n".join(parts) + "\n"


def clean_entry(e, section_keys):
    """Fill in anything missing so a hand-edited apps.json cannot break the app."""
    e = dict(e)
    e["id"] = str(e.get("id") or "")
    e["name"] = str(e.get("name") or e["id"] or "Untitled")
    e["section"] = e.get("section") if e.get("section") in section_keys else section_keys[0]
    e["stage"] = e.get("stage") if e.get("stage") in STAGE_KEYS else "working"
    e["family"] = str(e.get("family") or "").strip()
    e["path"] = str(e.get("path") or "")
    e["launch"] = str(e.get("launch") or "")
    f = str(e.get("file") or "")
    e["file"] = f if f.lower().endswith(".txt") and not re.search(r'[\\/]', f) and f == os.path.basename(f) else ""
    e["tldr"] = str(e.get("tldr") or "")
    e["pinned"] = bool(e.get("pinned"))  # kept at the top of its category whatever the sort
    try:
        e["created"] = float(e.get("created") or 0)
    except (TypeError, ValueError):
        e["created"] = 0.0
    return e


def clean_section(s, n):
    try:
        created = float(s.get("created") or n)
    except (TypeError, ValueError):
        created = float(n)
    return {"key": str(s["key"]), "title": str(s.get("title") or s["key"]), "parent": str(s.get("parent") or ""),
            "pinned": bool(s.get("pinned")), "created": created}


class Store:
    def __init__(self):
        os.makedirs(NOTES_DIR, exist_ok=True)
        self.sections = []
        self.entries = []
        self.load_entries()
        self.state = read_json(STATE_PATH, {})
        if not isinstance(self.state, dict):
            self.state = {}

    # ---- sections (categories). A category may sit inside another one ("parent"). The order of the
    # list is the order among brothers and sisters; the tree is drawn depth first.
    def section_keys(self):
        return [s["key"] for s in self.sections]

    def section(self, key):
        return next((s for s in self.sections if s["key"] == key), None)

    def section_title(self, key):
        return next((s["title"] for s in self.sections if s["key"] == key), key)

    def children(self, parent):
        return [s for s in self.sections if s["parent"] == parent]

    def descendants(self, key):
        out, todo = set(), [key]
        while todo:
            k = todo.pop()
            for c in self.children(k):
                if c["key"] not in out:
                    out.add(c["key"])
                    todo.append(c["key"])
        return out

    def flat_sections(self):
        """Every category with its depth, in the order the list shows them."""
        out = []

        def walk(parent, depth):
            for c in self.children(parent):
                out.append((c, depth))
                walk(c["key"], depth + 1)
        walk("", 0)
        return out

    def depth(self, key):
        d, s = 0, self.section(key)
        while s and s["parent"]:
            d, s = d + 1, self.section(s["parent"])
        return d

    def fix_parents(self):
        """A parent that does not exist, or a loop, makes a category top level again."""
        keys = set(self.section_keys())
        for s in self.sections:
            if s["parent"] not in keys or s["parent"] == s["key"]:
                s["parent"] = ""
        for s in self.sections:
            seen, p = {s["key"]}, s["parent"]
            while p:
                if p in seen:
                    s["parent"] = ""
                    break
                seen.add(p)
                p = self.section(p)["parent"]

    def add_section(self, title, parent=""):
        base = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "category"
        key, n = base, 2
        while key in self.section_keys():
            key = f"{base}_{n}"
            n += 1
        self.sections.append({"key": key, "title": title, "parent": parent if self.section(parent) else "",
                              "pinned": False, "created": time.time()})
        self.save_entries()
        return key

    def rename_section(self, key, title):
        for s in self.sections:
            if s["key"] == key:
                s["title"] = title
        self.save_entries()

    def set_section_pinned(self, key, on):
        s = self.section(key)
        if s:
            s["pinned"] = bool(on)
            self.save_entries()

    def place_section(self, key, parent, after=None):
        """Put a category inside `parent` ('' is the top level): right after the brother or sister `after`,
        or first among them. A category cannot go inside itself or one of its own subcategories."""
        s = self.section(key)
        if not s or parent == key or parent in self.descendants(key) or (parent and not self.section(parent)):
            return False
        self.sections.remove(s)
        s["parent"] = parent
        if after and self.section(after) and self.section(after)["parent"] == parent:
            i = self.sections.index(self.section(after)) + 1
        else:
            sib = self.children(parent)
            i = self.sections.index(sib[0]) if sib else len(self.sections)
        self.sections.insert(i, s)
        self.save_entries()
        return True

    def sort_sections(self, parent, by, rev):
        """Sort the categories that share a parent: by name or by when they were made. Pinned ones stay first."""
        sib = self.children(parent)
        pinned = [s for s in sib if s["pinned"]]
        rest = sorted((s for s in sib if not s["pinned"]),
                      key=(lambda s: s["title"].lower()) if by == "name" else (lambda s: s["created"]), reverse=rev)
        self.sections = [s for s in self.sections if s not in sib] + pinned + rest
        self.save_entries()

    def move_section(self, key, step):
        s = self.section(key)
        if not s:
            return
        sib = self.children(s["parent"])
        i = sib.index(s)
        j = max(0, min(len(sib) - 1, i + step))
        if i == j:
            return
        a, b = self.sections.index(sib[i]), self.sections.index(sib[j])
        self.sections[a], self.sections[b] = self.sections[b], self.sections[a]
        self.save_entries()

    def remove_section(self, key):
        """Take a category away. Its notes go to its parent (or to Other), its subcategories move up one
        level. Returns what Undo needs, or None."""
        s = self.section(key)
        if not s or len(self.sections) < 2:
            return None
        i = self.sections.index(s)
        kids = [c["key"] for c in self.children(key)]
        for c in self.children(key):
            c["parent"] = s["parent"]
        keys = self.section_keys()
        home = s["parent"] or ("other" if "other" in keys and key != "other" else next(k for k in keys if k != key))
        ids = [e["id"] for e in self.entries if e["section"] == key]
        for e in self.entries:
            if e["section"] == key:
                e["section"] = home
        self.sections.pop(i)
        self.save_entries()
        return {"section": s, "index": i, "ids": ids, "home": home, "kids": kids}

    def put_section(self, undo):
        """Undo for remove_section."""
        if undo["section"]["key"] in self.section_keys():
            return
        self.sections.insert(min(undo["index"], len(self.sections)), undo["section"])
        for c in self.sections:
            if c["key"] in undo.get("kids", []):
                c["parent"] = undo["section"]["key"]
        for e in self.entries:
            if e["id"] in undo["ids"]:
                e["section"] = undo["section"]["key"]
        self.save_entries()

    def migrate_v3(self):
        """2.0 layout: the default categories, with the old Apps, ComfyUI nodes and Guides and sites folded
        into Vibe Coded. Categories the user made stay, at the top level, before Other."""
        old = self.sections
        new = [clean_section(d, i + 1) for i, d in enumerate(DEFAULT_SECTIONS)]
        known = {d["key"] for d in DEFAULT_SECTIONS} | OLD_INTO_VIBE
        for o in old:  # a default key the user already had keeps the user's title
            for n in new:
                if n["key"] == o["key"] and o["key"] != "other":
                    n["title"] = o["title"]
        mine = [dict(o, parent="") for o in old if o["key"] not in known]
        at = next(i for i, n in enumerate(new) if n["key"] == "other")
        self.sections = new[:at] + mine + new[at:]
        return {k: "vibe" for k in OLD_INTO_VIBE}

    # ---- entries
    def load_entries(self):
        raw = read_json(APPS_PATH, {})
        raw = raw if isinstance(raw, dict) else {}
        self.sections, seen = [], set()
        for n, s in enumerate(raw.get("sections") or DEFAULT_SECTIONS, 1):
            if isinstance(s, dict) and s.get("key") and str(s["key"]) not in seen:
                seen.add(str(s["key"]))
                self.sections.append(clean_section(s, n))
        if not self.sections:
            self.sections = [clean_section(s, n) for n, s in enumerate(DEFAULT_SECTIONS, 1)]
        moved = {}
        migrate = bool(raw) and int(raw.get("version") or 1) < 3
        if migrate:
            moved = self.migrate_v3()
        self.fix_parents()
        keys = self.section_keys()
        self.entries, seen = [], set()
        for e in raw.get("entries", []):
            if isinstance(e, dict) and e.get("section") in moved:
                e = dict(e, section=moved[e["section"]])
            e = clean_entry(e, keys)
            if e["id"] and e["id"] not in seen:
                seen.add(e["id"])
                self.entries.append(e)
        changed = self.name_files() or migrate
        changed = self.move_old_notes() or changed
        if changed:
            self.save_entries()

    def name_files(self):
        """Every entry gets a notes file name of its own. Returns True when any had to be given one."""
        changed = False
        for e in self.entries:
            if not e["file"] or any(o is not e and o["file"].lower() == e["file"].lower() for o in self.entries):
                e["file"] = self.free_file_name(e)
                changed = True
        return changed

    def free_file_name(self, e):
        """<Name>.txt, or <Name> (2).txt and so on when another entry (or a stray folder, in notes/ or in
        images/) has that name. The entry's folders in notes/ and images/ carry the same name without
        the .txt."""
        taken = {o["file"].lower() for o in self.entries if o is not e and o["file"]}
        own = e["file"][:-4].lower() if e["file"] else ""
        base = safe_file_name(e["name"])
        name, n = base + ".txt", 2
        while name.lower() in taken or (name[:-4].lower() != own
                                        and (os.path.isdir(os.path.join(NOTES_DIR, name[:-4]))
                                             or os.path.isdir(os.path.join(IMAGES_DIR, name[:-4])))):
            name = f"{base} ({n}).txt"
            n += 1
        return name

    def move_old_notes(self):
        """Keep the layout current, moving (never copying, never losing) anything found in an older place.
        Notes first sat in data/notes named by id, then in notes/ as loose files named by entry; now each
        entry has a folder of its own in notes/. Pictures first sat in that folder too; now they live in
        images/<entry name>/, and so do pictures that an older version had set aside when they were
        removed from a note."""
        moved = False
        for e in self.entries:
            new = self.notes_path(e["id"])
            for old in (os.path.join(OLD_NOTES_DIR, e["id"] + ".txt"), os.path.join(NOTES_DIR, e["file"])):
                if os.path.isfile(old) and not os.path.exists(new):
                    os.makedirs(os.path.dirname(new), exist_ok=True)
                    os.replace(old, new)
                    moved = True
            for src_dir in (self.entry_dir(e), os.path.join(REMOVED_DIR, "pictures", e["id"])):
                if not os.path.isdir(src_dir):
                    continue
                for name in os.listdir(src_dir):
                    src = os.path.join(src_dir, name)
                    if not name.lower().endswith(MEDIA_EXT) or not os.path.isfile(src):
                        continue
                    stem, ext = os.path.splitext(name)
                    dst, n = os.path.join(self.media_dir(e), name), 2
                    while os.path.exists(dst) and src_dir != self.entry_dir(e):
                        dst = os.path.join(self.media_dir(e), f"{stem}_{n}{ext}")
                        n += 1
                    if not os.path.exists(dst):
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        os.replace(src, dst)
                        moved = True
                if src_dir != self.entry_dir(e):
                    try:
                        os.rmdir(src_dir)
                    except OSError:
                        pass
        try:
            os.rmdir(os.path.join(REMOVED_DIR, "pictures"))
        except OSError:
            pass
        if os.path.isdir(OLD_NOTES_DIR):
            try:
                for name in os.listdir(OLD_NOTES_DIR):  # a file no entry owns: keep it, clearly marked
                    dst = os.path.join(NOTES_DIR, "_unlinked " + name)
                    if not os.path.exists(dst):
                        os.replace(os.path.join(OLD_NOTES_DIR, name), dst)
                os.rmdir(OLD_NOTES_DIR)
            except OSError:
                pass
            moved = True
        return moved

    def get(self, eid):
        for e in self.entries:
            if e["id"] == eid:
                return e
        return None

    def save_entries(self):
        atomic_write(APPS_PATH, json.dumps({"version": 3, "sections": self.sections, "entries": self.entries},
                                           indent=1, ensure_ascii=False))

    def save_state(self):
        atomic_write(STATE_PATH, json.dumps(self.state, indent=1))

    def families(self):
        """Family names in use, A to Z, each spelled the way most of its members spell it."""
        spell = {}
        for e in self.entries:
            if e["family"]:
                spell.setdefault(e["family"].lower(), []).append(e["family"])
        return sorted((max(set(v), key=v.count) for v in spell.values()), key=str.lower)

    def members(self, family):
        fam = family.lower()
        return [e for e in self.entries if e["family"].lower() == fam] if fam else []

    def siblings(self, e):
        return [o for o in self.members(e["family"]) if o["id"] != e["id"]]

    def new_id(self, name):
        base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "note"
        taken = {e["id"] for e in self.entries} | {r["entry"]["id"] for r in self.removed()}
        eid, n = base, 2
        while (eid in taken or os.path.exists(os.path.join(REMOVED_DIR, eid + ".txt"))
               or os.path.exists(os.path.join(REMOVED_DIR, eid))):
            eid = f"{base}_{n}"
            n += 1
        return eid

    def add(self, name, section, after_id=None, first=False):
        e = clean_entry({"id": self.new_id(name), "name": name, "section": section, "stage": "early",
                         "created": time.time()}, self.section_keys())
        idx = len(self.entries)
        if after_id:
            for i, o in enumerate(self.entries):
                if o["id"] == after_id:
                    idx = i + 1
        elif first:  # first among the notes of its category
            idx = next((i for i, o in enumerate(self.entries) if o["section"] == e["section"]), idx)
        self.entries.insert(idx, e)
        e["file"] = self.free_file_name(e)
        self.save_entries()
        return e

    def drop(self, eid):
        """Forget an entry that never had anything in it (a blank new note left unused). No Undo record."""
        e = self.get(eid)
        if e:
            self.entries.remove(e)
            self.save_entries()

    def rename(self, e, name):
        """Rename an entry. Its notes folder, its notes file and its images folder are renamed with it,
        so they can always be found by the entry's name. If Windows will not let a folder be renamed
        (it is open somewhere), every folder keeps its old name and nothing is lost."""
        old_dir, old_file, old_media = self.entry_dir(e), e["file"], self.media_dir(e)
        e["name"] = name
        new_file = self.free_file_name(e)
        if new_file != old_file:
            new_dir = os.path.join(NOTES_DIR, new_file[:-4])
            new_media = os.path.join(IMAGES_DIR, new_file[:-4])
            done = []  # (now, before) for each rename made, so they can be put back
            try:
                if os.path.isdir(old_media):
                    if os.path.exists(new_media) and os.path.normcase(new_media) != os.path.normcase(old_media):
                        raise OSError("an images folder with the new name is already there")
                    os.replace(old_media, new_media)
                    done.append((new_media, old_media))
                if os.path.isdir(old_dir):
                    os.replace(old_dir, new_dir)
                    done.append((new_dir, old_dir))
                    inner = os.path.join(new_dir, old_file)
                    if os.path.isfile(inner):
                        os.replace(inner, os.path.join(new_dir, new_file))
                e["file"] = new_file
            except OSError:
                for now, before in reversed(done):
                    try:
                        os.replace(now, before)
                    except OSError:
                        pass
        self.save_entries()

    def reorder(self, pairs):
        """pairs: [(id, section)] in the new order."""
        by_id = {e["id"]: e for e in self.entries}
        out = []
        for eid, section in pairs:
            e = by_id.pop(eid, None)
            if e:
                e["section"] = section
                out.append(e)
        out.extend(by_id.values())
        self.entries = out
        self.save_entries()

    # ---- notes, ideas and pictures: all in the entry's own folder
    def entry_dir(self, e):
        return os.path.join(NOTES_DIR, e["file"][:-4])

    def notes_path(self, eid):
        e = self.get(eid)
        if e and e["file"]:
            return os.path.join(self.entry_dir(e), e["file"])
        return os.path.join(NOTES_DIR, eid + ".txt")

    def read_notes(self, eid):
        try:
            with open(self.notes_path(eid), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def write_notes(self, eid, text):
        path = self.notes_path(eid)
        if text or os.path.exists(path):  # an entry with nothing in its note gets no folder
            atomic_write(path, text)

    def read_ideas(self, eid):
        e = self.get(eid)
        if not e:
            return ""
        try:
            with open(os.path.join(self.entry_dir(e), "ideas.txt"), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def write_ideas(self, eid, text):
        e = self.get(eid)
        if not e:
            return
        path = os.path.join(self.entry_dir(e), "ideas.txt")
        if text.strip():
            atomic_write(path, text)
        elif os.path.exists(path):
            os.remove(path)

    def media_dir(self, e):
        """Where the entry's pictures and videos are kept: images/<entry name>/."""
        return os.path.join(IMAGES_DIR, e["file"][:-4])

    def image_path(self, eid, name):
        e = self.get(eid)
        return os.path.join(self.media_dir(e), name) if e else ""

    def free_image_name(self, eid, wanted):
        """A file name for a new picture or video that does not collide with anything in the entry's
        images folder (files stay there after they leave a note, so an old name is never reused)."""
        stem, ext = os.path.splitext(os.path.basename(wanted))
        stem = safe_file_name(stem)[:60].rstrip(". ") or "picture"
        ext = ext.lower() if ext.lower() in MEDIA_EXT else ".png"
        folder = self.media_dir(self.get(eid))
        name, n = stem + ext, 2
        while os.path.exists(os.path.join(folder, name)):
            name = f"{stem}_{n}{ext}"
            n += 1
        return name

    def add_image_file(self, eid, src):
        """Copy a picture or video into images/<entry name>/ and return its name there. The original is
        not touched, and the same file added twice is kept once."""
        folder = self.media_dir(self.get(eid))
        same = os.path.join(folder, os.path.basename(src))
        if os.path.isfile(same) and (os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(same))
                                     or filecmp.cmp(src, same, shallow=False)):
            return os.path.basename(src)
        name = self.free_image_name(eid, src)
        os.makedirs(folder, exist_ok=True)
        shutil.copy2(src, os.path.join(folder, name))
        return name

    def images_bytes(self):
        """How much the whole images folder holds, in bytes."""
        total = 0
        for base, _dirs, names in os.walk(IMAGES_DIR):
            for n in names:
                try:
                    total += os.path.getsize(os.path.join(base, n))
                except OSError:
                    pass
        return total

    def dates(self, e):
        """(created, last changed) for sorting: the app folder's dates, else the notes file's."""
        folder = self.folder(e)
        created, changed = folder_dates(folder) if folder and os.path.isdir(folder) else (0, 0)
        if not created or not changed:
            try:
                st = os.stat(self.notes_path(e["id"]))
                created, changed = created or st.st_ctime, changed or st.st_mtime
            except OSError:
                pass
        return created, changed

    # ---- folders and launchers
    def folder(self, e):
        return os.path.normpath(expand_dir(e["path"])) if e["path"] else ""

    def set_folder(self, e, path):
        e["path"] = contract_dir(os.path.normpath(path)) if path else ""
        e["launch"] = ""
        self.save_entries()

    def linked_launcher(self, e):
        """The launch file linked by hand, if one is set and it still exists."""
        if not e["launch"]:
            return ""
        p = expand_dir(e["launch"])
        if not os.path.isabs(p):
            folder = self.folder(e)
            p = os.path.join(folder, p) if folder else ""
        return os.path.normpath(p) if p and os.path.isfile(p) else ""

    def launcher(self, e):
        """The file that starts this entry: the one linked by hand, else the best guess, else ''."""
        linked = self.linked_launcher(e)
        if linked:
            return linked
        folder = self.folder(e)
        return find_launcher(folder) if folder and os.path.isdir(folder) else ""

    def set_launcher(self, e, path):
        """Link a launch file by hand. '' goes back to finding it automatically."""
        if path:
            path = os.path.normpath(path)
            folder = self.folder(e)
            inside = folder and os.path.normcase(path).startswith(os.path.normcase(folder) + os.sep)
            e["launch"] = os.path.relpath(path, folder) if inside else contract_dir(path)
        else:
            e["launch"] = ""
        self.save_entries()

    # ---- remove / restore
    def removed(self):
        data = read_json(REMOVED_PATH, [])
        return [r for r in data if isinstance(r, dict) and isinstance(r.get("entry"), dict)] if isinstance(data, list) else []

    def remove(self, eid):
        e = self.get(eid)
        if not e:
            return None
        idx = self.entries.index(e)
        os.makedirs(REMOVED_DIR, exist_ok=True)
        src, held = self.entry_dir(e), ""
        if os.path.isdir(src):  # the notes folder goes (notes and ideas); its images folder stays where it is
            dst, n = os.path.join(REMOVED_DIR, eid), 2
            while os.path.exists(dst):
                dst = os.path.join(REMOVED_DIR, f"{eid}_{n}")
                n += 1
            os.replace(src, dst)
            held = os.path.basename(dst)
        rec = {"entry": e, "index": idx, "removed": time.strftime("%Y-%m-%d %H:%M"), "folder": held}
        atomic_write(REMOVED_PATH, json.dumps(self.removed() + [rec], indent=1, ensure_ascii=False))
        self.entries.pop(idx)
        self.save_entries()
        return rec

    def restore(self, eid):
        recs = self.removed()
        rec = next((r for r in recs if r["entry"].get("id") == eid), None)
        if not rec or self.get(eid):
            return None
        e = clean_entry(rec["entry"], self.section_keys())
        old_file = e["file"]
        self.entries.insert(min(int(rec.get("index", len(self.entries))), len(self.entries)), e)
        if not e["file"] or any(o is not e and o["file"].lower() == e["file"].lower() for o in self.entries):
            e["file"] = self.free_file_name(e)
        held = os.path.join(REMOVED_DIR, rec["folder"]) if rec.get("folder") else ""
        if held and os.path.isdir(held) and not os.path.exists(self.entry_dir(e)):
            os.makedirs(NOTES_DIR, exist_ok=True)
            os.replace(held, self.entry_dir(e))
            inner = os.path.join(self.entry_dir(e), old_file)
            if old_file and old_file != e["file"] and os.path.isfile(inner):
                os.replace(inner, self.notes_path(eid))
        legacy = os.path.join(REMOVED_DIR, eid + ".txt")  # removed before entries had folders of their own
        if os.path.isfile(legacy) and not os.path.exists(self.notes_path(eid)):
            os.makedirs(self.entry_dir(e), exist_ok=True)
            os.replace(legacy, self.notes_path(eid))
        self.move_old_notes()  # a folder removed by an older version still has its pictures inside
        self.save_entries()
        atomic_write(REMOVED_PATH, json.dumps([r for r in recs if r is not rec], indent=1, ensure_ascii=False))
        return e
