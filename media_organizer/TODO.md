
# TODO: Media Organizer App Roadmap


## Open Tasks & Suggestions

1. Metadata Date Tag Fallback Logic
   - Goal: When organizing, use the first available date tag from the user’s prioritized list.
   - How: In your controller (not UI), implement a function that, given a metadata dict and a list of tag names, returns the first valid date found. This logic should be unit-testable and reusable.

2. Metadata Preview Display Formatting
   - Goal: Make metadata in the preview tab more readable.
   - How: Format key-value pairs in a table-like or grouped style, highlight important tags, and possibly add a search/filter box for large metadata sets.

3. Unit Tests for Controller & Metadata Parsing
   - Goal: Ensure reliability and catch regressions.
   - How: Add tests in tests/ for:
     - Date tag fallback logic.
     - Duplicate handling.
     - Metadata extraction (mock ExifTool output).

4. Optimize Duplicate Handling Logic
   - Goal: Make file naming for duplicates robust and efficient.
   - How: Refactor duplicate handling into a utility function, ensure it’s thread-safe, and add tests for edge cases (e.g., many duplicates).

5. CLI-Only (Headless) Mode
   - Goal: Allow running the organizer without a GUI for automation or server use.
   - How: Add a CLI entry point (e.g., cli.py) that accepts arguments for source, dest, operation, tags, etc., and calls the same controller logic as the GUI.

6. Config Persistence (JSON or SQLite)
   - Goal: Persist user preferences, last folders, and possibly history.
   - How: Abstract config read/write into a module (e.g., config.py), support both JSON and (optionally) SQLite for more complex state.

7. Date range selection (only organize files within a certain date range)

8. Keyboard shortcuts for main actions

## Completed Tasks

### MVP User App Requirements Checklist

- Select source and destination folders via UI
- Choose between move or copy operation
- Recursively scan for supported image/video formats
- Extract date metadata using ExifTool (with user-configurable tag order)
- Organize files into /YYYY/MM/ subfolders
- Support dry-run/preview mode
- Log all actions and errors to a visible log window
- Progress bar for operation status
- Show current file being processed
- Color-coded log window for info/warning/error
- Disable “Organize” button during processing
- Clear error if ExifTool is missing
- Handle and log errors gracefully (file access, metadata missing, etc.)
- All core logic separated from UI (testable, reusable)
- Easy to add new UI or CLI in the future
- Configurable supported formats in a single place
- README with clear usage instructions
- (Optional for MVP) Show summary dialog at end (files organized, skipped, errors)
- (Optional for MVP) Add a cancel button for long operations

### Refactoring & Modularity

- Refactor all file and path logic to use `pathlib` instead of `os.path`.
- Create `utils.py` for common helpers (e.g., ensure_dir, is_supported_file, date parsing).
- Separate UI logic from core logic (minimize logic in `main.py`).
- Make all core modules callable from both UI and CLI.

### Logging & Usability

- Upgrade `logger.py` to support log levels (info, warning, error) and optional file logging.
- Add a `dry_run` flag to core logic for preview mode (no file operations, just logs what would happen).
- Add clear error if ExifTool is missing at startup.
- Add log window and progress bar to Tkinter UI.

### CLI & Extensibility

- Scaffold a CLI entry point (`cli.py`) for headless/automated use.
- Add a plugin system skeleton (e.g., `plugins/` folder, `IMetadataExtractor` interface).

### Testing & Quality

- Scaffold a `tests/` folder and add basic pytest tests for each module.
- Ensure all modules are importable and testable.

### Async & Scalability

- Consider async/parallel scanning and organizing for large folders.

### Documentation

- Update README with new features, usage, and architecture notes.
- Document plugin system and how to add new format handlers.

### Phase 2: UI/UX Improvements

- Show estimated time remaining for large batches
- Display error/warning summary dialog at the end (e.g., X files organized, Y skipped, Z errors)
- Add a Cancel button to stop processing mid-way
- Remember last used folders (persist to config or use askdirectory initialdir)
- Filter by file type (checkboxes for images/videos)
- Preview mode: show a list of files that will be moved/copied before starting
- Responsive layout (widgets resize with the window)
- About/help dialog with version info and quick usage tips
- Date range selection (only organize files within a certain date range)
- Keyboard shortcuts for main actions
