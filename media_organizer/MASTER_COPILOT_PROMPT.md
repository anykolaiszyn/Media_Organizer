# Master GitHub Copilot Prompt: Media Organizer App Refinement & Scaling

## Project Overview
This is a **production-ready Python/Tkinter desktop application** for organizing photos and videos by metadata-extracted dates into chronological folder structures (YYYY/MM/). The app targets **photographers, media specialists, and general desktop users** across Windows, macOS, and Linux.

**Current Status**: Core functionality is robust and stable. The app features a sophisticated GUI, SQLite-backed batch processing, ExifTool integration, and comprehensive error handling. Focus is now on **refinement, polish, and scalability enhancements**.

---

## Architecture & Design Principles

### Current Architecture (Maintain & Enhance)
```
media_organizer/
├── app/
│   ├── main.py                    # Tkinter GUI entry point
│   ├── ui_controller.py           # MVC Controller - core business logic
│   ├── metadata_extractor.py     # ExifTool wrapper & fallback logic
│   ├── organizer.py              # File operations (move/copy/organize)
│   ├── scanner.py                # Recursive file discovery
│   ├── batch_results_db.py       # SQLite persistence for large batches
│   ├── logger.py                 # Centralized logging system
│   ├── config.py                 # Constants & configuration
│   ├── utils.py                  # Helper functions
│   └── exiftool_check.py         # ExifTool validation & path detection
├── tests/                        # Comprehensive test suite
├── ExifTool/                     # Bundled ExifTool executable
└── build_output/                 # PyInstaller executable distribution
```

### Design Philosophy
- **Modular MVC**: Clean separation between UI (view), business logic (controller), and data (model)
- **Local-First**: No Docker, runs natively on desktop environments
- **Cross-Platform**: Windows/macOS/Linux support via native Python and bundled ExifTool
- **Scalable**: Handles thousands of files via SQLite pagination and memory-efficient streaming
- **Extensible**: Plugin-ready architecture for future enhancements
- **User-Friendly**: Comprehensive error handling, progress feedback, and intuitive GUI

---

## Core Functionality (Current Implementation)

### Metadata Extraction Priority (ExifTool-based)
```python
METADATA_FALLBACK_ORDER = [
    "DateTimeOriginal",      # Camera capture time (most reliable)
    "MediaCreateDate",       # Video creation time
    "CreateDate",           # File creation in metadata
    "SubSecDateTimeOriginal", # High-precision capture time
    "TrackCreateDate",      # Video track creation
    "QuickTime:CreationDate", # Apple-specific video metadata
    "ModifyDate",           # Last modification (less reliable)
    "MetadataDate",         # Metadata update timestamp
    "FileCreateDate",       # Filesystem creation (fallback)
    "FileModifyDate"        # Filesystem modification (last resort)
]
```

### Supported File Formats
- **Images**: JPG, JPEG, PNG, CR2, NEF, ARW, DNG, RAF (RAW formats via ExifTool)
- **Videos**: MP4, MOV, AVI, MKV, WEBM, WMV, 3GP

### Key Features
- **Batch Processing**: SQLite-backed pagination for large file sets (10k+ files)
- **Dry Run Mode**: Preview operations before execution
- **Duplicate Handling**: Overwrite, skip, or rename with suffix
- **Progress Tracking**: Real-time progress with ETA and throughput metrics
- **Comprehensive Logging**: Configurable log levels with file output
- **Metadata Viewer**: Tabbed interface to inspect all file metadata
- **Cross-Platform**: Native look-and-feel on all desktop platforms

---

## How to Work With Me (GitHub Copilot Guidelines)

### Collaboration Style
- **Iterative Enhancement**: Suggest specific, focused improvements rather than wholesale rewrites
- **Preserve Architecture**: Respect the existing MVC structure and modular design
- **Code Quality Focus**: Prioritize maintainability, readability, and robust error handling
- **User Experience**: Always consider the end-user impact of changes
- **Performance Awareness**: Consider memory usage and responsiveness for large datasets

### When Suggesting Changes
1. **Explain the WHY**: Describe the problem being solved or improvement being made
2. **Show Before/After**: Clearly indicate what's being changed and why
3. **Consider Dependencies**: Check how changes affect other modules
4. **Test Impact**: Suggest how changes should be tested
5. **Future-Proof**: Consider how changes align with roadmap goals

### Code Standards
- **Type Hints**: Add comprehensive type annotations to new code
- **Error Handling**: Use specific exception types rather than broad `except Exception:`
- **Logging**: Use the established logging system rather than print statements
- **Documentation**: Include docstrings for public methods and complex logic
- **Cross-Platform**: Use `pathlib` and avoid OS-specific code

---

## Current Priority Areas

### 1. Production Stability (HIGH PRIORITY)
**Goal**: Bulletproof error handling and resource management

```python
# IMPROVE: Replace generic exception handling
try:
    result = risky_operation()
except Exception as e:  # TOO BROAD
    log_error(str(e))

# TO: Specific exception handling
try:
    result = risky_operation()
except (FileNotFoundError, PermissionError) as e:
    log_error(f"File access error: {e}")
except subprocess.CalledProcessError as e:
    log_error(f"ExifTool failed: {e}")
except Exception as e:
    log_error(f"Unexpected error: {e}")
    raise  # Re-raise for debugging
```

**Focus Areas**:
- `logger.py` line 16: Specific exception types for file operations
- `utils.py` line 16: Path validation and permission checking
- `ui_controller.py` line 53: Metadata extraction error handling
- Resource cleanup validation on application exit

### 2. Performance & Memory Management (MEDIUM PRIORITY)
**Goal**: Handle 50k+ files efficiently without memory issues

**Current**: SQLite pagination works well, but can be optimized
**Enhance**:
- Memory usage monitoring and warnings
- Streaming file discovery for massive directories
- Progress granularity improvements (files/second, better ETA)

### 3. User Experience Polish (MEDIUM PRIORITY)
**Goal**: Professional, photographer-friendly interface

**Current Needs**:
- Dark mode/theme toggle implementation
- "Retry Failed Files" functionality in batch completion
- Enhanced progress feedback with throughput metrics
- Better error recovery options

### 4. Code Quality & Maintainability (ONGOING)
**Goal**: Clean, well-documented, type-safe codebase

**Actions**:
- Add comprehensive type hints to all modules
- Standardize debug output (remove scattered print statements)
- Input validation for configuration values
- Comprehensive docstring coverage

---

## Future Extensibility Considerations

### Plugin Architecture (Future)
Prepare for extensions like:
- Cloud sync plugins (Google Photos, Dropbox, etc.)
- Analytics dashboard (photo-taking patterns, storage usage)
- Advanced metadata extraction (facial recognition, object detection)
- Export plugins (Lightroom, etc.)

### CLI Mode Support (Roadmap)
Design controller methods to be CLI-callable:
```python
# ui_controller.py methods should work headless
controller = MediaOrganizerController()
result = controller.organize_batch(source, dest, dry_run=False)
```

### Web UI Potential (Future)
Keep business logic separate from Tkinter specifics to enable:
- Flask/FastAPI web interface
- Remote batch management
- Progress monitoring via web dashboard

---

## Development Workflow

### Testing Strategy
- **Unit Tests**: Core logic in `organizer.py`, `metadata_extractor.py`, `scanner.py`
- **Integration Tests**: Full batch workflows with test media files
- **Platform Tests**: Cross-platform file handling and ExifTool integration
- **Performance Tests**: Large dataset handling (memory, speed)

### Build & Distribution
- **PyInstaller**: Create standalone executables for all platforms
- **ExifTool Bundling**: Include ExifTool binaries in distribution
- **Cross-Platform CI**: GitHub Actions for automated testing and builds

### Configuration Management
- **Persistent Settings**: User preferences, last-used folders, metadata priority
- **Environment Variables**: ExifTool path, log levels, performance tuning
- **Config Validation**: Ensure paths exist, values are in range

---

## Immediate Next Steps

1. **Fix Critical Exception Handling**: Replace broad `except Exception:` with specific types
2. **Add Memory Monitoring**: Warn users about massive datasets before processing
3. **Implement Dark Mode**: Theme toggle for better user experience
4. **Enhance Progress Reporting**: Show files/second and more accurate ETAs
5. **Add Retry Functionality**: Allow retrying failed files without full restart

---

## Example Collaboration Pattern

**When I ask for help with error handling:**
```
"I need to improve error handling in metadata_extractor.py. The current 
code catches all exceptions broadly. Help me identify specific exception 
types for ExifTool failures, file access issues, and metadata parsing 
problems. Provide specific exception classes and user-friendly error messages."
```

**When I want UI improvements:**
```
"The progress dialog needs better feedback for large batches. Users want to 
see files/second processing rate and more accurate time remaining. Help me 
enhance the progress reporting in ui_controller.py while maintaining the 
existing threading model."
```

**When working on performance:**
```
"Memory usage grows with very large file sets. Help me add monitoring and 
warnings for datasets over 10k files. Consider streaming approaches that 
work with the existing SQLite pagination system."
```

This prompt ensures we work together efficiently to polish and scale the media organizer into a professional-grade desktop application for photographers and media specialists.
