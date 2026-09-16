# Chunked ExifTool Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One ExifTool spawn per ~200 files instead of one (or two) per file, exact tag matching, and cancellation that can actually stop an in-flight extraction.

**Architecture:** `metadata_extractor.py` gains a chunked batch-extraction function that bisects on failure so one corrupt file can't take down a whole chunk. `organizer.py` and `cli.py` stop calling ExifTool themselves and instead receive a pre-extracted `{path: metadata}` dict. `ui_controller.py` extracts one chunk, organizes that chunk's files through the existing concurrent worker pool, then moves to the next chunk.

**Tech Stack:** Python 3.13 standard library — `subprocess.Popen`, `json`, `threading`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-16-extraction-performance-design.md`

## Prerequisite

**This plan assumes `docs/superpowers/plans/2026-09-16-batch-events.md` has already been executed and merged.** `organize_batch` in `ui_controller.py` must already be publishing `batch_events` (`Scanned`, `FileStarted`, `FileDone`, `LogLine`, `Finished`) through an `emit` callable before Task 3 below touches it again. If that plan has not landed yet, run it first — do not attempt to merge the two changes into one pass.

## Global Constraints

- Python 3.13. Interpreter at `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`; `python` also resolves on PATH in a fresh terminal.
- Run tests from the **repo root**: `python -m pytest media_organizer/tests -q`.
- No new dependencies.
- `media_organizer/tests/test_metadata_extractor.py` is rewritten in Task 1 of this plan — after that task, it should be fully passing (it currently has 3 pre-existing failures against a module named `exiftool_wrapper` that doesn't exist; those are deleted, not fixed in place). Any *other* file's pre-existing failures are not this plan's concern.
- Never commit `__pycache__/*.pyc`. They are tracked in this repo by mistake; stage source files explicitly, never `git add -A`.
- Metadata dict error shape, used everywhere: `{"error": <str message>, "type": "timeout" | "exiftool_error" | "json_parse_error" | "missing_exiftool"}`.
- Chunk size: `MEDIA_ORGANIZER_CHUNK_SIZE` env var, default `200`. Same resolution pattern as the existing `MEDIA_ORGANIZER_MAX_WORKERS`.

---

### Task 1: Chunked batch extraction, exact tag matching, real cancellation

**Files:**
- Modify: `media_organizer/app/metadata_extractor.py` (near-total rewrite)
- Test: `media_organizer/tests/test_metadata_extractor.py` (replace entirely)

**Interfaces:**
- Consumes: `get_exiftool_path()` from `media_organizer.app.exiftool_check`; `log` from `media_organizer.app.logger`.
- Produces:
  - `extract_metadata_batch(file_paths: list[str], chunk_size: int | None = None, emit=None) -> dict[str, dict]` — keys are the input paths exactly as given (as strings), values are either a real metadata dict or an error dict in the shape above.
  - `extract_metadata(file_path) -> dict` — unchanged signature and return shape from today; implemented as `extract_metadata_batch([str(file_path)], chunk_size=1)[str(file_path)]`.
  - `select_datetime(metadata: dict, tags: list[str] | None = None) -> str | None`.
  - `select_earliest_datetime(metadata: dict, tags: list[str] | None = None) -> str | None`.
  - `cancel_exiftool()` — same name and no-argument signature as today.
  - Emits, if `emit` is given: `ExtractionProgress(chunks_done, chunks_total, files_done, files_total)`, a new dataclass added to `media_organizer/app/batch_events.py`.
  - Deleted: `extract_datetime`, `extract_datetime_with_tags`, `extract_earliest_datetime`, `_register_exiftool_process`, `_unregister_exiftool_process`, `_exiftool_procs`, `_exiftool_lock`.

- [ ] **Step 1: Add the new event type**

In `media_organizer/app/batch_events.py`, add:

```python
@dataclass(frozen=True)
class ExtractionProgress:
    chunks_done: int
    chunks_total: int
    files_done: int
    files_total: int
```

- [ ] **Step 2: Write the failing tests**

Replace the entire contents of `media_organizer/tests/test_metadata_extractor.py`:

```python
"""Batch extraction: one ExifTool call per chunk, exact tag matching, real cancel."""
import json
import subprocess

import pytest

from media_organizer.app import batch_events as ev
from media_organizer.app.metadata_extractor import (
    cancel_exiftool,
    extract_metadata,
    extract_metadata_batch,
    select_datetime,
    select_earliest_datetime,
)


class FakeCompletedProcess:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class FakePopen:
    """Stands in for subprocess.Popen: records the command, answers communicate()."""
    instances = []

    def __init__(self, cmd, stdout=None, stderr=None, text=None, startupinfo=None):
        self.cmd = cmd
        self.returncode = 0
        self.terminated = False
        self.killed = False
        FakePopen.instances.append(self)

    def communicate(self, timeout=None):
        raise NotImplementedError("set via monkeypatch per test")

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def _json_for(paths, extra=None):
    """Build the JSON array ExifTool -j would emit for these paths."""
    extra = extra or {}
    return json.dumps([
        {"SourceFile": p, "DateTimeOriginal": "2024:01:02 03:04:05", **extra.get(p, {})}
        for p in paths
    ])


@pytest.fixture(autouse=True)
def reset_fake_popen():
    FakePopen.instances.clear()
    yield
    FakePopen.instances.clear()


def test_a_healthy_chunk_takes_exactly_one_popen_call(monkeypatch, tmp_path):
    paths = [str(tmp_path / f"{i}.jpg") for i in range(5)]

    def fake_communicate(self, timeout=None):
        return _json_for(paths), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    result = extract_metadata_batch(paths, chunk_size=10)

    assert len(FakePopen.instances) == 1
    assert set(result.keys()) == set(paths)
    assert all("error" not in v for v in result.values())


def test_results_are_matched_by_sourcefile_not_position(monkeypatch, tmp_path):
    paths = [str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg")]

    def fake_communicate(self, timeout=None):
        # Deliberately return them in reverse order.
        return _json_for(list(reversed(paths))), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    result = extract_metadata_batch(paths, chunk_size=10)

    assert result[paths[0]]["SourceFile"] == paths[0]
    assert result[paths[1]]["SourceFile"] == paths[1]


def test_one_bad_file_is_isolated_by_bisection(monkeypatch, tmp_path):
    """A chunk that fails as a whole must not fail every file in it."""
    paths = [str(tmp_path / f"{i}.jpg") for i in range(4)]
    bad = paths[2]

    def fake_communicate(self, timeout=None):
        called_paths = [c for c in self.cmd if c in paths]
        if bad in called_paths and len(called_paths) > 1:
            raise subprocess.TimeoutExpired(cmd=self.cmd, timeout=1)
        if called_paths == [bad]:
            raise subprocess.TimeoutExpired(cmd=self.cmd, timeout=1)
        return _json_for(called_paths), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    result = extract_metadata_batch(paths, chunk_size=10)

    assert len(result) == 4
    assert "error" in result[bad]
    assert result[bad]["type"] == "timeout"
    for p in paths:
        if p != bad:
            assert "error" not in result[p]


def test_bisection_never_runs_two_popens_concurrently(monkeypatch, tmp_path):
    """Cancellation depends on at most one process being in flight at a time.

    Forces full bisection down to single files (any chunk with more than one
    real file path fails) so recursion is actually exercised, then checks no
    two communicate() calls were ever open at once.
    """
    paths = [str(tmp_path / f"{i}.jpg") for i in range(4)]
    concurrent = {"count": 0, "max": 0}

    def fake_communicate(self, timeout=None):
        concurrent["count"] += 1
        concurrent["max"] = max(concurrent["max"], concurrent["count"])
        try:
            real_paths = [c for c in self.cmd if c in paths]
            if len(real_paths) > 1:
                raise subprocess.TimeoutExpired(cmd=self.cmd, timeout=1)
            return _json_for(real_paths), ""
        finally:
            concurrent["count"] -= 1

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    extract_metadata_batch(paths, chunk_size=10)

    assert concurrent["max"] == 1


def test_extraction_progress_is_emitted_per_chunk(monkeypatch, tmp_path):
    paths = [str(tmp_path / f"{i}.jpg") for i in range(6)]

    def fake_communicate(self, timeout=None):
        called_paths = [c for c in self.cmd if c in paths]
        return _json_for(called_paths), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    events = []
    extract_metadata_batch(paths, chunk_size=2, emit=events.append)

    progress = [e for e in events if isinstance(e, ev.ExtractionProgress)]
    assert len(progress) == 3
    assert progress[-1].chunks_done == 3
    assert progress[-1].chunks_total == 3
    assert progress[-1].files_done == 6


def test_cancel_exiftool_terminates_the_registered_process(monkeypatch, tmp_path):
    paths = [str(tmp_path / "a.jpg")]
    registered = {}

    def fake_communicate(self, timeout=None):
        registered['proc'] = self
        cancel_exiftool()
        return _json_for(paths), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    extract_metadata_batch(paths, chunk_size=10)

    assert registered['proc'].terminated is True


def test_extract_metadata_single_file_uses_chunk_size_one(monkeypatch, tmp_path):
    path = str(tmp_path / "a.jpg")

    def fake_communicate(self, timeout=None):
        assert len([c for c in self.cmd if c == path]) == 1
        return _json_for([path]), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    result = extract_metadata(path)

    assert result["SourceFile"] == path


def test_select_datetime_matches_the_exact_tag_only():
    """Regression for the endswith bug: CreateDate must not resolve to MediaCreateDate."""
    metadata = {
        "QuickTime:MediaCreateDate": "2020:01:01 00:00:00",
        "EXIF:CreateDate": "2022:06:15 12:00:00",
    }

    assert select_datetime(metadata, tags=["CreateDate"]) == "2022:06:15 12:00:00"


def test_select_datetime_returns_none_when_nothing_matches():
    assert select_datetime({"EXIF:ModifyDate": "2022:01:01"}, tags=["CreateDate"]) is None


def test_select_earliest_datetime_does_not_double_count_an_exact_match():
    metadata = {"EXIF:CreateDate": "2022:06:15 12:00:00"}

    # A single matching tag must not appear twice and break sorting/selection.
    result = select_earliest_datetime(metadata, tags=["CreateDate"])

    assert result == "2022:06:15 12:00:00"


def test_select_earliest_datetime_picks_the_earliest_across_tags():
    metadata = {
        "EXIF:CreateDate": "2022:06:15 12:00:00",
        "QuickTime:TrackCreateDate": "2020:01:01 00:00:00",
    }

    result = select_earliest_datetime(metadata, tags=["CreateDate", "TrackCreateDate"])

    assert result == "2020:01:01 00:00:00"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest media_organizer/tests/test_metadata_extractor.py -q`

Expected: FAIL, `ImportError: cannot import name 'extract_metadata_batch'`.

- [ ] **Step 4: Rewrite `metadata_extractor.py`**

Replace the entire file:

```python
from pathlib import Path
from .logger import log
import json
import subprocess
import sys
import threading
from media_organizer.app.exiftool_check import get_exiftool_path
from media_organizer.app.batch_events import ExtractionProgress

_current_chunk_process = None
_current_chunk_process_lock = threading.Lock()


def cancel_exiftool():
    global _current_chunk_process
    with _current_chunk_process_lock:
        proc = _current_chunk_process
    if proc is None:
        return
    try:
        proc.terminate()
        log('[CANCEL] ExifTool process terminated by user.')
    except Exception as e:
        log(f'[CANCEL] Failed to terminate ExifTool process: {e}')
        try:
            proc.kill()
            log('[CANCEL] ExifTool process force-killed by user.')
        except Exception as e2:
            log(f'[CANCEL] Failed to force-kill ExifTool process: {e2}')


def _startupinfo():
    if not sys.platform.startswith('win'):
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return info


def _run_chunk(paths, timeout):
    """One ExifTool invocation over `paths`. Returns (json_text_or_None, error_dict_or_None)."""
    global _current_chunk_process
    exiftool_path = get_exiftool_path()
    if not Path(exiftool_path).exists():
        msg = f"ExifTool executable not found at {exiftool_path}"
        return None, {"error": msg, "type": "missing_exiftool"}

    cmd = [exiftool_path, '-j', '-G', '-a', '-s'] + list(paths)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        startupinfo=_startupinfo(),
    )
    with _current_chunk_process_lock:
        _current_chunk_process = proc
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            # Drain any buffered output so the pipes don't leak. Best-effort:
            # a second failure here doesn't change the outcome, which is
            # already "timeout" either way.
            proc.communicate()
        except Exception:
            pass
        msg = f"ExifTool timed out extracting {len(paths)} file(s)"
        return None, {"error": msg, "type": "timeout"}
    finally:
        with _current_chunk_process_lock:
            _current_chunk_process = None

    if proc.returncode != 0:
        msg = stderr.strip() if stderr else f"ExifTool exited with code {proc.returncode}"
        return None, {"error": f"ExifTool returned error: {msg}", "type": "exiftool_error"}

    return stdout, None


def _extract_chunk(paths, timeout, results):
    """Extract `paths` as one chunk, bisecting into results on failure."""
    stdout, error = _run_chunk(paths, timeout)
    if error is not None:
        if len(paths) == 1:
            results[paths[0]] = error
            return
        mid = len(paths) // 2
        _extract_chunk(paths[:mid], timeout, results)
        _extract_chunk(paths[mid:], timeout, results)
        return

    try:
        entries = json.loads(stdout)
    except json.JSONDecodeError as e:
        if len(paths) == 1:
            results[paths[0]] = {
                "error": f"Failed to parse ExifTool JSON output: {e}",
                "type": "json_parse_error",
            }
            return
        mid = len(paths) // 2
        _extract_chunk(paths[:mid], timeout, results)
        _extract_chunk(paths[mid:], timeout, results)
        return

    by_source = {entry.get("SourceFile"): entry for entry in entries}
    for p in paths:
        if p in by_source:
            results[p] = by_source[p]
        else:
            results[p] = {"error": "ExifTool returned no entry for this file",
                          "type": "exiftool_error"}


def extract_metadata_batch(file_paths, chunk_size=None, emit=None):
    """Extract metadata for every path in file_paths, one ExifTool call per chunk.

    Returns {path: metadata_dict_or_error_dict}. A chunk that fails outright
    (bad exit, timeout, unparseable JSON) is bisected until the one bad file
    is isolated as a per-file error; every other file in that chunk still
    gets a real result.
    """
    import os
    if chunk_size is None:
        try:
            chunk_size = int(os.environ.get('MEDIA_ORGANIZER_CHUNK_SIZE', 200))
        except (ValueError, TypeError):
            chunk_size = 200
    chunk_size = max(1, chunk_size)

    file_paths = [str(p) for p in file_paths]
    chunks = [file_paths[i:i + chunk_size] for i in range(0, len(file_paths), chunk_size)]
    results = {}
    files_done = 0

    for i, chunk in enumerate(chunks):
        timeout = 10 + 0.5 * len(chunk)
        _extract_chunk(chunk, timeout, results)
        files_done += len(chunk)
        if emit:
            emit(ExtractionProgress(
                chunks_done=i + 1, chunks_total=len(chunks),
                files_done=files_done, files_total=len(file_paths),
            ))

    return results


def extract_metadata(file_path):
    """Single-file extraction, for the interactive Metadata Viewer tab."""
    path = str(file_path)
    return extract_metadata_batch([path], chunk_size=1)[path]


def _key_matches_tag(key, tag):
    if key == tag:
        return True
    if ':' in key and key.rsplit(':', 1)[-1] == tag:
        return True
    return False


def select_datetime(metadata, tags=None):
    """First tag in priority order that has a value in `metadata`, or None."""
    if tags is None:
        tags = ['DateTimeOriginal', 'CreateDate', 'MediaCreateDate']
    for tag in tags:
        for key, value in metadata.items():
            if _key_matches_tag(key, tag):
                return value
    return None


def select_earliest_datetime(metadata, tags=None):
    """Earliest valid date among all matches for `tags` in `metadata`, or None."""
    from .utils import parse_exif_date
    found = []
    for tag in tags or []:
        for key, value in metadata.items():
            if _key_matches_tag(key, tag):
                dt = parse_exif_date(value)
                if dt:
                    found.append((dt, value))
    if not found:
        return None
    found.sort(key=lambda pair: pair[0])
    return found[0][1]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest media_organizer/tests/test_metadata_extractor.py -q`

Expected: PASS, 11 tests.

- [ ] **Step 6: Commit**

```bash
git add media_organizer/app/metadata_extractor.py media_organizer/app/batch_events.py media_organizer/tests/test_metadata_extractor.py
git commit -m "Extract metadata in chunks with exact tag matching and real cancel"
```

---

### Task 2: `organizer.py` takes metadata instead of fetching it

**Files:**
- Modify: `media_organizer/app/organizer.py`
- Modify: `media_organizer/tests/test_organizer.py`

**Interfaces:**
- Consumes: `select_datetime`, `select_earliest_datetime` from Task 1.
- Produces: `organize_files(files, dest_folder, metadata_by_path, operation='copy', dry_run=False, tag_order=None, use_earliest=False) -> list[tuple[str, Placement]]` — same return shape as today, one new required positional parameter in the middle.
- Removes: `get_organize_preview` (no replacement — dead code, see spec).

- [ ] **Step 1: Write the failing tests**

Replace `media_organizer/tests/test_organizer.py` in full:

```python
from pathlib import Path
from media_organizer.app.organizer import Placement, organize_files
import pytest


def meta_for(path, date_str=None):
    return {path: ({"EXIF:CreateDate": date_str} if date_str else {})}


def test_organize_files_dry_run(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, meta_for(str(f1), '2022:01:02 12:00:00'),
                   operation='copy', dry_run=True)
    dest = tmp_path / '2022' / '01' / 'a.jpg'
    assert not dest.exists()


def test_organize_files_copy(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, meta_for(str(f1), '2022:01:02 12:00:00'),
                   operation='copy', dry_run=False)
    dest = tmp_path / '2022' / '01' / 'a.jpg'
    assert dest.exists()
    assert f1.exists()


def test_organize_files_move(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, meta_for(str(f1), '2022:01:02 12:00:00'),
                   operation='move', dry_run=False)
    dest = tmp_path / '2022' / '01' / 'a.jpg'
    assert dest.exists()
    assert not f1.exists()


def test_organize_files_no_date_goes_to_no_metadata(tmp_path):
    f1 = tmp_path / 'a.bad'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, meta_for(str(f1)), operation='copy', dry_run=False)
    dest = tmp_path / 'no_metadata' / 'a.bad'
    assert dest.exists()


def test_organize_files_is_idempotent_across_runs(tmp_path):
    src = tmp_path / 'src' / 'a.jpg'
    src.parent.mkdir()
    src.write_bytes(b'photo')
    dest = tmp_path / 'lib'
    metadata = meta_for(str(src), '2022:01:02 12:00:00')

    first = organize_files([str(src)], dest, metadata, operation='copy')
    second = organize_files([str(src)], dest, metadata, operation='copy')

    month = dest / '2022' / '01'
    assert [p.name for p in month.iterdir()] == ['a.jpg']
    assert [outcome for _, outcome in first] == [Placement.WROTE]
    assert [outcome for _, outcome in second] == [Placement.SKIPPED_IDENTICAL]


def test_organize_files_keeps_distinct_files_sharing_a_name(tmp_path):
    a = tmp_path / 'one' / 'a.jpg'
    a.parent.mkdir()
    a.write_bytes(b'first photo')
    b = tmp_path / 'two' / 'a.jpg'
    b.parent.mkdir()
    b.write_bytes(b'second photo')
    dest = tmp_path / 'lib'
    metadata = {**meta_for(str(a), '2022:01:02'), **meta_for(str(b), '2022:01:02')}

    organize_files([str(a), str(b)], dest, metadata, operation='copy')

    month = dest / '2022' / '01'
    assert sorted(p.name for p in month.iterdir()) == ['a.jpg', 'a_1.jpg']


def test_organize_files_uses_earliest_when_requested(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    metadata = {str(f1): {
        "EXIF:CreateDate": "2022:06:15",
        "QuickTime:TrackCreateDate": "2020:01:01",
    }}

    organize_files([str(f1)], tmp_path, metadata, operation='copy',
                   tag_order=["CreateDate", "TrackCreateDate"], use_earliest=True)

    assert (tmp_path / '2020' / '01' / 'a.jpg').exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest media_organizer/tests/test_organizer.py -q`

Expected: FAIL — `organize_files() missing 1 required positional argument: 'metadata_by_path'` (today's signature has no such parameter).

- [ ] **Step 3: Rewrite `organizer.py`'s extraction boundary**

In `media_organizer/app/organizer.py`, change the import line from

```python
from .metadata_extractor import extract_datetime
```

to

```python
from .metadata_extractor import select_datetime, select_earliest_datetime
```

Replace `organize_files` and `_destination_for`:

```python
def organize_files(files, dest_folder, metadata_by_path, operation='copy', dry_run=False,
                   tag_order=None, use_earliest=False):
    """File each path under dest_folder/YYYY/MM using its already-extracted metadata.

    Returns a list of (source_path, Placement) so callers can report accurate
    counts instead of inferring them from log text.
    """
    dest_folder = Path(dest_folder)
    results = []
    for file_path in files:
        metadata = metadata_by_path.get(str(file_path), {})
        dest_path = _destination_for(file_path, dest_folder, metadata, tag_order, use_earliest)
        try:
            outcome, final_path = place_file(file_path, dest_path, operation, dry_run)
        except Exception as e:
            logger.error(f"Failed to {operation} {file_path}: {e}")
            continue
        results.append((str(file_path), outcome))
        _log_placement(file_path, final_path, operation, outcome, dry_run)
    return results


def _destination_for(file_path, dest_folder, metadata, tag_order, use_earliest):
    """Where this file belongs: a dated folder, or a fallback bucket."""
    if use_earliest:
        date_str = select_earliest_datetime(metadata, tags=tag_order)
    else:
        date_str = select_datetime(metadata, tags=tag_order)

    name = Path(file_path).name
    if not date_str:
        return dest_folder / "no_metadata" / name
    dt = parse_exif_date(date_str)
    if not dt:
        return dest_folder / "unsorted" / name
    return dest_folder / str(dt.year) / f"{dt.month:02d}" / name
```

Delete `get_organize_preview` entirely — it has no caller.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest media_organizer/tests/test_organizer.py -q`

Expected: PASS, 7 tests.

Do **not** run the full suite as a completion check for this task. `ui_controller.py`'s `organize_one` still calls `organize_files` with the old 3-positional-argument pattern until Task 3 rewrites it — `organize_files`'s new `metadata_by_path` parameter has no default, so that stale call now binds the `operation` string into the `metadata_by_path` slot, and every controller-level test in `test_batch_events.py` that actually reaches `organize_files` will fail with a confusing `AttributeError: 'str' object has no attribute 'get'`. This is expected and temporary, exactly like `main.py` being knowingly broken between Task 1 and Task 4 of the batch-events plan — Task 3 fixes it.

- [ ] **Step 5: Commit**

```bash
git add media_organizer/app/organizer.py media_organizer/tests/test_organizer.py
git commit -m "organize_files takes pre-extracted metadata instead of fetching it"
```

---

### Task 3: Controller extracts a chunk, then organizes it

**Files:**
- Modify: `media_organizer/app/ui_controller.py` (`organize_batch`, `organize_one`)
- Modify: `media_organizer/tests/test_batch_events.py` (extend the `batch` fixture)

**Interfaces:**
- Consumes: `extract_metadata_batch` from Task 1; `organize_files(files, dest, metadata_by_path, ...)` from Task 2; the event-publishing `organize_batch` shape already established by the batch-events plan.
- Produces: no change to `organize_batch`'s external signature. `ExtractionProgress` events now appear in the event stream between `Scanned` and the first `FileDone` of each chunk.

- [ ] **Step 1: Update the shared test fixture for `organize_files`'s new signature**

The batch-events plan's `batch` fixture (already in `media_organizer/tests/test_batch_events.py`) has a `fake_organize` that stands in for `organize_files`. Task 2 inserted `metadata_by_path` as a new third positional parameter, so this fake now binds arguments wrong — the `operation` string would silently land in the `metadata_by_path` slot instead of raising, since `operation` has a default. Fix the fake in place:

```python
    def fake_organize(files, dest_, operation, dry_run=False, tag_order=None, use_earliest=False):
        outcome = by_path[str(files[0])]
        if outcome == 'raise':
            raise OSError("disk on fire")
        return [(str(files[0]), outcome)]
```

becomes

```python
    def fake_organize(files, dest_, metadata_by_path, operation, dry_run=False, tag_order=None,
                      use_earliest=False):
        outcome = by_path[str(files[0])]
        if outcome == 'raise':
            raise OSError("disk on fire")
        return [(str(files[0]), outcome)]
```

(`metadata_by_path` is accepted but unused here — every test using this fixture fakes `organize_files` entirely, so what's actually inside the dict never matters to it.)

- [ ] **Step 2: Write the failing tests**

Append to `media_organizer/tests/test_batch_events.py`:

```python
def test_large_batches_extract_in_chunks_with_accurate_progress(batch, monkeypatch):
    """Progress must reflect the OUTER batch position (chunk 2 of 3, 20 of 25
    files) -- not each extraction call's own view of just its one chunk,
    which is always trivially '1 of 1' since organize_batch calls
    extract_metadata_batch once per outer chunk, never once for everything."""
    monkeypatch.setenv('MEDIA_ORGANIZER_CHUNK_SIZE', '10')
    source, dest = batch([Placement.WROTE] * 25)

    captured_chunk_calls = []

    def spying_extract(paths, chunk_size=None):
        captured_chunk_calls.append(len(paths))
        return {p: {} for p in paths}

    monkeypatch.setattr(
        'media_organizer.app.ui_controller.extract_metadata_batch', spying_extract)

    events = []
    controller = MediaOrganizerController()
    controller.organize_batch(
        source, dest, 'copy', False, None, False, emit=events.append)

    assert captured_chunk_calls == [10, 10, 5]
    progress = [e for e in events if isinstance(e, ev.ExtractionProgress)]
    assert [p.chunks_done for p in progress] == [1, 2, 3]
    assert [p.chunks_total for p in progress] == [3, 3, 3]
    assert [p.files_done for p in progress] == [10, 20, 25]
    assert progress[-1].files_total == 25


def test_cancel_during_organize_stops_before_the_next_chunks_extraction(batch, monkeypatch):
    """Cancel partway through chunk 1's organize phase, not during extraction --
    the real-world timing this guarantee has to hold for."""
    monkeypatch.setenv('MEDIA_ORGANIZER_CHUNK_SIZE', '5')
    source, dest = batch([Placement.WROTE] * 15)
    controller = MediaOrganizerController()

    extraction_calls = []
    organize_calls = []

    def spying_extract(paths, chunk_size=None, emit=None):
        extraction_calls.append(len(paths))
        return {p: {} for p in paths}

    def organize_and_cancel_partway(files, dest_, metadata_by_path, operation, dry_run=False,
                                    tag_order=None, use_earliest=False):
        organize_calls.append(files[0])
        if len(organize_calls) == 3:  # partway through chunk 1's 5 files
            controller.cancel()
        return [(str(files[0]), Placement.WROTE)]

    monkeypatch.setattr(
        'media_organizer.app.ui_controller.extract_metadata_batch', spying_extract)
    monkeypatch.setattr(
        'media_organizer.app.ui_controller.organize_files', organize_and_cancel_partway)

    events = []
    controller.organize_batch(
        source, dest, 'copy', False, None, False, emit=events.append)

    assert extraction_calls == [5], "a second chunk's extraction must not start after cancel"
    finished = [e for e in events if isinstance(e, ev.Finished)][-1]
    assert finished.cancelled is True
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest media_organizer/tests/test_batch_events.py -q -k "chunk or cancel_during"`

Expected: FAIL. Both tests fail with `AttributeError: <module 'media_organizer.app.ui_controller'> has no attribute 'extract_metadata_batch'` — `monkeypatch.setattr` raises it immediately, before either batch runs, since `ui_controller.py` doesn't import that name yet.

- [ ] **Step 4: Rewrite the extraction/organize interleaving in `organize_batch`**

In `media_organizer/app/ui_controller.py`, add to the imports:

```python
from .metadata_extractor import extract_metadata_batch
from .batch_events import ExtractionProgress
```

(Remove the old per-file `from .metadata_extractor import extract_metadata` import that lived inside `organize_one` — it's no longer called there.)

Inside `organize_batch`, after `max_workers = self._resolve_max_workers(max_workers)` and before the `counts = Counter()` line, add:

```python
        import os as _os
        try:
            chunk_size = max(1, int(_os.environ.get('MEDIA_ORGANIZER_CHUNK_SIZE', 200)))
        except (ValueError, TypeError):
            chunk_size = 200
        chunks = [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]
```

Replace the body from `def organize_one(file_path):` through the end of the `with ThreadPoolExecutor(...)` block with:

```python
        def organize_one(file_path, metadata_by_path):
            if self.cancel_flag:
                if self.batch_db is not None:
                    self.batch_db.insert_result(
                        file_path, operation, 'cancelled', {}, error='Batch cancelled')
                return 'cancelled', file_path, None, None

            emit(FileStarted(file_path))
            metadata = metadata_by_path.get(file_path, {})
            error = None
            outcome = None
            if 'error' in metadata:
                status = 'error'
                error = metadata['error']
                emit(LogLine(f"ERROR: {file_path}: {error}"))
            else:
                try:
                    results = organize_files(
                        [file_path], dest, metadata_by_path, operation, dry_run=dry_run,
                        tag_order=tag_order, use_earliest=use_earliest)
                    if results:
                        outcome = results[0][1].value
                        status = outcome
                    else:
                        status = 'error'
                        error = 'File was not placed'
                except Exception as e:
                    error = f"{type(e).__name__}: {e}"
                    status = 'error'
                    emit(LogLine(f"ERROR: {file_path}: {error}"))
                    if _os.environ.get('MEDIA_ORGANIZER_DEBUG'):
                        raise

            if self.batch_db is not None:
                self.batch_db.insert_result(file_path, operation, status, {}, error=error)
            return status, file_path, outcome, error

        files_extracted = 0
        for chunk_index, chunk in enumerate(chunks):
            if self.cancel_flag:
                break
            # Not forwarding `emit` into extract_metadata_batch here: called
            # once per outer chunk, its own internal view is always "chunk 1
            # of 1" -- meaningless for a UI showing progress across the whole
            # batch. Compute that from this loop's own position instead.
            metadata_by_path = extract_metadata_batch(chunk, chunk_size=chunk_size)
            files_extracted += len(chunk)
            emit(ExtractionProgress(
                chunks_done=chunk_index + 1, chunks_total=len(chunks),
                files_done=files_extracted, files_total=total,
            ))
            if self.cancel_flag:
                break
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(organize_one, f, metadata_by_path) for f in chunk]
                for future in as_completed(futures):
                    status, path, outcome, error = future.result()
                    with self._lock:
                        completed += 1
                        counts[status] += 1
                        elapsed = time.time() - start_time
                        eta = int((elapsed / completed) * (total - completed)) if completed else 0
                    emit(FileDone(path, outcome, error, completed, total, eta))
                    if self.cancel_flag:
                        emit(LogLine("Operation cancelled by user."))
                        break
```

Note `organize_files` is now passed the whole chunk's `metadata_by_path`, not a single-entry dict — this matches Task 2's signature, which does its own per-file lookup inside the loop it runs over `files` (here always a one-element list, so behavior is identical to looking up one entry).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest media_organizer/tests -q`

Expected: everything passes. No pre-existing failures should remain at this point — Task 1 already replaced the only file that had any.

- [ ] **Step 6: Commit**

```bash
git add media_organizer/app/ui_controller.py media_organizer/tests/test_batch_events.py
git commit -m "Extract each chunk once, then organize its files"
```

---

### Task 4: CLI extracts once up front

**Files:**
- Modify: `media_organizer/cli.py`

**Interfaces:**
- Consumes: `extract_metadata_batch` from Task 1; `organize_files(files, dest, metadata_by_path, ...)` from Task 2.
- Produces: no change to the CLI's command-line arguments or output.

- [ ] **Step 1: Write the failing test**

Create `media_organizer/tests/test_cli.py`:

```python
"""The CLI extracts metadata once, up front, not once per file inside organize_files."""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_cli_organizes_by_date(tmp_path):
    source = tmp_path / 'src'
    dest = tmp_path / 'lib'
    source.mkdir()
    (source / 'a.jpg').write_bytes(b'not a real jpg, exiftool will find no date tags')

    result = subprocess.run(
        [sys.executable, '-m', 'media_organizer.cli',
         '--source', str(source), '--dest', str(dest)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60,
    )

    assert result.returncode == 0, result.stderr
    # No real date metadata in a fake file -> it lands in no_metadata, proving
    # the run completed rather than crashing on the new organize_files signature.
    assert (dest / 'no_metadata' / 'a.jpg').exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest media_organizer/tests/test_cli.py -q`

Expected: FAIL. The CLI still calls `organize_files(files, args.dest, operation=..., dry_run=..., tag_order=args.tags)` with no `metadata_by_path` argument, so it exits non-zero with a `TypeError` on stderr.

- [ ] **Step 3: Update `cli.py`**

In `media_organizer/cli.py`, change the import line from

```python
from media_organizer.app.organizer import organize_files
```

to

```python
from media_organizer.app.metadata_extractor import extract_metadata_batch
from media_organizer.app.organizer import organize_files
```

and change the extraction/organize call from

```python
    files = scan_media_files(args.source)
    logger.info(f"Found {len(files)} media files.")
    organize_files(
        files,
        args.dest,
        operation='move' if args.move else 'copy',
        dry_run=args.dry_run,
        tag_order=args.tags
    )
```

to

```python
    files = scan_media_files(args.source)
    logger.info(f"Found {len(files)} media files.")
    metadata_by_path = extract_metadata_batch(files)
    organize_files(
        files,
        args.dest,
        metadata_by_path,
        operation='move' if args.move else 'copy',
        dry_run=args.dry_run,
        tag_order=args.tags
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest media_organizer/tests/test_cli.py -q`

Expected: PASS.

Then the full suite: `python -m pytest media_organizer/tests -q`

Expected: everything passes.

- [ ] **Step 5: Commit**

```bash
git add media_organizer/cli.py media_organizer/tests/test_cli.py
git commit -m "CLI extracts metadata once up front instead of once per file"
```

---

## Manual verification after Task 4

```bash
python -m media_organizer.cli --source <folder with 300+ real photos> --dest <empty folder> --dry-run
```

1. Watch the console: there should be a small, countable number of ExifTool-related delays (one pause per ~200 files), not one per file.
2. Time it against how long the same folder took before this plan, if you have that reference point.
3. Run the GUI (`python -m media_organizer.app.main`) against the same folder without `--dry-run` and confirm the summary's organized count matches the file count, and that a second run against the same source/dest reports everything skipped.
