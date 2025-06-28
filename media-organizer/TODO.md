# TODO: Media Organizer App Roadmap

## MVP User App Requirements Checklist
- [x] Select source and destination folders via UI
- [x] Choose between move or copy operation
- [x] Recursively scan for supported image/video formats
- [x] Extract date metadata using ExifTool (with user-configurable tag order)
- [x] Organize files into /YYYY/MM/ subfolders
- [x] Support dry-run/preview mode
- [x] Log all actions and errors to a visible log window
- [x] Progress bar for operation status
- [x] Show current file being processed
- [x] Color-coded log window for info/warning/error
- [x] Disable “Organize” button during processing
- [x] Clear error if ExifTool is missing
- [x] Handle and log errors gracefully (file access, metadata missing, etc.)
- [x] All core logic separated from UI (testable, reusable)
- [x] Easy to add new UI or CLI in the future
- [x] Configurable supported formats in a single place
- [x] Dockerfile for easy cross-platform use
- [x] README with clear usage instructions
- [x] (Optional for MVP) Show summary dialog at end (files organized, skipped, errors)
- [x] (Optional for MVP) Add a cancel button for long operations

## Refactoring & Modularity
- [x] Refactor all file and path logic to use `pathlib` instead of `os.path`.
- [x] Create `utils.py` for common helpers (e.g., ensure_dir, is_supported_file, date parsing).
- [x] Separate UI logic from core logic (minimize logic in `main.py`).
- [x] Make all core modules callable from both UI and CLI.

## Logging & Usability
- [x] Upgrade `logger.py` to support log levels (info, warning, error) and optional file logging.
- [x] Add a `dry_run` flag to core logic for preview mode (no file operations, just logs what would happen).
- [x] Add clear error if ExifTool is missing at startup.
- [x] Add log window and progress bar to Tkinter UI.

## CLI & Extensibility
- [x] Scaffold a CLI entry point (`cli.py`) for headless/automated use.
- [x] Add a plugin system skeleton (e.g., `plugins/` folder, `IMetadataExtractor` interface).

## Testing & Quality
- [x] Scaffold a `tests/` folder and add basic pytest tests for each module.
- [x] Ensure all modules are importable and testable.

## Async & Scalability
- [x] Consider async/parallel scanning and organizing for large folders.

## Documentation
- [x] Update README with new features, usage, and architecture notes.
- [x] Document plugin system and how to add new format handlers.

---

## Phase 2: UI/UX Improvements
- [x] Show estimated time remaining for large batches
- [x] Display error/warning summary dialog at the end (e.g., X files organized, Y skipped, Z errors)
- [x] Add a Cancel button to stop processing mid-way
- [x] Remember last used folders (persist to config or use askdirectory initialdir)
- [x] Filter by file type (checkboxes for images/videos)
- [ ] Date range selection (only organize files within a certain date range)
- [x] Preview mode: show a list of files that will be moved/copied before starting
- [ ] Keyboard shortcuts for main actions
- [x] Responsive layout (widgets resize with the window)
- [x] About/help dialog with version info and quick usage tips
