# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Tkinter desktop app (+ CLI) that organizes photos/videos into `dest/YYYY/MM/` folders based on date metadata read via a bundled ExifTool executable. Windows-first; ships as a standalone EXE via PyInstaller with ExifTool bundled alongside it.

## Repo layout gotcha

The actual application package is nested one level down: **`media_organizer/`** (containing `app/`, `cli.py`, `plugins/`, `tests/`, `ExifTool/`) sits inside this repo root. `media_organizer/` has no `__init__.py` — it's a namespace package — but every import in the codebase is fully qualified as `media_organizer.app.X`. This only resolves when the **repo root** is on `sys.path`, i.e. commands must be run from the repo root, not from inside `media_organizer/`.

The project is Windows EXE + CLI first: the GUI is what gets packaged into the standalone EXE, and the CLI is the headless/automation path. Running from raw Python source is a developer workflow, not the primary distribution path — see `README.md` (repo root) for the user-facing instructions.

Docker support was explored early in the project's history and deliberately dropped in favor of this local-first, standalone-EXE distribution model (see `media_organizer/TODO.md`'s "Won't fix" section) — don't reintroduce it without discussing first. A handful of stale historical files (old AI-collaboration prompts, a Dockerfile, ad-hoc debug scripts left over from earlier sessions, a `.bak` file, an empty duplicate `.spec` file) were removed as clutter; nothing in the current codebase depends on them.

## Commands

Run from the repo root (`E:\SecretProjects\Media_Organizer-1`):

```sh
# GUI
python -m media_organizer.app.main

# CLI
python -m media_organizer.cli --source <src> --dest <dst> [--move] [--dry-run] [--tags TAG1 TAG2 ...]

# Full test suite
python -m pytest
# or
python run_tests.py

# Single test
python -m pytest media_organizer/tests/test_organizer.py::test_name -v

# Build Windows EXE (PyInstaller + bundles ExifTool/ into build_output/)
media_organizer/build_exe.ps1
```

Useful env vars:
- `MEDIA_ORGANIZER_LOG_LEVEL` — `DEBUG`/`INFO`/`WARNING`/`ERROR` (default `INFO`)
- `MEDIA_ORGANIZER_MAX_WORKERS` — concurrent worker threads placing/copying files during a batch (default 3)
- `MEDIA_ORGANIZER_CHUNK_SIZE` — files per ExifTool invocation during extraction (default 200)
- `MEDIA_ORGANIZER_DEBUG` — when set, re-raises unexpected per-file errors during batch processing instead of just logging them

## Architecture

Pipeline, wired together by `app/ui_controller.py`'s `MediaOrganizerController`:

1. **`app/scanner.py`** — recursively globs the source folder for files matching `app/config.py`'s `SUPPORTED_FORMATS` (image/video extension lists — extend here for new file types).
2. **`app/metadata_extractor.py`** — `extract_metadata_batch(files, chunk_size=None, emit=None)` shells out to the bundled `exiftool.exe` once per chunk (~200 files, `-j -G -a -s`, JSON output; matched back to input paths by the `SourceFile` field, never by list position), not once per file. A chunk that fails outright (timeout, crash, bad JSON) bisects into halves recursively until the one bad file is isolated as a per-file error dict (`{"error": ..., "type": ...}`), so one corrupt file never takes down a whole chunk. `select_datetime`/`select_earliest_datetime` are pure functions that pick a date from an already-fetched metadata dict — exact tag matching (case-insensitive, but never a substring match: requesting `CreateDate` will not silently match `MediaCreateDate`), and ExifTool's own `0000:00:00 00:00:00` "no date" placeholder is filtered out as a candidate, not treated as a real value. `extract_metadata(file_path)` is a thin single-file wrapper over the batch function, kept for the GUI's interactive Metadata Viewer tab. Cancellation reaches a real, currently-running `Popen` via a single registered handle guarded by a lock (`cancel_exiftool()`) — see the TODO.md note on its one known limitation (a chunk already mid-extraction when cancel is pressed still finishes, since a bisection retry after `terminate()` isn't itself cancelled).
3. **`app/organizer.py`** — `organize_files(files, dest_folder, metadata_by_path, ...)` takes a pre-fetched `{path: metadata}` map (never fetches metadata itself) and turns each file's date into a `dest/YYYY/MM/` path via `_destination_for`. `place_file` (the actual move/copy) claims the destination name atomically (`O_CREAT|O_EXCL`, serialized per destination directory via a lock) and compares content byte-for-byte on a name collision: an identical file is skipped (and deleted from the source on Move, since the data demonstrably survives), a genuinely different one is pushed to the next free `_1`, `_2`, ... name. Nothing is ever silently overwritten, and re-running against the same source/dest is idempotent. Files with no date (or a metadata dict carrying an `'error'` key — extraction genuinely failed) go to `no_metadata/`; a date string that fails to parse goes to `unsorted/`.
4. **`app/ui_controller.py`** — `organize_batch` chunks `files` by `MEDIA_ORGANIZER_CHUNK_SIZE`, and for each chunk: calls `extract_metadata_batch` once, then organizes that chunk's files through a `ThreadPoolExecutor` bounded by `MEDIA_ORGANIZER_MAX_WORKERS` before moving to the next chunk. Every file's outcome is written to a per-process temp SQLite DB (`app/batch_results_db.py`, one file at `%TEMP%/media_organizer_batch_<pid>.sqlite3`, guarded by a lock since the connection is shared across worker threads) so the UI can paginate/export results without holding everything in memory; before a batch starts it consults `app/memory_monitor.py` to warn (via a caller-supplied callback) on large (10k+) or massive (50k+) file counts or high memory pressure. Progress, cancellation, and scan status are all published as typed events (`app/batch_events.py`: `Scanned`, `FileStarted`, `FileDone`, `ExtractionProgress`, `LogLine`, `Finished`, plus `Scan*` variants) through a single `emit` callable — the controller has no knowledge of Tk. The aggregation loop never breaks early on cancellation (it drains every submitted future to keep `Finished.counts` accurate — `ThreadPoolExecutor.__exit__` waits for them regardless, so breaking early only loses counts, not time) and uses a one-shot flag so the "cancelled" log line fires once, not once per remaining file.
5. **`app/main.py`** — the GUI backs `emit` with a `queue.Queue`, drained on the Tk main thread via `root.after(100, ...)`. No worker thread touches a widget, a `tk.*Var`, or `messagebox` directly — the one exception (a blocking memory-pressure confirmation dialog) marshals the actual dialog call onto the main thread via `root.after(0, ...)` and has the worker thread block on a `threading.Event` with a 300s timeout.

### Windows subprocess handling

`app/exiftool_check.get_exiftool_path()` resolves the ExifTool path differently depending on whether the app is frozen (`sys.frozen`, PyInstaller build → `ExifTool/` next to the EXE) or running from source (→ `media_organizer/ExifTool/`). Plain ExifTool subprocess calls would flash a console window on Windows; what prevents that is the hidden `STARTUPINFO`/`SW_HIDE` passed on each `subprocess.run` call in `metadata_extractor.py`. That is the only mechanism — keep it on any new ExifTool invocation you add.

`main.py` previously also reassigned `subprocess.Popen`/`run`/`call` globally at import time. That is gone, and must not come back: it sat after the `if __name__ == "__main__"` block so it never applied while the app was running, and because `asyncio.windows_utils` does `class Popen(subprocess.Popen)`, replacing `Popen` with a function made `import asyncio` raise `TypeError` — which aborted pytest collection and meant the suite could not run at all. `tests/test_main_imports.py` guards against regression by importing `main` in a fresh interpreter and asserting the `subprocess` module is unmodified.

### Plugin system

`plugins/interface.py` defines an `IMetadataExtractor` ABC for pluggable date-extraction strategies, per the README's stated design. No concrete plugins exist yet, and nothing in `app/metadata_extractor.py` currently dispatches through this interface — it's a declared extension point, not a wired-up mechanism.

### Logging

`app/logger.py` is a small custom `Logger` (not stdlib `logging`), exposed as the singleton `logger` and the `log` alias (`logger.info`). Level is read from `MEDIA_ORGANIZER_LOG_LEVEL` at construction time. The GUI's log callback buffers/throttles messages (flush every 100ms or every 20 messages) before writing to the on-screen log widget.
