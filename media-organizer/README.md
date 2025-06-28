# Media Organizer

A modular Python app with a simple Tkinter UI to organize your photos and videos by creation date or metadata. Supports both local and EXE (standalone) usage.


## Features

- Select source and destination folders
- Choose to move or copy files
- Recursively scans for images and videos
- Uses ExifTool to extract creation date metadata (user-configurable tag order)
- Organizes files into /YYYY/MM/ subfolders
- **Preview mode:** See a list of files to be moved/copied before starting
- **Dry-run:** Simulate organization without making changes
- **Cancel button:** Stop processing mid-way
- **Summary dialog:** See organized, skipped, and error files at the end
- **Progress bar, ETA, and color-coded log window**
- **File type filter:** Organize images, videos, or both
- **Remembers last used folders**
- **Responsive layout:** UI resizes with the window
- **About/help dialog**
- **Plugin system:** Easily add new metadata extractors
- **CLI support:** Organize from the command line
- **Testable, modular codebase**


## Supported Formats

- **Images:** .jpg, .jpeg, .png, .cr2, .nef, .arw
- **Videos:** .mp4, .mov, .avi, .mkv


## Usage

### Local Usage

1. Install Python 3.10+ and [ExifTool](https://exiftool.org/) (if not using the bundled EXE).

2. Install dependencies:

   ```sh
   pip install -r requirements.txt
   ```

3. Run the app:

   ```sh
   python app/main.py
   ```

### Standalone EXE

You can build a standalone Windows executable (with ExifTool bundled) using PyInstaller:

1. Ensure ExifTool is present in the `ExifTool/` folder (exiftool.exe).

2. Run the build script:

   ```powershell
   ./build_exe.ps1
   ```

3. The EXE will be in `build_output/media-organizer.exe`.

4. Double-click the EXE to run the app without Python installed.

### CLI

You can also use the CLI for headless/automated organization:

```sh
python cli.py --source <src> --dest <dst> [--move] [--dry-run] [--tags TAG1 TAG2 ...]
```


## Plugin System

The app supports plugins for metadata extraction. To add a new metadata extractor:

1. Create a new Python file in the `plugins/` folder (e.g., `my_extractor.py`).

2. Implement the `IMetadataExtractor` interface:

   ```python
   from plugins.interface import IMetadataExtractor

   class MyExtractor(IMetadataExtractor):
       def extract_datetime(self, file_path):
           # Your custom extraction logic here
           return "2022:01:02 12:00:00"
   ```

3. Register or use your extractor in the app as needed (see `app/metadata_extractor.py` for integration points).

- Plugins allow you to support new file types, custom date logic, or external tools.
- The system is designed for easy extensibility and future plugin discovery/registration.


## Testing

- All core modules are covered by pytest-based tests in the `tests/` folder.

- To run tests:

  ```sh
  cd media-organizer
  python -m pytest
  ```


## Architecture Notes

- Core logic is separated from UI for testability and reuse.
- All file/path logic uses `pathlib`.
- Async/parallel file processing for scalability.
- Easy to add new UI or CLI frontends.


## Notes

- Files without valid date metadata are skipped.
- For best results, run locally or use the standalone EXE build.
- See About/Help in the app for quick usage tips.
