# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Tkinter desktop app (+ CLI) that organizes photos/videos into `dest/YYYY/MM/` folders based on date metadata read via a bundled ExifTool executable. Windows-first; ships as a standalone EXE via PyInstaller with ExifTool bundled alongside it.

## Repo layout gotcha

The actual application package is nested one level down: **`media_organizer/`** (containing `app/`, `cli.py`, `plugins/`, `tests/`, `ExifTool/`) sits inside this repo root. `media_organizer/` has no `__init__.py` — it's a namespace package — but every import in the codebase is fully qualified as `media_organizer.app.X`. This only resolves when the **repo root** is on `sys.path`, i.e. commands must be run from the repo root, not from inside `media_organizer/`.

The repo root also has stray, ad-hoc verification scripts left over from build/debug sessions: `test_final_verification.py`, `test_headless_exiftool.py`, `test_memory.py`, `test_metadata_simple.py`. These are **not** part of the pytest suite (real tests live in `media_organizer/tests/`) — they're manual scripts meant to be run against a built EXE, and at least one (`test_headless_exiftool.py`) has a stale hardcoded path from an earlier clone of this repo (`c:/SecretProjects/Media_Organizer` without the `-1` suffix). Don't treat them as authoritative or wire them into CI.

`DEBUG_CLEANUP_SUMMARY.md` and `TYPE_SAFETY_FIXES.md` are historical change-log docs from past cleanup passes, not living docs — e.g. `TYPE_SAFETY_FIXES.md` describes migrating to the `PyExifTool` library, but the current code in `metadata_extractor.py` shells out to `exiftool.exe` directly via `subprocess.run`. Trust the code over these docs.

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
- `MEDIA_ORGANIZER_MAX_WORKERS` — concurrent ExifTool subprocesses during a batch (default 3)
- `MEDIA_ORGANIZER_DEBUG` — when set, re-raises unexpected per-file errors during batch processing instead of just logging them

## Architecture

Pipeline, wired together by `app/ui_controller.py`'s `MediaOrganizerController`:

1. **`app/scanner.py`** — recursively globs the source folder for files matching `app/config.py`'s `SUPPORTED_FORMATS` (image/video extension lists — extend here for new file types).
2. **`app/metadata_extractor.py`** — shells out to the bundled `exiftool.exe` (`-j -G -a -s`, JSON output) to extract date tags. `extract_datetime` walks a configurable tag-priority list; `extract_earliest_datetime` instead picks the earliest valid date across all given tags. All ExifTool subprocesses are registered in a module-level set so `cancel_exiftool()` can terminate/kill them on user cancel.
3. **`app/organizer.py`** — turns the extracted date into a `dest/YYYY/MM/` path, handles duplicate filenames (`overwrite` vs `preserve` with `_1`, `_2`... suffixes), and does the move/copy or dry-run log line. Files with no date go to `no_metadata/`; files with an unparseable date go to `unsorted/`.
4. **`app/ui_controller.py`** — runs a batch through a `ThreadPoolExecutor` bounded by `MEDIA_ORGANIZER_MAX_WORKERS`, throttling submission (`time.sleep(0.05)` between launches) to avoid spawning too many ExifTool processes at once. Every file's outcome is written to a per-process temp SQLite DB (`app/batch_results_db.py`, one file at `%TEMP%/media_organizer_batch_<pid>.sqlite3`) so the UI can paginate/export results without holding everything in memory; before a batch starts it consults `app/memory_monitor.py` to warn (via a caller-supplied callback) on large (10k+) or massive (50k+) file counts or high memory pressure.

### Windows subprocess handling

`app/exiftool_check.get_exiftool_path()` resolves the ExifTool path differently depending on whether the app is frozen (`sys.frozen`, PyInstaller build → `ExifTool/` next to the EXE) or running from source (→ `media_organizer/ExifTool/`). Plain ExifTool subprocess calls would flash a console window on Windows; what prevents that is the hidden `STARTUPINFO`/`SW_HIDE` passed on each `subprocess.run` call in `metadata_extractor.py`. That is the only mechanism — keep it on any new ExifTool invocation you add.

`main.py` previously also reassigned `subprocess.Popen`/`run`/`call` globally at import time. That is gone, and must not come back: it sat after the `if __name__ == "__main__"` block so it never applied while the app was running, and because `asyncio.windows_utils` does `class Popen(subprocess.Popen)`, replacing `Popen` with a function made `import asyncio` raise `TypeError` — which aborted pytest collection and meant the suite could not run at all. `tests/test_main_imports.py` guards against regression by importing `main` in a fresh interpreter and asserting the `subprocess` module is unmodified.

### Plugin system

`plugins/interface.py` defines an `IMetadataExtractor` ABC for pluggable date-extraction strategies, per the README's stated design. No concrete plugins exist yet, and nothing in `app/metadata_extractor.py` currently dispatches through this interface — it's a declared extension point, not a wired-up mechanism.

### Logging

`app/logger.py` is a small custom `Logger` (not stdlib `logging`), exposed as the singleton `logger` and the `log` alias (`logger.info`). Level is read from `MEDIA_ORGANIZER_LOG_LEVEL` at construction time. The GUI's log callback buffers/throttles messages (flush every 100ms or every 20 messages) before writing to the on-screen log widget.
