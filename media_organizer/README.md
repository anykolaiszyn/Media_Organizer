# Media Organizer

A modular Python app with a simple Tkinter UI to organize your photos and videos by creation date or metadata. Supports both local and EXE (standalone) usage.

## Features

- Select source and destination folders
- Choose to move or copy files
- Recursively scans for images and videos
- Uses ExifTool to extract creation date metadata (user-configurable tag order, checked case-insensitively)
- Organizes files into `/YYYY/MM/` subfolders
- **Never overwrites or loses a file:** if a destination name is already taken, the existing file's content is compared byte-for-byte — an identical file is skipped, a genuinely different one is kept alongside it as `_1`, `_2`, etc. Safe to re-run against the same source/destination repeatedly (e.g. "migrate once, then top up" workflows) — nothing already organized gets duplicated or clobbered.
- **Chunked, batched metadata extraction:** ExifTool is invoked once per ~200 files rather than once per file, with automatic retry/bisection so one corrupt file can't take down a whole batch.
- **Batch-safe processing:** limits the number of concurrent worker threads (configurable, default 3).
- **Progress bar and ETA:** real-time progress and estimated time remaining for large batches.
- **Summary dialog:** at the end of each batch, a dialog summarizes how many files were organized, skipped (already present), or had errors, with paginated detail available for review and CSV export.
- **Dry-run:** simulate organization without making changes.
- **Cancel button:** stop processing mid-way.
- **File type filter:** organize images, videos, or both.
- **Settings persistence:** source/destination folders, tag order, "use earliest date," and file-type filters are all remembered across restarts.
- **About/help dialog**
- **Plugin interface:** an `IMetadataExtractor` ABC exists for pluggable date-extraction strategies, though nothing currently implements or dispatches through it.
- **CLI support:** organize from the command line.
- **Testable, modular codebase.**

## Supported Formats

A broad set of RAW, common, and legacy image formats, plus the common video container formats. The authoritative list is `media_organizer/app/config.py`'s `IMAGE_FORMATS`/`VIDEO_FORMATS` — check there rather than here, since it's extended more often than this file is updated.

## Usage

### Local Usage

1. Install Python 3.10+ (developed/tested against 3.13) and [ExifTool](https://exiftool.org/) if not using the bundled EXE.

2. Install dependencies:

   ```sh
   pip install psutil
   ```

   (`requirements.txt` lists `tk`, but that's the name of an unrelated PyPI package — Tkinter ships with CPython itself on Windows and doesn't need a separate install.)

3. Run the app from the **repository root** (the directory containing this `media_organizer/` folder — every import in the codebase is fully qualified as `media_organizer.app.X`, which only resolves with the repo root on `sys.path`):

   ```sh
   python -m media_organizer.app.main
   ```

### Standalone EXE

You can build a standalone Windows executable (with ExifTool bundled) using PyInstaller:

1. Ensure ExifTool is present in the `ExifTool/` folder (`exiftool.exe`).

2. From the repository root:

   ```powershell
   pip install pyinstaller
   ./media_organizer/build_exe.ps1
   ```

3. The EXE will be in `build_output/media_organizer.exe`, with the `ExifTool/` folder copied alongside it.

4. Double-click the EXE to run the app without Python installed.

### CLI

You can also use the CLI for headless/automated organization, from the repository root:

```sh
python -m media_organizer.cli --source <src> --dest <dst> [--move] [--dry-run] [--tags TAG1 TAG2 ...]
```

Duplicate handling is automatic and identical to the GUI's — there's no separate flag for it. If the destination folder is nested inside the source folder (or vice versa in the harmful direction), the CLI refuses with a clear error rather than re-scanning its own output on a later run.

## Plugin System

`plugins/interface.py` declares an `IMetadataExtractor` interface for pluggable date-extraction strategies:

```python
from plugins.interface import IMetadataExtractor

class MyExtractor(IMetadataExtractor):
    def extract_datetime(self, file_path):
        return "2022:01:02 12:00:00"
```

No concrete plugin currently exists, and nothing in `app/metadata_extractor.py` dispatches through this interface — it's a declared extension point, not a wired-up mechanism.

## Testing

All core modules are covered by pytest-based tests in `media_organizer/tests/`.

```sh
# from the repository root
python -m pytest
# or, to run a single test:
python -m pytest media_organizer/tests/test_organizer.py::test_name -v
```

## Architecture Notes

- Core logic is separated from the UI for testability and reuse; `app/ui_controller.py`'s `MediaOrganizerController` is the seam between them.
- All file/path logic uses `pathlib`.
- Metadata is extracted in chunks (`app/metadata_extractor.py`'s `extract_metadata_batch`, ~200 files per ExifTool invocation) rather than one process per file, with bisection so a single bad file degrades to a per-file error instead of failing the whole chunk.
- File placement (`app/organizer.py`'s `place_file`) claims destination names atomically and compares content before ever overwriting, so concurrent workers and repeated runs are both safe.
- Batch progress, cancellation, and scan progress are all published as typed events (`app/batch_events.py`) and drained on the Tk main thread via `root.after` — no worker thread touches a widget directly.
- Real-time progress and ETA are calculated from actual per-file completions, not inferred from log text.
- All errors and warnings are logged and summarized at the end of each batch, with a summary dialog for user review and CSV export.

## Notes

- Files without valid date metadata (or whose extraction genuinely failed) are placed in `no_metadata/`; a date that can't be parsed lands in `unsorted/`.
- ExifTool's own "no date" placeholder (`0000:00:00 00:00:00`) is treated the same as a missing date, not a malformed one.
- For best results, run locally or use the standalone EXE build.
- See About/Help in the app for quick usage tips.
