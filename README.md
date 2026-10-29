# Batch Rename & Sort

A pair of lightweight Windows-friendly desktop tools built with **Python 3** and **Tkinter** to help organize files efficiently:

- **Batch File Renamer** — rename selected files or folders using rules, prefixes, suffixes, capitalization, and numbering.
- **Folder Sorter** — move files into folders based on words in their filenames.

Both tools use Python's standard library and include run logs that support undoing previous operations.

## Tools

### 1. Batch File Renamer (`renamer.py`)

Rename multiple files or folders in one batch with a graphical interface.

**Features**
- Browse a folder and filter items using filename patterns such as `*.png` or `*.jpg`.
- Choose to work with files, folders, or both.
- Select individual items, select all, select none, or invert the selection.
- Search the listed items and reorder them by dragging names in the list.
- Remove or replace text in filenames:
  - Anywhere
  - At the start
  - At the end
  - As a whole word
- Add multiple remove/replace rules and apply them in order.
- Optionally remove dimension suffixes such as `_384x256`.
- Add a prefix and/or suffix.
- Replace spaces with underscores.
- Capitalize the first letter of the name or the first letter of each word.
- Number selected items in list order, with a configurable starting number and zero-padding.
- Optionally move renamed files into a new folder.
- Preview the resulting names before applying changes.
- Review the run log and undo a previous run.

**Example**

A set of files such as:

```text
man_idle.png
man_walk.png
man_run.png
```

Can be numbered with the prefix `sprite` to produce names like:

```text
sprite_1.png
sprite_2.png
sprite_3.png
```

The actual numbering follows the displayed list order when the option to preserve the order is enabled; otherwise, items are numbered in natural order (for example, `file2` before `file10`).

### 2. Folder Sorter (`sorter.py`)

Sort loose files into folders based on words in their filenames. The tool moves files; it does not rename them.

**Features**
- Browse a folder and filter files with patterns such as `*.png` or `*.jpg`.
- Define rules that map a filename word to a destination folder.
- Use whole-word matching or match the word anywhere in the filename.
- Apply rules in order: the first matching rule wins.
- Automatically capitalize new folder names, with an option to turn this off.
- Reuse existing destination folders, preserving their existing spelling.
- Fill sorting rules from existing subfolders.
- Optionally include files inside subfolders.
- Choose whether to preserve each file's subfolder structure inside its destination folder or move it directly into the destination folder.
- Preview destinations before moving files.
- Leave files that match no rule in their current locations.
- Automatically add a numeric suffix to avoid destination filename conflicts.
- View the operation log and undo a previous sorting run.

**Example**

Given files such as:

```text
bandit_idle.png
bandit_attack.png
healer_idle.png
```

Rules can route filenames containing `bandit` to a `Bandit` folder and filenames containing `healer` to a `Healer` folder:

```text
Bandit/
├── bandit_idle.png
└── bandit_attack.png

Healer/
└── healer_idle.png
```

The folder names and matching behavior depend on the rules configured in the application.

## Requirements

- Windows or another environment where Python and Tkinter are available.
- Python 3.
- Tkinter, which is included with many standard Python installations.
- No third-party Python packages are required.

The tools use Windows-compatible file operations and should be run in an environment where the selected files and folders are accessible.

## Getting Started

1. Clone or download this repository.
2. Place `renamer.py` and `sorter.py` in the same folder.
3. Run the tool you want to use from a terminal.

### Run the Batch File Renamer

```bash
python renamer.py
```

### Run the Folder Sorter

```bash
python sorter.py
```

## Logs and Undo

Each tool maintains its own JSON log beside its Python script:

- `renamer_log.json` — records rename/move runs made by `renamer.py`.
- `sorter_log.json` — records file-sorting runs made by `sorter.py`.

The logs are created as operations are recorded. Use each application's **Undo last run** option to reverse a logged operation when the required files are still available at the recorded paths.

Do not manually delete or edit a log if you still need its undo history.

## Safe Usage Tips

- **Test on a copy first**, especially when processing many files.
- Review the previewed names or destinations before confirming an operation.
- Check that the correct folder and file filter are selected.
- Keep the JSON logs if you may need to undo a previous run.
- Avoid modifying the same files manually between an operation and its undo, as changes to paths or name conflicts can affect restoration.
- These tools perform real filesystem changes. Undo is based on the recorded operation history and is not a substitute for a backup.

## Project Structure

```text
.
├── renamer.py
├── sorter.py
├── renamer_log.json   # created when the renamer records operations
└── sorter_log.json    # created when the sorter records operations
```

The JSON log files are generated at runtime and do not need to be included in the repository.

## Technology Stack

- Python 3
- Tkinter / ttk
- Standard-library file and path operations
- JSON for operation history

## License

No license has been specified. Add a `LICENSE` file if you intend to allow others to reuse, modify, or distribute this project.
