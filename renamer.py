"""
Batch File Renamer
------------------
Pick a folder, tick the files (or folders) you want, remove or replace words in the names
(at the start, at the end, anywhere, or as a whole word), or number them in order
(1.png, 2.png ... or notes_1.png, notes_2.png ...), add a prefix and/or
suffix, optionally move the renamed files into a new folder, and undo runs from
the log.  (To sort files into folders by word, use sorter.py.)

Numbering follows the list from top to bottom. The list starts in natural order
(a2 before a10); drag a name up or down to change the order.

Run:  python renamer.py
Needs only Python 3 (standard library, Tkinter included).
"""

import fnmatch
import json
import os
import re
import shutil
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:  # lets the logic be imported/tested without a display
    tk = None

# Every run is recorded in this one file, which lives next to renamer.py
# (never inside the folders being renamed).
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renamer_log.json")
# Per-folder log written by an older version; just ignored when listing files.
LOG_NAME = ".renamer_last_run.json"


# ----------------------------------------------------------------------------
# Core logic (no GUI)
# ----------------------------------------------------------------------------
def _natural_key(name):
    """Sort key so that file2 comes before file10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def list_files(folder, patterns, kind="Files"):
    """
    Items directly inside `folder` (nothing from deeper levels) that match the
    comma-separated patterns, in natural order (a2 before a10). kind is "Files",
    "Folders" or "Both". With "Both" the patterns apply to files only and every
    (visible) folder is listed.
    """
    pats = [p.strip().lower() for p in patterns.split(",") if p.strip()] or ["*"]
    out = []
    try:
        names = sorted(os.listdir(folder), key=_natural_key)
    except OSError:
        return out
    for name in names:
        if name == LOG_NAME:
            continue
        path = os.path.join(folder, name)
        if os.path.isdir(path):
            if kind == "Files" or name.startswith("."):
                continue
            if kind == "Both" or any(fnmatch.fnmatch(name.lower(), p) for p in pats):
                out.append(name)
            continue
        if kind == "Folders" or not os.path.isfile(path):
            continue
        if any(fnmatch.fnmatch(name.lower(), p) for p in pats):
            out.append(name)
    return out


SIZE_RE = re.compile(r"[\s_\-]*\d+\s*[xX]\s*\d+$")   # e.g. _384x256 at the end
SEPARATORS = " _-"


def _split_list(text):
    """'man_, creature_' -> ['creature_', 'man_'] (longest first)."""
    items = [t.strip() for t in text.split(",") if t.strip()]
    return sorted(items, key=len, reverse=True)


WHERE_CHOICES = ("Anywhere", "Start", "End", "Whole word")
DOUBLE_SEP = re.compile(r"([ _\-])\1+")     # "__", "--", "  "
_WORD_START = r"(?<![^_\-\s])"              # start of name or just after _ - space
_WORD_END = r"(?![^_\-\s])"                 # end of name or just before _ - space


def apply_rule(stem, where, find, replace):
    """
    Apply one remove/replace rule to `stem` (case-insensitive).
    `find` may hold several options separated by commas.
      Start / End : the first option that matches is replaced
      Anywhere    : every occurrence of every option is replaced
      Whole word  : like Anywhere, but only when it is a separate word
                    (between _ - space or the ends of the name)
    An empty `replace` removes the text.
    """
    for item in _split_list(find):
        low, it = stem.lower(), item.lower()
        if where == "Start":
            if low.startswith(it):
                stem = replace + stem[len(item):]
                break
        elif where == "End":
            if low.endswith(it):
                stem = stem[:len(stem) - len(item)] + replace
                break
        elif where == "Whole word":
            stem = re.sub(_WORD_START + re.escape(item) + _WORD_END,
                          lambda m: replace, stem, flags=re.IGNORECASE)
        else:  # Anywhere
            stem = re.sub(re.escape(item), lambda m: replace, stem, flags=re.IGNORECASE)
    return stem


def remove_parts(stem, rules=(), strip_size=False):
    """
    Apply the size removal (if ticked) and then every rule, top to bottom.
    `rules` is a list of (where, find, replace). Returns (new_stem, changed).
    """
    original = stem
    if strip_size:
        stem = SIZE_RE.sub("", stem)
    for where, find, replace in rules:
        stem = apply_rule(stem, where, find, replace)
    if stem != original:
        if not DOUBLE_SEP.search(original):
            stem = DOUBLE_SEP.sub(r"\1", stem)   # tidy "__" left behind by a removal
        stem = stem.strip(SEPARATORS)            # and leftover _ - space at the ends
    return stem, stem != original


CAPITALISE_CHOICES = ("Off", "First letter only", "Every word")
_WORD_FIRST_LETTER = re.compile(r"(^|[ _\-])([^\W\d_])")   # a letter that starts a word


def apply_capitalise(text, mode="Off"):
    """
    "First letter only": capitalise the first letter of the whole name.
    "Every word": capitalise the first letter of every word (words are split
    by _ - or space). Only those letters change; the rest of each word is left
    exactly as it is, and words that start with a digit are untouched.
    """
    if mode == "First letter only":
        return text[:1].upper() + text[1:]
    if mode == "Every word":
        return _WORD_FIRST_LETTER.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    return text


def build_name(filename, prefix, suffix, replace_spaces, rules=(), strip_size=False,
               capitalise="Off", is_dir=False, number=None):
    """
    Return (new_name, already_prefixed, removal_skipped).
    Order: remove/replace words, then replace spaces, then add prefix/suffix,
    then (optionally) capitalise: first letter only, or every word.
    removal_skipped is True when the rules would leave an empty name, in which
    case the original name is kept for that step.
    If `number` (a string such as "7") is given, it replaces the whole name
    (the remove/replace rules are not used); prefix/suffix still get added,
    e.g. prefix "notes" + number "7" -> notes_7.png
    """
    # a folder name is one whole name: "Bandit v1.2" has no extension
    stem, ext = (filename, "") if is_dir else os.path.splitext(filename)
    removal_skipped = False
    if number is not None:
        stem = number
    else:
        cut, changed = remove_parts(stem, rules, strip_size)
        if changed:
            if cut:
                stem = cut
            else:
                removal_skipped = True
    prefix, suffix = prefix.strip(), suffix.strip()
    joiner = " "
    if replace_spaces:
        joiner = "_"
        stem = stem.replace(" ", joiner)
        prefix = prefix.replace(" ", joiner)
        suffix = suffix.replace(" ", joiner)
    already = bool(prefix) and stem.lower().startswith(prefix.lower() + joiner)
    parts = [p for p in (prefix, stem, suffix) if p]
    new_stem = joiner.join(parts)
    new_stem = apply_capitalise(new_stem, capitalise)
    return new_stem + ext, already, removal_skipped


def _is_own_name(src, dst):
    """
    True if `dst` is free, or is the very same file as `src`. This is what lets
    a rename that only changes capital letters (standstill_x -> Standstill_x)
    work on filesystems that ignore letter case, such as Windows.
    """
    if not os.path.exists(dst):
        return True
    try:
        return os.path.samefile(src, dst)
    except OSError:
        return False


def _move_pairs(pairs, done):
    """
    Move every (src, dst). If a destination is the current name of another item
    in the batch (e.g. 1.png <-> 2.png, or 2.png -> 1.png while 1.png -> 2.png),
    everything goes via temporary names first so nothing gets overwritten.
    Finished moves are appended to `done`.
    """
    srcs = {os.path.normcase(s) for s, _ in pairs}
    chained = any(os.path.normcase(d) in srcs and os.path.normcase(d) != os.path.normcase(s)
                  for s, d in pairs)
    if not chained:
        for src, dst in pairs:
            shutil.move(src, dst)
            done.append((src, dst))
        return
    tag = datetime.now().strftime("%H%M%S%f")
    staged = []                      # (src, temp, dst)
    try:
        for i, (src, dst) in enumerate(pairs):
            temp = os.path.join(os.path.dirname(src), f".renamer_tmp_{tag}_{i}")
            shutil.move(src, temp)
            staged.append((src, temp, dst))
    except Exception:
        for src, temp, _ in reversed(staged):   # put everything back
            shutil.move(temp, src)
        raise
    pending = list(staged)
    try:
        while pending:
            src, temp, dst = pending[0]
            shutil.move(temp, dst)
            done.append((src, dst))
            pending.pop(0)
    except Exception:
        for src, temp, _ in pending:            # restore what was not finished
            if os.path.exists(temp):
                shutil.move(temp, src)
        raise


def plan_renames(folder, selected, prefix, suffix, replace_spaces, move_folder=None,
                 rules=(), strip_size=False, capitalise="Off",
                 numbering=False, start=1, pad=0, keep_order=False):
    """
    Build the rename plan for the selected filenames.
    Returns a list of dicts: src, dst, name, numbered (bool), already_prefixed (bool).
    Name clashes (with files on disk or within this batch) get _1, _2, ...
    With numbering=True the selected items are called start, start+1, ...
    (zero-padded to `pad` digits), in the order given if keep_order is True,
    otherwise in natural order (file2 before file10).
    """
    target_dir = os.path.join(folder, move_folder) if move_folder else folder
    existing = set()    # names already in the target folder (lower-case)
    if os.path.isdir(target_dir):
        existing = {n.lower() for n in os.listdir(target_dir)}
    if numbering:
        if not keep_order:
            selected = sorted(selected, key=_natural_key)
        if not move_folder:
            # the selected items all get new, distinct names, so their current
            # names are free to be reused (lets 2.png -> 1.png and 1.png -> 2.png work)
            existing -= {s.lower() for s in selected}
    planned = set()     # names given out so far in this batch (lower-case)
    plan = []
    for idx, fname in enumerate(selected):
        src = os.path.join(folder, fname)
        is_dir = os.path.isdir(src)
        if is_dir and move_folder:
            raise ValueError("Folders can't be moved into a new folder.")
        number = str(start + idx).zfill(pad) if numbering else None
        new_name, already, skipped = build_name(
            fname, prefix, suffix, replace_spaces, rules, strip_size, capitalise, is_dir,
            number)
        numbered = False
        # a file whose name doesn't change and stays in place is not a clash
        unchanged = (new_name == fname and not move_folder)
        if not unchanged:
            stem, ext = (new_name, "") if is_dir else os.path.splitext(new_name)
            candidate, n = new_name, 0
            while True:
                low = candidate.lower()
                clash = low in planned
                if not clash and low in existing:
                    # in place, the file's own current name is not a clash
                    own = (not move_folder and low == fname.lower()
                           and _is_own_name(src, os.path.join(target_dir, candidate)))
                    clash = not own
                if not clash:
                    break
                n += 1
                candidate = f"{stem}_{n}{ext}"
                numbered = True
            new_name = candidate
        planned.add(new_name.lower())
        plan.append({
            "src": src,
            "dst": os.path.join(target_dir, new_name),
            "name": new_name,
            "is_dir": is_dir,
            "numbered": numbered,
            "already_prefixed": already,
            "removal_skipped": skipped,
            "unchanged": unchanged,
        })
    return plan


def load_history():
    """All logged runs, oldest first. Empty list if there is no log yet."""
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_history(history):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def apply_plan(folder, plan, move_folder=None):
    """
    Execute the plan and record the run in the log file next to this script.
    Returns the list of (old, new) paths done. If the run stops part-way,
    whatever was already moved is still logged so it can be undone.
    """
    folder = os.path.abspath(folder)
    created_dir = None
    if move_folder:
        target_dir = os.path.join(folder, move_folder)
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)
            created_dir = target_dir
    done = []
    try:
        pairs = [(i["src"], i["dst"]) for i in plan if not i["unchanged"]]
        leaving = {os.path.normcase(s) for s, _ in pairs}   # names about to be vacated
        for src, dst in pairs:
            if not _is_own_name(src, dst) and os.path.normcase(dst) not in leaving:
                raise FileExistsError(f"Target already exists: {dst}")
        _move_pairs(pairs, done)
    finally:
        if done:
            history = load_history()
            moved_to = {new for _, new in done}
            history.append({
                "id": max((e.get("id", 0) for e in history), default=0) + 1,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "folder": folder,
                "move_folder": move_folder,
                "created_dir": created_dir,
                "moves": [[old, new] for old, new in done],
                "numbered": [p["dst"] for p in plan
                             if p["numbered"] and p["dst"] in moved_to],
                "undone": False,
            })
            save_history(history)
        elif created_dir and os.path.isdir(created_dir) and not os.listdir(created_dir):
            os.rmdir(created_dir)  # nothing moved, don't leave an empty folder
    return done


def last_run_id(folder=None):
    """Id of the newest run that has not been undone (optionally for one folder)."""
    want = os.path.normcase(os.path.abspath(folder)) if folder else None
    for entry in reversed(load_history()):
        if entry.get("undone"):
            continue
        if want is None or os.path.normcase(os.path.abspath(entry["folder"])) == want:
            return entry["id"]
    return None


def undo_run(run_id):
    """Reverse one logged run. Returns number of files restored."""
    history = load_history()
    entry = next((e for e in history if e.get("id") == run_id), None)
    if entry is None:
        raise FileNotFoundError("That run is not in the log.")
    if entry.get("undone"):
        raise ValueError("That run was already undone.")
    back = [(new, old) for old, new in reversed(entry["moves"]) if os.path.exists(new)]
    leaving = {os.path.normcase(n) for n, _ in back}
    back = [(n, o) for n, o in back
            if _is_own_name(n, o) or os.path.normcase(o) in leaving]
    restored_pairs = []
    _move_pairs(back, restored_pairs)
    restored = len(restored_pairs)
    created = entry.get("created_dir")
    if created and os.path.isdir(created) and not os.listdir(created):
        os.rmdir(created)
    entry["undone"] = True
    entry["undone_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_history(history)
    return restored


def undo_last(folder=None):
    """Undo the newest active run (for `folder` if given). Returns files restored."""
    run_id = last_run_id(folder)
    if run_id is None:
        raise FileNotFoundError("No earlier run to undo.")
    return undo_run(run_id)


# ----------------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------------
CHECKED, UNCHECKED = "☑", "☐"


class RenamerApp:
    def __init__(self, root):
        self.root = root
        root.title("Batch File Renamer")
        root.geometry("900x850")
        root.minsize(760, 730)

        self.folder = tk.StringVar()
        self.filter = tk.StringVar(value="*.png")
        self.items = tk.StringVar(value="Files")      # Files / Folders / Both
        self.search = tk.StringVar()
        self.prefix = tk.StringVar()
        self.suffix = tk.StringVar()
        self.rules = []        # remove/replace rows, see _add_rule
        self.strip_size = tk.BooleanVar(value=False)
        self.capitalise = tk.StringVar(value="Off")
        self.replace_spaces = tk.BooleanVar(value=True)
        self.numbering = tk.BooleanVar(value=False)
        self.num_start = tk.StringVar(value="1")
        self.num_pad = tk.StringVar(value="0")
        self.do_move = tk.BooleanVar(value=False)
        self.move_name = tk.StringVar()
        self.move_name_touched = False

        self.files = []        # all filenames in folder matching the filter, in list order
        self.checked = {}      # filename -> bool
        self.dirs = set()      # which of self.files are folders
        self.press = None      # row pressed with the mouse: (name, start_y)
        self.dragging = None   # name of the row being dragged

        self._build_menu()
        self._build_ui()
        for var in (self.search, self.prefix, self.suffix):
            var.trace_add("write", lambda *a: self._on_change())
        for var in (self.strip_size, self.capitalise, self.replace_spaces,
                    self.numbering, self.num_start, self.num_pad,
                    self.do_move, self.move_name):
            var.trace_add("write", lambda *a: self._refresh())
        self.items.trace_add("write", lambda *a: self._on_items_change())

    # ---- layout ----------------------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        log_menu = tk.Menu(menubar, tearoff=0)
        log_menu.add_command(label="View log...", command=self.show_log)
        log_menu.add_command(label="Undo last run (this folder)", command=self.undo)
        log_menu.add_separator()
        log_menu.add_command(label="Clear log...", command=self.clear_log)
        menubar.add_cascade(label="Log", menu=log_menu)
        self.root.config(menu=menubar)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Folder:").pack(side="left")
        ttk.Entry(top, textvariable=self.folder).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="Browse", command=self.browse).pack(side="left")
        ttk.Label(top, text="  Items:").pack(side="left")
        ttk.Combobox(top, textvariable=self.items, values=("Files", "Folders", "Both"),
                     state="readonly", width=8).pack(side="left", padx=4)
        ttk.Label(top, text="  Filter:").pack(side="left")
        flt = ttk.Entry(top, textvariable=self.filter, width=12)
        flt.pack(side="left", padx=4)
        flt.bind("<Return>", lambda e: self.load_files())
        ttk.Button(top, text="Reload", command=self.load_files).pack(side="left")

        sel = ttk.Frame(self.root)
        sel.pack(fill="x", **pad)
        ttk.Button(sel, text="Select all", command=lambda: self.set_all(True)).pack(side="left")
        ttk.Button(sel, text="Select none", command=lambda: self.set_all(False)).pack(side="left", padx=4)
        ttk.Button(sel, text="Invert", command=self.invert).pack(side="left")
        ttk.Button(sel, text="Sort A-Z", command=self.sort_natural).pack(side="left", padx=(12, 0))
        ttk.Entry(sel, textvariable=self.search, width=22).pack(side="right")
        ttk.Label(sel, text="Search:").pack(side="right", padx=4)
        ttk.Label(self.root, text="Tip: drag a name up or down to change the order "
                                  "(numbering follows the list, top to bottom; "
                                  "clear Search first).",
                  foreground="#666666").pack(anchor="w", padx=10)

        mid = ttk.Frame(self.root)
        mid.pack(fill="both", expand=True, **pad)
        cols = ("check", "old", "new", "note")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="none")
        self.tree.heading("check", text="")
        self.tree.heading("old", text="Current name")
        self.tree.heading("new", text="New name")
        self.tree.heading("note", text="Note")
        self.tree.column("check", width=34, anchor="center", stretch=False)
        self.tree.column("old", width=260)
        self.tree.column("new", width=300)
        self.tree.column("note", width=200)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.bind("<ButtonPress-1>", self._on_press)
        self.tree.bind("<B1-Motion>", self._on_drag)
        self.tree.bind("<ButtonRelease-1>", self._on_release)
        self.tree.tag_configure("warn", foreground="#b35c00")
        self.tree.tag_configure("off", foreground="#888888")
        self.tree.tag_configure("drag", background="#dbe9ff")

        rem = ttk.LabelFrame(self.root,
                             text="Remove / replace word (rules run top to bottom, before adding)")
        rem.pack(fill="x", **pad)
        self.rules_box = ttk.Frame(rem)
        self.rules_box.pack(fill="x", padx=8, pady=(4, 0))
        ttk.Label(self.rules_box, text="Where").grid(row=0, column=0, sticky="w")
        ttk.Label(self.rules_box, text="Find").grid(row=0, column=1, sticky="w")
        ttk.Label(self.rules_box, text="Replace with (empty = remove)").grid(
            row=0, column=3, sticky="w")
        self._add_rule()
        rbar = ttk.Frame(rem)
        rbar.pack(fill="x", padx=8, pady=(2, 2))
        ttk.Button(rbar, text="+ Add rule", command=self._add_rule).pack(side="left")
        ttk.Checkbutton(rbar, text="Also remove a size at the end (like _384x256)",
                        variable=self.strip_size).pack(side="left", padx=16)
        ttk.Label(rem, text="Tip: put several options in one Find box separated by commas "
                            "(man_, creature_).").pack(anchor="w", padx=8, pady=(0, 4))

        opts = ttk.LabelFrame(self.root, text="Rename options")
        opts.pack(fill="x", **pad)
        row1 = ttk.Frame(opts)
        row1.pack(fill="x", padx=8, pady=4)
        ttk.Label(row1, text="Prefix:").pack(side="left")
        ttk.Entry(row1, textvariable=self.prefix, width=22).pack(side="left", padx=6)
        ttk.Label(row1, text="Suffix:").pack(side="left", padx=(16, 0))
        ttk.Entry(row1, textvariable=self.suffix, width=22).pack(side="left", padx=6)

        ttk.Checkbutton(opts, text='Replace spaces with "_"',
                        variable=self.replace_spaces).pack(anchor="w", padx=8)
        crow = ttk.Frame(opts)
        crow.pack(fill="x", padx=8, pady=2)
        ttk.Label(crow, text="Capitalise:").pack(side="left")
        ttk.Combobox(crow, textvariable=self.capitalise, values=CAPITALISE_CHOICES,
                     state="readonly", width=18).pack(side="left", padx=6)
        ttk.Label(crow, text="First letter only: Standstill_rat    "
                             "Every word: Standstill_Rat").pack(side="left")
        nrow = ttk.Frame(opts)
        nrow.pack(fill="x", padx=8, pady=2)
        ttk.Checkbutton(nrow, text="Number the ticked items in list order "
                                   "(replaces the name; prefix/suffix still added)",
                        variable=self.numbering).pack(side="left")
        ttk.Label(nrow, text="  Start at:").pack(side="left")
        ttk.Spinbox(nrow, textvariable=self.num_start, from_=0, to=999999,
                    width=7).pack(side="left", padx=4)
        ttk.Label(nrow, text="Digits:").pack(side="left")
        ttk.Spinbox(nrow, textvariable=self.num_pad, from_=0, to=10,
                    width=4).pack(side="left", padx=4)
        ttk.Label(opts, text="Example: prefix notes -> notes_1.png, notes_2.png ...  "
                             "No prefix -> 1.png, 2.png ...  Digits 3 -> 001, 002 ...").pack(
            anchor="w", padx=28)
        self.move_check = ttk.Checkbutton(opts, text="Move renamed files into a new folder "
                                                     "(files only)",
                                          variable=self.do_move)
        self.move_check.pack(anchor="w", padx=8)
        row2 = ttk.Frame(opts)
        row2.pack(fill="x", padx=28, pady=(0, 6))
        ttk.Label(row2, text="Folder name:").pack(side="left")
        ent = ttk.Entry(row2, textvariable=self.move_name, width=28)
        ent.pack(side="left", padx=6)
        ent.bind("<KeyRelease>", lambda e: setattr(self, "move_name_touched", True))

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", **pad)
        ttk.Button(bottom, text="Rename selected", command=self.rename).pack(side="left")
        ttk.Button(bottom, text="Undo last run", command=self.undo).pack(side="left", padx=8)
        self.status = ttk.Label(bottom, text="Choose a folder to begin.")
        self.status.pack(side="right")

    # ---- remove / replace rules -------------------------------------------
    def _add_rule(self, where="Anywhere", find="", replace=""):
        rule = {
            "where": tk.StringVar(value=where),
            "find": tk.StringVar(value=find),
            "replace": tk.StringVar(value=replace),
        }
        box = self.rules_box
        rule["combo"] = ttk.Combobox(box, textvariable=rule["where"], values=WHERE_CHOICES,
                                     state="readonly", width=11)
        rule["find_entry"] = ttk.Entry(box, textvariable=rule["find"], width=26)
        rule["arrow"] = ttk.Label(box, text="→")
        rule["replace_entry"] = ttk.Entry(box, textvariable=rule["replace"], width=26)
        rule["remove"] = ttk.Button(box, text="−", width=3,
                                    command=lambda r=rule: self._remove_rule(r))
        for key in ("where", "find", "replace"):
            rule[key].trace_add("write", lambda *a: self._refresh())
        self.rules.append(rule)
        self._layout_rules()
        self._refresh()

    def _remove_rule(self, rule):
        if rule in self.rules:
            self.rules.remove(rule)
        for key in ("combo", "find_entry", "arrow", "replace_entry", "remove"):
            rule[key].destroy()
        self._layout_rules()
        self._refresh()

    def _layout_rules(self):
        for row, rule in enumerate(self.rules, start=1):
            rule["combo"].grid(row=row, column=0, padx=(0, 6), pady=2, sticky="w")
            rule["find_entry"].grid(row=row, column=1, padx=(0, 6), pady=2)
            rule["arrow"].grid(row=row, column=2, padx=4)
            rule["replace_entry"].grid(row=row, column=3, padx=(0, 6), pady=2)
            rule["remove"].grid(row=row, column=4, pady=2)

    def _rules(self):
        """(where, find, replace) for every row that has something in Find."""
        return [(r["where"].get(), r["find"].get(), r["replace"].get())
                for r in self.rules if r["find"].get().strip()]

    # ---- actions ---------------------------------------------------------
    def browse(self):
        path = filedialog.askdirectory(title="Choose folder")
        if path:
            self.folder.set(path)
            self.load_files()

    def load_files(self):
        folder = self.folder.get().strip()
        if not os.path.isdir(folder):
            messagebox.showwarning("Folder", "Please choose a valid folder.")
            return
        self.files = list_files(folder, self.filter.get(), self.items.get())
        self.checked = {f: True for f in self.files}
        self.dirs = {f for f in self.files if os.path.isdir(os.path.join(folder, f))}
        self._refresh()

    def _visible(self):
        q = self.search.get().strip().lower()
        return [f for f in self.files if q in f.lower()]

    def set_all(self, state):
        for f in self._visible():
            self.checked[f] = state
        self._refresh()

    def invert(self):
        for f in self._visible():
            self.checked[f] = not self.checked[f]
        self._refresh()

    def sort_natural(self):
        """Put the list back in natural order (a2 before a10)."""
        self.files.sort(key=_natural_key)
        self._refresh()

    # ---- mouse: tick a box, or drag a name to reorder ----------------------
    def _on_press(self, event):
        self.press, self.dragging = None, None
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return "break"
        if self.tree.identify_column(event.x) == "#1":     # the tick box
            self.checked[iid] = not self.checked.get(iid, False)
            self._refresh()
        else:                                              # maybe the start of a drag
            self.press = (iid, event.y)
        return "break"

    def _on_drag(self, event):
        if not self.press:
            return
        if self.dragging is None:
            if abs(event.y - self.press[1]) < 5:           # ignore tiny wobbles
                return
            if self.search.get().strip():
                self.status.config(text="Clear the Search box to reorder.")
                self.press = None
                return
            self.dragging = self.press[0]
            self.tree.config(cursor="fleur")
        over = self.tree.identify_row(event.y)
        if not over and self.files:                        # dragged past the top/bottom
            kids = self.tree.get_children()
            over = kids[0] if event.y < 0 else kids[-1]
        if over and over != self.dragging and over in self.files:
            i, j = self.files.index(self.dragging), self.files.index(over)
            self.files.insert(j, self.files.pop(i))
            self._refresh()

    def _on_release(self, event):
        self.press, self.dragging = None, None
        self.tree.config(cursor="")
        self._refresh()

    def _on_change(self):
        # default the move-folder name to prefix (or suffix) until the user edits it
        if not self.move_name_touched:
            self.move_name.set(self.prefix.get().strip() or self.suffix.get().strip())
        self._refresh()

    def _on_items_change(self):
        mode = self.items.get()
        flt = self.filter.get().strip()
        # sensible default filter for each mode (only if the user left it alone)
        if mode == "Folders" and flt == "*.png":
            self.filter.set("*")
        elif mode != "Folders" and flt == "*":
            self.filter.set("*.png")
        # moving into a new folder only makes sense for files
        folders_listed = mode != "Files"
        if folders_listed:
            self.do_move.set(False)
        self.move_check.config(state="disabled" if folders_listed else "normal")
        if os.path.isdir(self.folder.get().strip()):
            self.load_files()

    def _move_folder(self):
        if self.do_move.get():
            name = self.move_name.get().strip()
            return name or None
        return None

    def _selected(self):
        return [f for f in self.files if self.checked.get(f)]

    def _plan(self):
        return plan_renames(
            self.folder.get().strip(), self._selected(),
            self.prefix.get(), self.suffix.get(),
            self.replace_spaces.get(), self._move_folder(),
            rules=self._rules(), strip_size=self.strip_size.get(),
            capitalise=self.capitalise.get(),
            numbering=self.numbering.get(),
            start=self._int(self.num_start, 1), pad=self._int(self.num_pad, 0),
            keep_order=True,          # numbers follow the list, top to bottom
        )

    @staticmethod
    def _int(var, default):
        try:
            return max(0, int(var.get().strip()))
        except ValueError:
            return default

    def _refresh(self):
        if not self.files and not self.folder.get():
            return
        plan = {os.path.basename(p["src"]): p for p in self._plan()}
        self.tree.delete(*self.tree.get_children())
        for f in self._visible():
            on = self.checked.get(f, False)
            p = plan.get(f)
            kind = ["folder"] if f in self.dirs else []
            if on and p:
                new = p["name"]
                warns = []
                if p["numbered"]:
                    warns.append("⚠ number added (name clash)")
                if p["already_prefixed"]:
                    warns.append("⚠ already has prefix")
                if p["removal_skipped"]:
                    warns.append("⚠ removal skipped (would leave empty name)")
                tags = ("warn",) if warns else ()
                note = "; ".join(kind + warns)
            else:
                new, note, tags = "(unchanged)", "; ".join(kind), ("off",)
            if f == self.dragging:
                tags = tags + ("drag",)
            self.tree.insert("", "end", iid=f,
                             values=(CHECKED if on else UNCHECKED, f, new, note),
                             tags=tags)
        n_sel = len(self._selected())
        self.status.config(text=f"{n_sel} of {len(self.files)} selected")

    def rename(self):
        folder = self.folder.get().strip()
        selected = self._selected()
        if not selected:
            messagebox.showinfo("Rename", "No files are ticked.")
            return
        if not self.prefix.get().strip() and not self.suffix.get().strip() \
                and not self._rules() and not self.strip_size.get() \
                and self.capitalise.get() == "Off" and not self.numbering.get() \
                and not self.replace_spaces.get() and not self._move_folder():
            messagebox.showinfo("Rename", "Nothing to do: enter a prefix/suffix or text "
                                          "to remove, or tick an option.")
            return
        if self.do_move.get() and not self._move_folder():
            messagebox.showwarning("Rename", "Enter a name for the new folder.")
            return
        if not messagebox.askyesno("Confirm", f"Rename {len(selected)} item(s)?"):
            return
        plan = self._plan()
        try:
            done = apply_plan(folder, plan, self._move_folder())
        except Exception as exc:
            messagebox.showerror(
                "Error", f"{exc}\n\nAnything renamed before this error is in the log "
                         "and can be undone. (A folder that is open in another program "
                         "can't be renamed.)")
            self.load_files()
            return

        numbered = [p for p in plan if p["numbered"]]
        msg = f"Renamed {len(done)} item(s)."
        if self._move_folder():
            msg += f"\nMoved into folder: {self._move_folder()}"
        if numbered:
            msg += "\n\nThese names clashed, so a number was added:\n"
            msg += "\n".join(f"  {os.path.basename(p['src'])}  ->  {p['name']}"
                             for p in numbered)
        messagebox.showinfo("Done", msg)
        self.load_files()

    def undo(self):
        folder = self.folder.get().strip()
        if not os.path.isdir(folder):
            messagebox.showwarning("Undo", "Please choose a folder first.")
            return
        try:
            count = undo_last(folder)
        except FileNotFoundError:
            messagebox.showinfo("Undo", "No earlier run to undo for this folder.")
            return
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        messagebox.showinfo("Undo", f"Restored {count} item(s).")
        self.load_files()

    def clear_log(self):
        if not load_history():
            messagebox.showinfo("Log", "The log is already empty.")
            return
        if messagebox.askyesno("Clear log",
                               "Delete the whole rename history?\n"
                               "Earlier runs can no longer be undone afterwards."):
            save_history([])

    def show_log(self):
        win = tk.Toplevel(self.root)
        win.title("Rename log")
        win.geometry("860x540")
        win.transient(self.root)

        ttk.Label(win, text=f"Log file: {LOG_FILE}").pack(anchor="w", padx=8, pady=(8, 0))

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=8, pady=6)
        tree = ttk.Treeview(body, columns=("time", "folder", "files", "status"),
                            show="headings", height=8, selectmode="browse")
        for col, text, width in (("time", "Time", 140), ("folder", "Folder", 440),
                                 ("files", "Items", 60), ("status", "Status", 90)):
            tree.heading(col, text=text)
            tree.column(col, width=width, stretch=(col == "folder"))
        tsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=tsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        tsb.grid(row=0, column=1, sticky="ns")

        detail = tk.Text(body, height=12, wrap="none", state="disabled")
        dsb = ttk.Scrollbar(body, orient="vertical", command=detail.yview)
        detail.configure(yscrollcommand=dsb.set)
        detail.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        dsb.grid(row=1, column=1, sticky="ns", pady=(8, 0))
        body.rowconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)

        runs = {}

        def show_detail(*_):
            text = ""
            sel = tree.selection()
            if sel:
                e = runs[sel[0]]
                lines = [f"Run #{e['id']}  -  {e['time']}", f"Folder: {e['folder']}"]
                if e.get("move_folder"):
                    lines.append(f"Moved into folder: {e['move_folder']}")
                if e.get("undone"):
                    lines.append(f"Undone: {e.get('undone_time', '')}")
                lines.append("")
                numbered = set(e.get("numbered", []))
                for old, new in e["moves"]:
                    mark = "   [number added: name clash]" if new in numbered else ""
                    try:
                        shown = os.path.relpath(new, e["folder"])
                    except ValueError:
                        shown = new
                    lines.append(f"{os.path.basename(old)}  ->  {shown}{mark}")
                text = "\n".join(lines)
            detail.config(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", text)
            detail.config(state="disabled")

        def fill():
            tree.delete(*tree.get_children())
            history = load_history()
            runs.clear()
            runs.update({str(e["id"]): e for e in history})
            for e in reversed(history):
                tree.insert("", "end", iid=str(e["id"]),
                            values=(e["time"], e["folder"], len(e["moves"]),
                                    "Undone" if e.get("undone") else "Active"))
            kids = tree.get_children()
            if kids:
                tree.selection_set(kids[0])
            show_detail()

        def undo_selected():
            sel = tree.selection()
            if not sel:
                return
            e = runs[sel[0]]
            if e.get("undone"):
                messagebox.showinfo("Undo", "This run was already undone.", parent=win)
                return
            if not messagebox.askyesno(
                    "Undo", f"Undo run #{e['id']} ({len(e['moves'])} item(s))?", parent=win):
                return
            try:
                count = undo_run(e["id"])
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=win)
                return
            messagebox.showinfo("Undo", f"Restored {count} item(s).", parent=win)
            fill()
            if os.path.isdir(self.folder.get().strip()):
                self.load_files()

        tree.bind("<<TreeviewSelect>>", show_detail)
        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btns, text="Undo selected run", command=undo_selected).pack(side="left")
        ttk.Button(btns, text="Refresh", command=fill).pack(side="left", padx=6)
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")
        fill()


def main():
    if tk is None:
        raise SystemExit("Tkinter is not available in this Python install.")
    root = tk.Tk()
    RenamerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
