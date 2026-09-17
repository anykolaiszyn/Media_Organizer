# TODO: Photo & Video Media Organizer App Roadmap

**Status:** Core organize/extract/GUI pipeline was substantially rewritten and verified (unit tests, multi-agent code review, and a real EXE build/launch) — see the commit history and `docs/superpowers/` for the specs, plans, and review findings behind that pass. Items below are what's genuinely still open, not a restatement of what already shipped.

## Open

### Correctness / robustness

- **Cancel doesn't abort in-flight ExifTool extraction.** Clicking Cancel while a chunk is mid-extraction doesn't stop that chunk — `cancel_exiftool()`'s `terminate()` makes the extraction call return normally rather than raising, so the bisection-on-failure logic can't tell "killed by user" from "genuinely failed," and ends up finishing the chunk via new, uncancelled ExifTool calls before the batch loop notices cancellation and stops. No data is lost or corrupted (the batch loop still correctly skips organizing that chunk), but cancellation is only honored *between* chunks, not within one already running. Fixing it properly means threading a cancellation signal through `extract_metadata_batch`'s bisection recursion.
- **Configurable ExifTool timeout.** Currently fixed (chunk timeout scales with chunk size, but the base constants aren't user-configurable). Worth exposing for users with very large or very slow files.

### User experience

- **Dark mode / theme toggle.**
- **"Retry Failed Files" in the summary dialog**, instead of requiring a full re-run (though re-running is now cheap and safe — see below).
- **Batch resume** after an interrupted run. Partially covered already: since re-running is idempotent (already-organized files are recognized and skipped), a naive "just run it again" gets most of the value; a dedicated resume UI would still save the re-scan/re-extraction cost.

### Extensibility

- **Plugin discovery/registration.** `plugins/interface.py` declares `IMetadataExtractor`, but nothing implements or dispatches through it yet — it's a declared extension point, not a working feature.

### Platform

- **Cross-platform testing.** The app and its tests currently assume Windows (hidden-window subprocess flags, `%TEMP%`-based paths, the PyInstaller build targets Windows only). Linux/macOS behavior is unverified.
- **Installer/portable ZIP** for the EXE build, beyond the raw `build_output/` folder.

## Won't fix / not planned

- Docker support was explored early in the project's history and deliberately dropped in favor of a local-first, standalone-EXE distribution model. Don't reintroduce it without discussing first.
