# Media Organizer

Media Organizer sorts a messy folder of photos and videos into a tidy
`YYYY/MM` structure — one folder per year, one subfolder per month — based on
the date each file was actually taken (read from the photo/video's own
metadata, not the file's "date modified"). It's built for anyone with a
Downloads folder, an old phone dump, or a Google Photos/Takeout export full
of thousands of unsorted files.

It never deletes or overwrites anything. If a file with the same name
already exists at the destination, Media Organizer checks whether it's
actually the same file — an exact duplicate is skipped, and a genuinely
different file is kept side-by-side. That means it's safe to run more than
once on the same folders (e.g. to "top up" after adding new photos).

## Getting the app

Media Organizer runs as a single Windows program: **`media_organizer.exe`**,
with an `ExifTool` folder that must stay next to it (it's how the app reads
photo/video dates — nothing else to install). If someone already handed you
a folder containing both, skip ahead to **How to Use**.

To build it yourself from this source folder, see **Building the EXE**
below.

## How to Use

1. Double-click `media_organizer.exe`.
2. Click **Browse** next to **Source Folder** and pick the folder full of
   photos/videos you want to organize (it also looks inside subfolders).
3. Click **Browse** next to **Destination Folder** and pick (or create) the
   folder where the sorted `YYYY/MM` structure should be built.
4. Choose **Move** (files leave the source folder) or **Copy** (source
   folder is left untouched).
5. Optional: use **Dry Run** first — it shows you exactly what *would*
   happen without moving or copying a single file. Good for a first look at
   a folder you've never organized before.
6. Click **Organize**. A progress bar and estimated time remaining appear
   for large batches; click **Cancel** at any time to stop.
7. When it finishes, a summary dialog reports how many files were sorted,
   how many were skipped as duplicates, and whether anything had a problem
   — with a detailed, exportable list if you want to dig in.

**Where things end up if a file has no usable date:** a file with no date
metadata at all goes into a `no_metadata` folder instead of being guessed at
or lost; a file with a date that's present but unreadable goes into
`unsorted`. Both sit inside your destination folder alongside the `YYYY/MM`
folders, so nothing ever just disappears.

**Why some files land in `no_metadata`:** most cameras and phones save the
date a photo was taken directly inside the file. Screenshots, and photos
that have been through Facebook, Messenger, WhatsApp, or similar apps,
often don't have that data anymore — those apps strip it before you
download the file. That's not a bug in Media Organizer; there's no date
left in the file to read.

### Other things worth knowing

- **File types:** a broad set of common photo formats (JPG, PNG, HEIC, most
  camera RAW formats, and more) and video formats (MP4, MOV, AVI, and more).
  You can filter to just images, just videos, or both in the app.
- **Settings are remembered** between runs — your last-used folders, tag
  order, and file-type filter.
- **About/Help** in the app has a quick in-app reminder of all of this.

## Command-Line Use (for automation)

There's also a command-line version, for running Media Organizer without
opening the window — for example, from a scheduled task. It currently
requires Python (see **Running from source** below), rather than being
built into `media_organizer.exe`:

```sh
python -m media_organizer.cli --source <source folder> --dest <destination folder> [--move] [--dry-run] [--tags TAG1 TAG2 ...]
```

Duplicate handling is automatic and identical to the app's — there's no
separate flag for it. If the destination folder is nested inside the source
folder (or vice versa in the harmful direction), the CLI refuses with a
clear error rather than re-scanning its own output on a later run.

---

## Building the EXE

You'll need [Python 3.10+](https://www.python.org/downloads/) (developed
against 3.13) and a copy of [ExifTool](https://exiftool.org/) placed at
`media_organizer/ExifTool/exiftool.exe`.

From the **repository root** (the folder containing this `media_organizer/`
folder):

```powershell
pip install -r media_organizer/requirements.txt
python -m PyInstaller --distpath build_output --workpath .pyi_build --clean media_organizer.spec
```

Then copy the `media_organizer/ExifTool` folder into `build_output/` so it
sits next to the new `media_organizer.exe`. The result in `build_output/` is
the same self-contained pair described above — copy that whole folder
anywhere you like.

## Running from source (developers)

```sh
# GUI
python -m media_organizer.app.main

# CLI
python -m media_organizer.cli --source <src> --dest <dst> [--move] [--dry-run] [--tags TAG1 TAG2 ...]
```

Run these from the **repository root**, not from inside `media_organizer/`
— every import in the codebase is fully qualified as `media_organizer.app.X`,
which only resolves with the repo root on `sys.path`.

### Testing

```sh
# from the repository root
python -m pytest
# or, to run a single test:
python -m pytest media_organizer/tests/test_organizer.py::test_name -v
```

### Plugin System

`plugins/interface.py` declares an `IMetadataExtractor` interface for
pluggable date-extraction strategies:

```python
from plugins.interface import IMetadataExtractor

class MyExtractor(IMetadataExtractor):
    def extract_datetime(self, file_path):
        return "2022:01:02 12:00:00"
```

No concrete plugin currently exists, and nothing in `app/metadata_extractor.py`
dispatches through this interface yet — it's a declared extension point, not
a wired-up mechanism.

### Architecture

See `CLAUDE.md` at the repository root for the full pipeline walkthrough
(scanner → metadata extraction → organizer → UI controller → GUI) and the
Windows-specific subprocess/threading details.
