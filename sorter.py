"""
Folder Sorter
-------------
Sort loose files into folders by a word in their names. It never renames
anything, it only moves files.

  * Rules:  "name contains [word]"  ->  folder [name]   (first matching rule wins)
  * New folders are created capitalised (bandit -> Bandit) unless you untick that.
  * A folder that already exists is reused exactly as spelled, even if the
    letter case differs (rule "bandit" puts files in your existing "Bandit").
  * "Fill rules from existing folders" makes one rule per sub-folder.
  * Files that match no rule stay where they are.
  * "Include sub-folders" also sorts files found inside sub-folders. They keep
    their sub-folder inside the target (south/x.png -> Bandit/south/x.png) or go
    straight into the target folder, as you choose. Files that are already inside
    a target folder are left alone.
  * Every run is logged next to this script (sorter_log.json) and can be undone.

Run:  python sorter.py
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

# Every run is recorded in this one file, next to sorter.py.
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sorter_log.json")
INVALID_CHARS = '\\/:*?"<>|'


# ----------------------------------------------------------------------------
# Core logic (no GUI)
# ----------------------------------------------------------------------------
def _matches_patterns(name, pats):
    return any(fnmatch.fnmatch(name.lower(), p) for p in pats)


def list_files(folder, patterns, recursive=False):
    """
    Files in `folder` whose names match the comma-separated patterns. Returns
    paths relative to `folder`. With recursive=True files inside sub-folders are
    included too (as "sub/name.png"); hidden folders are skipped.
    """
    pats = [p.strip().lower() for p in patterns.split(",") if p.strip()] or ["*"]
    if not recursive:
        try:
            names = sorted(os.listdir(folder), key=str.lower)
        except OSError:
            return []
        return [n for n in names
                if os.path.isfile(os.path.join(folder, n)) and _matches_patterns(n, pats)]
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        rel_root = os.path.relpath(root, folder)
        for name in files:
            if _matches_patterns(name, pats):
                out.append(name if rel_root == "." else os.path.join(rel_root, name))
    return sorted(out, key=str.lower)


def list_subfolders(folder):
    """Names of the visible sub-folders of `folder`."""
    try:
        names = sorted(os.listdir(folder), key=str.lower)
    except OSError:
        return []
    return [n for n in names
            if not n.startswith(".") and os.path.isdir(os.path.join(folder, n))]


def _norm(text):
    """Lower-case, with runs of _ - and spaces treated as one space."""
    return re.sub(r"[_\-\s]+", " ", text.lower()).strip()


def name_matches(filename, word, whole_word=True):
    """
    Does the file name (without extension) contain `word`?
    Ignores capital letters and treats _ - and space alike, so "dark knight"
    matches dark_knight_walk.png. With whole_word the word must be a separate
    word: "rat" matches rat_walk.png but not pirate.png.
    """
    w = _norm(word)
    if not w:
        return False
    stem = _norm(os.path.splitext(filename)[0])
    if whole_word:
        return re.search(r"(?<![^ ])" + re.escape(w) + r"(?![^ ])", stem) is not None
    return w in stem


def auto_folder_name(word, capitalise=True):
    """bandit -> Bandit (or unchanged when capitalise is off)."""
    word = word.strip()
    return word[:1].upper() + word[1:] if capitalise else word


def find_rule(filename, rules):
    """First rule (dict with word, folder, whole) that matches, or None."""
    for rule in rules:
        if name_matches(filename, rule["word"], rule.get("whole", True)):
            return rule
    return None


def in_target_folder(rel, rules):
    """
    True if `rel` (a path below the base folder) already sits inside one of the
    rules' target folders, e.g. Bandit/south/x.png when a rule sends files to
    Bandit. Such files are already sorted and are left alone.
    """
    parts = rel.split(os.sep)
    if len(parts) < 2:
        return False
    return parts[0].lower() in {r["folder"].lower() for r in rules}


def folder_problem(name):
    """Reason a folder name can't be used, or None if it is fine."""
    if not name:
        return "empty folder name"
    if any(c in INVALID_CHARS for c in name):
        return "folder name has characters that aren't allowed"
    if name != name.strip() or name.endswith("."):
        return "folder name can't end with a space or a dot"
    return None


def resolve_folder(base, name):
    """
    Look for an existing entry called `name` in `base`, ignoring letter case.
    Returns (actual_name, kind) where kind is "dir", "file" or "none".
    """
    try:
        entries = os.listdir(base)
    except OSError:
        entries = []
    for entry in entries:
        if entry.lower() == name.lower():
            kind = "dir" if os.path.isdir(os.path.join(base, entry)) else "file"
            return entry, kind
    return name, "none"


def plan_sort(base, selected, rules, keep_structure=True):
    """
    Decide where each selected file goes. `selected` are paths below `base`
    (plain names, or sub/name when sub-folders are included) and `rules` is a
    list of dicts {"word", "folder", "whole"}.
    With keep_structure a file found in a sub-folder keeps that sub-folder inside
    the target folder (south/x.png -> Bandit/south/x.png); otherwise it goes
    straight into the target folder (Bandit/x.png).
    Returns a list of dicts: src, name (path below base), file (just the file
    name), dst (None = stays), rel_dst, folder (target folder), new_folder,
    numbered, error, matched, in_place.
    A file that already exists in the destination gets _1, _2, ...
    """
    base = os.path.abspath(base)
    plan = []
    taken = {}      # destination folder (lower) -> lower-case names already there/planned
    resolved = {}   # requested folder name (lower) -> (actual, kind)
    for rel in selected:
        fname = os.path.basename(rel)
        subdir = os.path.dirname(rel)
        item = {"src": os.path.join(base, rel), "name": rel, "file": fname, "dst": None,
                "rel_dst": None, "folder": None, "new_folder": False, "numbered": False,
                "error": None, "matched": False, "in_place": False}
        plan.append(item)
        if in_target_folder(rel, rules):
            item["in_place"] = True      # already sorted, leave it alone
            continue
        rule = find_rule(fname, rules)
        if rule is None:
            continue
        item["matched"] = True
        problem = folder_problem(rule["folder"])
        if problem:
            item["error"] = problem
            continue
        key = rule["folder"].lower()
        if key not in resolved:
            resolved[key] = resolve_folder(base, rule["folder"])
        actual, kind = resolved[key]
        if kind == "file":
            item["error"] = f"a file called '{actual}' already exists here"
            continue
        item["folder"] = actual
        item["new_folder"] = (kind == "none")
        if keep_structure and subdir:
            dest_dir = os.path.join(base, actual, subdir)
        else:
            dest_dir = os.path.join(base, actual)
        dkey = dest_dir.lower()
        if dkey not in taken:
            taken[dkey] = ({n.lower() for n in os.listdir(dest_dir)}
                           if os.path.isdir(dest_dir) else set())
        names = taken[dkey]
        stem, ext = os.path.splitext(fname)
        candidate, n = fname, 0
        while candidate.lower() in names:
            n += 1
            candidate = f"{stem}_{n}{ext}"
            item["numbered"] = True
        names.add(candidate.lower())
        item["dst"] = os.path.join(dest_dir, candidate)
        item["rel_dst"] = os.path.relpath(item["dst"], base)
    return plan


# ---- history log (next to this script) --------------------------------------
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


def _make_dirs(path):
    """Create `path` and any missing parents. Returns the folders created, parent first."""
    missing = []
    p = path
    while not os.path.isdir(p):
        missing.append(p)
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    created = list(reversed(missing))
    for d in created:
        os.mkdir(d)
    return created


def apply_plan(base, plan):
    """
    Move the files in the plan, creating folders only when a file goes into
    them, and record the run in the log. Returns (done, created) where done is
    a list of (old, new) paths and created the folders that were made. If the
    run stops part-way, what was already moved is still logged.
    """
    base = os.path.abspath(base)
    done, created = [], []
    try:
        for item in plan:
            if not item["dst"] or item["error"]:
                continue
            created.extend(_make_dirs(os.path.dirname(item["dst"])))
            if os.path.exists(item["dst"]):
                raise FileExistsError(f"Target already exists: {item['dst']}")
            shutil.move(item["src"], item["dst"])
            done.append((item["src"], item["dst"]))
    finally:
        if done:
            history = load_history()
            moved_to = {new for _, new in done}
            history.append({
                "id": max((e.get("id", 0) for e in history), default=0) + 1,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "folder": base,
                "created_dirs": created,
                "moves": [[old, new] for old, new in done],
                "numbered": [p["dst"] for p in plan
                             if p["numbered"] and p["dst"] in moved_to],
                "undone": False,
            })
            save_history(history)
        else:
            for d in reversed(created):   # nothing moved, don't leave empty folders behind
                if os.path.isdir(d) and not os.listdir(d):
                    os.rmdir(d)
    return done, created


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
    """Move the files of one logged run back. Returns number of files restored."""
    history = load_history()
    entry = next((e for e in history if e.get("id") == run_id), None)
    if entry is None:
        raise FileNotFoundError("That run is not in the log.")
    if entry.get("undone"):
        raise ValueError("That run was already undone.")
    restored = 0
    for old, new in reversed(entry["moves"]):
        if os.path.exists(new) and not os.path.exists(old):
            os.makedirs(os.path.dirname(old), exist_ok=True)   # in case that folder was removed
            shutil.move(new, old)
            restored += 1
    for d in reversed(entry.get("created_dirs", [])):
        if os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
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
STRUCTURE_CHOICES = ("Keep their sub-folder (Bandit/south/...)",
                     "Straight into the folder (Bandit/...)")


class SorterApp:
    def __init__(self, root):
        self.root = root
        root.title("Folder Sorter")
        root.geometry("900x760")
        root.minsize(760, 640)

        self.folder = tk.StringVar()
        self.filter = tk.StringVar(value="*.png")
        self.search = tk.StringVar()
        self.capitalise = tk.BooleanVar(value=True)
        self.recursive = tk.BooleanVar(value=False)       # include files in sub-folders
        self.structure = tk.StringVar(value=STRUCTURE_CHOICES[0])

        self.rules = []        # rule rows, see _add_rule
        self.files = []        # all filenames in folder matching the filter
        self.checked = {}      # filename -> bool

        self._build_menu()
        self._build_ui()
        self.search.trace_add("write", lambda *a: self._refresh())
        self.capitalise.trace_add("write", lambda *a: self._on_capitalise())
        self.recursive.trace_add("write", lambda *a: self._on_recursive())
        self.structure.trace_add("write", lambda *a: self._refresh())

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
        ttk.Label(top, text="  Filter:").pack(side="left")
        flt = ttk.Entry(top, textvariable=self.filter, width=12)
        flt.pack(side="left", padx=4)
        flt.bind("<Return>", lambda e: self.load_files())
        ttk.Button(top, text="Reload", command=self.load_files).pack(side="left")
        ttk.Checkbutton(top, text="Include sub-folders",
                        variable=self.recursive).pack(side="left", padx=8)

        sel = ttk.Frame(self.root)
        sel.pack(fill="x", **pad)
        ttk.Button(sel, text="Select all", command=lambda: self.set_all(True)).pack(side="left")
        ttk.Button(sel, text="Select none", command=lambda: self.set_all(False)).pack(side="left", padx=4)
        ttk.Button(sel, text="Invert", command=self.invert).pack(side="left")
        ttk.Entry(sel, textvariable=self.search, width=22).pack(side="right")
        ttk.Label(sel, text="Search:").pack(side="right", padx=4)

        mid = ttk.Frame(self.root)
        mid.pack(fill="both", expand=True, **pad)
        cols = ("check", "name", "dest", "note")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="none")
        self.tree.heading("check", text="")
        self.tree.heading("name", text="File")
        self.tree.heading("dest", text="Goes to")
        self.tree.heading("note", text="Note")
        self.tree.column("check", width=34, anchor="center", stretch=False)
        self.tree.column("name", width=250)
        self.tree.column("dest", width=290)
        self.tree.column("note", width=220)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.tag_configure("warn", foreground="#b35c00")
        self.tree.tag_configure("off", foreground="#888888")

        rem = ttk.LabelFrame(self.root, text="Sorting rules (first matching rule wins)")
        rem.pack(fill="x", **pad)
        self.rules_box = ttk.Frame(rem)
        self.rules_box.pack(fill="x", padx=8, pady=(4, 0))
        ttk.Label(self.rules_box, text="Name contains").grid(row=0, column=0, sticky="w")
        ttk.Label(self.rules_box, text="Whole word").grid(row=0, column=1, sticky="w")
        ttk.Label(self.rules_box, text="Folder").grid(row=0, column=3, sticky="w")
        self._add_rule()
        bar = ttk.Frame(rem)
        bar.pack(fill="x", padx=8, pady=(2, 2))
        ttk.Button(bar, text="+ Add rule", command=self._add_rule).pack(side="left")
        ttk.Button(bar, text="Fill rules from existing folders",
                   command=self.fill_from_folders).pack(side="left", padx=8)
        ttk.Checkbutton(bar, text="Capitalise new folder names (Bandit)",
                        variable=self.capitalise).pack(side="left", padx=8)
        bar2 = ttk.Frame(rem)
        bar2.pack(fill="x", padx=8, pady=(0, 2))
        ttk.Label(bar2, text="Files found in sub-folders:").pack(side="left")
        self.structure_combo = ttk.Combobox(bar2, textvariable=self.structure,
                                            values=STRUCTURE_CHOICES, state="disabled",
                                            width=38)
        self.structure_combo.pack(side="left", padx=6)
        ttk.Label(bar2, text='(used when "Include sub-folders" is ticked)').pack(side="left")
        ttk.Label(rem, text="Files that match no rule stay where they are. "
                            "Existing folders are reused as spelled.").pack(
            anchor="w", padx=8, pady=(0, 4))

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", **pad)
        ttk.Button(bottom, text="Sort selected", command=self.sort).pack(side="left")
        ttk.Button(bottom, text="Undo last run", command=self.undo).pack(side="left", padx=8)
        self.status = ttk.Label(bottom, text="Choose a folder to begin.")
        self.status.pack(side="right")

    # ---- rules -------------------------------------------------------------
    def _add_rule(self, word="", folder="", whole=True, touched=False):
        rule = {
            "word": tk.StringVar(value=word),
            "folder": tk.StringVar(value=folder),
            "whole": tk.BooleanVar(value=whole),
            "touched": touched,   # True once the user has typed their own folder name
        }
        box = self.rules_box
        rule["word_entry"] = ttk.Entry(box, textvariable=rule["word"], width=26)
        rule["whole_check"] = ttk.Checkbutton(box, variable=rule["whole"])
        rule["arrow"] = ttk.Label(box, text="→")
        rule["folder_entry"] = ttk.Entry(box, textvariable=rule["folder"], width=26)
        rule["remove"] = ttk.Button(box, text="−", width=3,
                                    command=lambda r=rule: self._remove_rule(r))
        rule["folder_entry"].bind(
            "<KeyRelease>",
            lambda e, r=rule: r.__setitem__("touched", bool(r["folder"].get().strip())))
        rule["word"].trace_add("write", lambda *a, r=rule: self._on_word(r))
        rule["folder"].trace_add("write", lambda *a: self._refresh())
        rule["whole"].trace_add("write", lambda *a: self._refresh())
        self.rules.append(rule)
        self._layout_rules()
        return rule

    def _remove_rule(self, rule, refresh=True):
        if rule in self.rules:
            self.rules.remove(rule)
        for key in ("word_entry", "whole_check", "arrow", "folder_entry", "remove"):
            rule[key].destroy()
        self._layout_rules()
        if refresh:
            self._refresh()

    def _layout_rules(self):
        for row, rule in enumerate(self.rules, start=1):
            rule["word_entry"].grid(row=row, column=0, padx=(0, 6), pady=2)
            rule["whole_check"].grid(row=row, column=1, padx=(0, 6), pady=2)
            rule["arrow"].grid(row=row, column=2, padx=4)
            rule["folder_entry"].grid(row=row, column=3, padx=(0, 6), pady=2)
            rule["remove"].grid(row=row, column=4, pady=2)

    def _on_word(self, rule):
        # until the user types their own folder name, follow the word (capitalised)
        if not rule["touched"]:
            rule["folder"].set(auto_folder_name(rule["word"].get(), self.capitalise.get()))
        self._refresh()

    def _on_capitalise(self):
        for rule in self.rules:
            if not rule["touched"] and rule["word"].get().strip():
                rule["folder"].set(auto_folder_name(rule["word"].get(), self.capitalise.get()))
        self._refresh()

    def _effective_rules(self):
        """Rules that have a word, with the folder name that will really be used."""
        out = []
        for r in self.rules:
            word = r["word"].get().strip()
            if not word:
                continue
            folder = r["folder"].get().strip() or auto_folder_name(word, self.capitalise.get())
            out.append({"word": word, "folder": folder, "whole": r["whole"].get()})
        return out

    def _keep_structure(self):
        return self.structure.get() == STRUCTURE_CHOICES[0]

    def _on_recursive(self):
        self.structure_combo.config(state="readonly" if self.recursive.get() else "disabled")
        if os.path.isdir(self.folder.get().strip()):
            self.load_files()
        else:
            self._refresh()

    def fill_from_folders(self):
        folder = self.folder.get().strip()
        if not os.path.isdir(folder):
            messagebox.showwarning("Folder", "Please choose a folder first.")
            return
        subs = list_subfolders(folder)
        if not subs:
            messagebox.showinfo("Fill rules", "There are no sub-folders in this folder.")
            return
        for rule in [r for r in self.rules if not r["word"].get().strip()]:
            self._remove_rule(rule, refresh=False)       # drop blank rows
        have = {r["folder"].get().strip().lower() for r in self.rules}
        added = 0
        for name in subs:
            if name.lower() in have:
                continue
            self._add_rule(word=name.lower(), folder=name, whole=True, touched=True)
            added += 1
        if not self.rules:
            self._add_rule()
        self._refresh()
        self.status.config(text=f"Added {added} rule(s) from existing folders")

    # ---- actions -----------------------------------------------------------
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
        self.files = list_files(folder, self.filter.get(), self.recursive.get())
        self.checked = {f: True for f in self.files}
        self._refresh()

    def _candidates(self):
        """Listed files, minus those already inside one of the target folders."""
        if not self.recursive.get():
            return list(self.files)
        rules = self._effective_rules()
        return [f for f in self.files if not in_target_folder(f, rules)]

    def _visible(self):
        q = self.search.get().strip().lower()
        return [f for f in self._candidates() if q in f.lower()]

    def set_all(self, state):
        for f in self._visible():
            self.checked[f] = state
        self._refresh()

    def invert(self):
        for f in self._visible():
            self.checked[f] = not self.checked[f]
        self._refresh()

    def _on_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.tree.identify_row(event.y)
        if iid:
            self.checked[iid] = not self.checked.get(iid, False)
            self._refresh()
        return "break"

    def _selected(self):
        return [f for f in self._candidates() if self.checked.get(f)]

    def _plan(self):
        return plan_sort(self.folder.get().strip(), self._selected(),
                         self._effective_rules(), self._keep_structure())

    def _refresh(self):
        if not self.files and not self.folder.get():
            return
        plan = {p["name"]: p for p in self._plan()}
        self.tree.delete(*self.tree.get_children())
        for f in self._visible():
            on = self.checked.get(f, False)
            p = plan.get(f)
            if on and p and p["error"]:
                dest, note, tags = "(skipped)", "⚠ " + p["error"], ("warn",)
            elif on and p and p["dst"]:
                dest = p["rel_dst"].replace(os.sep, "/")
                notes = []
                if p["new_folder"]:
                    notes.append("new folder")
                if p["numbered"]:
                    notes.append("⚠ number added (name clash)")
                note = "; ".join(notes)
                tags = ("warn",) if p["numbered"] else ()
            elif on and p:
                dest, note, tags = "(stays)", "no rule matches", ("off",)
            else:
                dest, note, tags = "(stays)", "", ("off",)
            self.tree.insert("", "end", iid=f,
                             values=(CHECKED if on else UNCHECKED,
                                     f.replace(os.sep, "/"), dest, note),
                             tags=tags)
        moving = sum(1 for p in plan.values() if p["dst"] and not p["error"])
        cands = self._candidates()
        hidden = len(self.files) - len(cands)
        text = f"{len(self._selected())} of {len(cands)} selected, {moving} will move"
        if hidden:
            text += f"  ({hidden} already sorted, hidden)"
        self.status.config(text=text)

    def sort(self):
        folder = self.folder.get().strip()
        if not self._selected():
            messagebox.showinfo("Sort", "No files are ticked.")
            return
        if not self._effective_rules():
            messagebox.showinfo("Sort", "Add at least one rule (a word and a folder).")
            return
        plan = self._plan()
        moving = [p for p in plan if p["dst"] and not p["error"]]
        if not moving:
            messagebox.showinfo("Sort", "None of the ticked files match a rule, "
                                        "so nothing would move.")
            return
        n_folders = len({p["folder"].lower() for p in moving})
        if not messagebox.askyesno(
                "Confirm", f"Move {len(moving)} file(s) into {n_folders} folder(s)?"):
            return
        try:
            done, created = apply_plan(folder, plan)
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            self.load_files()
            return

        unmatched = [p for p in plan if not p["matched"]]
        errors = [p for p in plan if p["error"]]
        numbered = [p for p in plan if p["numbered"] and p["dst"]]
        msg = f"Moved {len(done)} file(s)."
        base = os.path.abspath(folder)
        if created:
            msg += "\n\nNew folders: " + ", ".join(
                os.path.relpath(d, base).replace(os.sep, "/") for d in created)
        if numbered:
            msg += "\n\nThese names clashed, so a number was added:\n"
            msg += "\n".join(f"  {p['name'].replace(os.sep, '/')}  ->  "
                             f"{p['rel_dst'].replace(os.sep, '/')}" for p in numbered)
        if errors:
            msg += "\n\nSkipped:\n" + "\n".join(f"  {p['name']}: {p['error']}" for p in errors)
        if unmatched:
            msg += f"\n\n{len(unmatched)} ticked file(s) matched no rule and stayed."
        # sub-folders that the move left empty are kept (never deleted), but reported
        emptied = sorted({os.path.relpath(os.path.dirname(old), base).replace(os.sep, "/")
                          for old, _ in done
                          if os.path.dirname(old) != base and os.path.isdir(os.path.dirname(old))
                          and not os.listdir(os.path.dirname(old))})
        if emptied:
            msg += "\n\nNow-empty sub-folders (left in place): " + ", ".join(emptied)
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
        messagebox.showinfo("Undo", f"Restored {count} file(s).")
        self.load_files()

    def clear_log(self):
        if not load_history():
            messagebox.showinfo("Log", "The log is already empty.")
            return
        if messagebox.askyesno("Clear log",
                               "Delete the whole sorting history?\n"
                               "Earlier runs can no longer be undone afterwards."):
            save_history([])

    def show_log(self):
        win = tk.Toplevel(self.root)
        win.title("Sorting log")
        win.geometry("860x540")
        win.transient(self.root)

        ttk.Label(win, text=f"Log file: {LOG_FILE}").pack(anchor="w", padx=8, pady=(8, 0))

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=8, pady=6)
        tree = ttk.Treeview(body, columns=("time", "folder", "files", "status"),
                            show="headings", height=8, selectmode="browse")
        for col, text, width in (("time", "Time", 140), ("folder", "Folder", 440),
                                 ("files", "Files", 60), ("status", "Status", 90)):
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
                if e.get("created_dirs"):
                    lines.append("New folders: " + ", ".join(
                        os.path.relpath(d, e["folder"]).replace(os.sep, "/")
                        for d in e["created_dirs"]))
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
                    "Undo", f"Undo run #{e['id']} ({len(e['moves'])} file(s))?", parent=win):
                return
            try:
                count = undo_run(e["id"])
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=win)
                return
            messagebox.showinfo("Undo", f"Restored {count} file(s).", parent=win)
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
    SorterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
