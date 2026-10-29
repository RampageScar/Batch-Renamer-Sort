# File Organizer Tools

A pair of lightweight Python desktop tools for managing files in batches:

- **Batch File Renamer** — rename selected files or folders using rules, clean up names, or number items in a chosen order.
- **Folder Sorter** — move files into folders based on words in their filenames.

Both tools use a simple graphical interface built with Tkinter and keep a history log so you can review previous operations and undo a run.

## Features

### Batch File Renamer (`renamer.py`)

- Select a folder and filter the list by filename or extension, such as `*.png` or `*.jpg, *.png`.
- Choose to work with **files**, **folders**, or **both**.
- Preview current and proposed names before applying changes.
- Add, remove, or replace text at the start, end, anywhere in the name, or as a whole word.
- Enter multiple search terms in one rule, separated by commas.
- Remove size suffixes such as `_384x256`.
- Replace spaces with underscores and capitalise the first letter or every word.
- Number selected items, with a configurable starting number and zero-padding.
- Drag items to change their order before numbering them.
- Optionally move renamed files into a new folder.
- Review the history log and undo a previous run.

### Folder Sorter (`sorter.py`)

- Sort files into destination folders based on words in their filenames.
- Define rules using a **word** and a **destination folder**; the first matching rule wins.
- Match whole words (for example, `rat` matches `rat_walk.png` but not `pirate.png`) or match a word inside a longer name.
- Automatically capitalise new folder names, or keep the entered spelling.
- Fill rules from existing sub-folders to help organise files into those folders.
- Filter the file list by filename or extension and select which files to sort.
- Optionally include files inside sub-folders and choose whether to preserve their sub-folder structure.
- Leave files that match no rule where they are.
- Reuse existing destination folders and avoid overwriting files when a name already exists.
- Review the history log and undo a previous run.

## Requirements

- Python 3
- Tkinter, which is included with most standard Python installations
- Windows, macOS, or Linux with a graphical desktop environment

No third-party Python packages are required.

## Getting Started

1. Download or clone this repository.
2. Keep `renamer.py` and `sorter.py` in the same project folder.
3. Open a terminal or Command Prompt in that folder.
4. Run the tool you need:

```bash
python renamer.py
```

```bash
python sorter.py
```

On some systems, use `python3` instead of `python`. On Windows, you can also try `py renamer.py` or `py sorter.py`.

## How to Use the Renamer

1. Launch `renamer.py`.
2. Browse to the folder containing the items you want to rename.
3. Choose whether to list files, folders, or both, and set a filter if needed.
4. Tick the items you want to change.
5. Add rename rules and choose any other options, such as replacing spaces or numbering.
6. Check the **New name** column to review the proposed changes.
7. Select **Rename selected** to apply them.
8. Use **Undo last run** or the history log if you need to reverse a run.

**Rule tip:** To add a prefix or suffix, choose **Start** or **End** and leave the **Find** field empty. For example, a Start rule with `sprite_` adds that text to the beginning of the name.

## How to Use the Sorter

1. Launch `sorter.py`.
2. Browse to the folder whose files you want to organise.
3. Set the file filter and select the files to process.
4. Add rules by entering a filename word and the destination folder name.
5. Review the **Goes to** column to see where each selected file will go.
6. If needed, enable **Include sub-folders** and choose how to handle their structure.
7. Select **Sort selected** and confirm the move.
8. Use **Undo last run** or the history log if you need to reverse a run.

**Rule tip:** Rules run from top to bottom. Put more specific rules above broader rules when a filename could match more than one rule.

## History Logs and Undo

Each script creates its own JSON history log next to the script file:

- Renamer: `renamer_log.json`
- Sorter: `sorter_log.json`

The log records completed changes and lets you inspect runs or undo a previous run from the application's **Log** menu. Keep the relevant log file if you want to preserve the ability to undo past operations. Clearing a log removes that recorded history, so the associated runs can no longer be undone through the tool.

## Important Notes

- Review the proposed names or destinations before applying an operation.
- Consider testing with a copy of your files first, especially for large batches.
- Files that match no sorting rule are left where they are.
- If a destination name already exists, the tools add a suffix such as `_1` rather than intentionally overwriting the existing item.
- The logs are stored beside the scripts, not inside the folders being processed.

## Project Structure

```text
file-organizer-tools/
├── README.md
├── renamer.py
├── sorter.py
├── renamer_log.json   # created when the renamer records a run
└── sorter_log.json    # created when the sorter records a run
```

The two log files are generated when needed; you do not need to create them manually.
