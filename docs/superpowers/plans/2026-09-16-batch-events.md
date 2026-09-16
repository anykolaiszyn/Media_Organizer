# Batch Events and Worker/UI Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make batch progress, ETA and summary counts reflect what actually happened, and stop worker threads from touching Tk.

**Architecture:** `organize_batch` stops calling UI callbacks and instead publishes typed events to a plain `emit` callable. The GUI backs `emit` with a `queue.Queue` and drains it from a `root.after` pump on the main thread, so every widget update happens where Tk requires it. Per-file outcomes (`Placement`, already returned by `organize_files`) are counted into the terminal `Finished` event, replacing regex scraping of log text.

**Tech Stack:** Python 3.13 standard library only — `dataclasses`, `queue`, `threading`, `concurrent.futures`, `tkinter`. pytest for tests. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-09-16-batch-events-design.md`

## Global Constraints

- Python 3.13. Interpreter at `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`; `python` also resolves on PATH in a fresh terminal.
- Run tests from the **repo root** (`E:\SecretProjects\Media_Organizer-1`): `python -m pytest media_organizer/tests -q`. `media_organizer/` is a namespace package with no `__init__.py`, so imports only resolve with the repo root on `sys.path`.
- No new dependencies. Standard library only.
- Windows-first. `tkinter` GUI construction in tests must use a withdrawn root (`root = tk.Tk(); root.withdraw()`) and `root.destroy()` at the end.
- `media_organizer/tests/test_metadata_extractor.py` has **3 pre-existing failures** (stale `exiftool_wrapper` monkeypatch targets). They are unrelated to this work. A run showing `3 failed` and everything else passing is the expected green state. Do not "fix" them in this plan.
- Never commit `__pycache__/*.pyc`. They are tracked in this repo by mistake; stage source files explicitly, never `git add -A`.
- Counter keys are plain strings throughout: `'wrote'`, `'renamed'`, `'skipped_identical'`, `'error'`, `'cancelled'`. Never mix `Placement` enum members with strings as keys.

---

### Task 1: Event types and an event-publishing batch loop

This is the correctness core. It creates the event module as scaffolding, replaces the broken futures gate, honours `max_workers`, and accumulates real counts.

**Files:**
- Create: `media_organizer/app/batch_events.py`
- Modify: `media_organizer/app/ui_controller.py:37-155` (`organize_batch` and its nested `organize_one`)
- Modify: `media_organizer/tests/test_batch_safety.py` (call signature changes)
- Test: `media_organizer/tests/test_batch_events.py` (create)

**Interfaces:**
- Consumes: `Placement` and `organize_files` from `media_organizer.app.organizer`. `organize_files(files, dest, operation, dry_run=False, tag_order=None, use_earliest=False)` returns `list[tuple[str, Placement]]`.
- Produces:
  - `media_organizer.app.batch_events` with `Scanned(total)`, `FileStarted(path)`, `FileDone(path, outcome, error, completed, total, eta_seconds)`, `LogLine(text)`, `Finished(counts, cancelled, elapsed)`.
  - `MediaOrganizerController.organize_batch(source, dest, operation, dry_run, tag_order, use_earliest, formats=None, max_workers=None, emit=None, memory_warning_callback=None)`.
  - `FileDone.outcome` is `Optional[str]` holding a `Placement` **value** (`'wrote'`), not the enum member. This is a deliberate refinement of the spec, which said "`Placement` or `None`": keeping it a string leaves `batch_events` dependency-free and makes it identical to the counter keys.

- [ ] **Step 1: Write the failing tests**

Create `media_organizer/tests/test_batch_events.py`:

```python
"""A batch reports what actually happened, through events only."""
import itertools

import pytest

from media_organizer.app import batch_events as ev
from media_organizer.app.organizer import Placement
from media_organizer.app.ui_controller import MediaOrganizerController


@pytest.fixture
def batch(monkeypatch, tmp_path):
    """Return setup(outcomes) -> (source, dest) with scanning and placing faked.

    Each entry in `outcomes` is either a Placement (what organize_files will
    report for that file) or the string 'raise' (organize_files blows up).
    """
    source = tmp_path / 'src'
    dest = tmp_path / 'lib'
    source.mkdir()

    def setup(outcomes):
        paths = []
        for i, _ in enumerate(outcomes):
            p = source / f'{i}.jpg'
            p.write_bytes(b'x')
            paths.append(str(p))

        monkeypatch.setattr(
            'media_organizer.app.ui_controller.scan_media_files',
            lambda src, formats=None: paths,
        )
        monkeypatch.setattr(
            'media_organizer.app.metadata_extractor.extract_metadata',
            lambda path: {},
        )
        by_path = dict(zip(paths, outcomes))

        def fake_organize(files, dest_, operation, dry_run=False, tag_order=None,
                          use_earliest=False):
            outcome = by_path[str(files[0])]
            if outcome == 'raise':
                raise OSError("disk on fire")
            return [(str(files[0]), outcome)]

        monkeypatch.setattr(
            'media_organizer.app.ui_controller.organize_files', fake_organize)
        return str(source), str(dest)

    return setup


def run_batch(setup, outcomes, **kwargs):
    source, dest = setup(outcomes)
    events = []
    controller = MediaOrganizerController()
    controller.organize_batch(
        source, dest, 'copy', False, None, False,
        emit=events.append, **kwargs
    )
    return events


def test_every_file_is_reported_done(batch):
    """Regression: the old futures gate left completed stuck near max_workers."""
    events = run_batch(batch, [Placement.WROTE] * 25)

    done = [e for e in events if isinstance(e, ev.FileDone)]
    assert len(done) == 25
    assert done[-1].completed == 25
    assert done[-1].total == 25


def test_counts_reflect_real_outcomes(batch):
    events = run_batch(batch, [
        Placement.WROTE, Placement.WROTE, Placement.RENAMED,
        Placement.SKIPPED_IDENTICAL, 'raise',
    ])

    finished = [e for e in events if isinstance(e, ev.Finished)][-1]
    assert finished.counts == {
        'wrote': 2, 'renamed': 1, 'skipped_identical': 1, 'error': 1,
    }


def test_max_workers_argument_beats_the_environment(batch, monkeypatch):
    monkeypatch.setenv('MEDIA_ORGANIZER_MAX_WORKERS', '3')

    events = run_batch(batch, [Placement.WROTE] * 4, max_workers=1)

    lines = [e.text for e in events if isinstance(e, ev.LogLine)]
    assert any('up to 1 ' in text for text in lines), lines


def test_environment_is_used_when_no_argument_given(batch, monkeypatch):
    monkeypatch.setenv('MEDIA_ORGANIZER_MAX_WORKERS', '2')

    events = run_batch(batch, [Placement.WROTE] * 4)

    lines = [e.text for e in events if isinstance(e, ev.LogLine)]
    assert any('up to 2 ' in text for text in lines), lines


def test_scanned_comes_first_and_finished_last(batch):
    events = run_batch(batch, [Placement.WROTE] * 3)

    assert isinstance(events[0], ev.Scanned)
    assert events[0].total == 3
    assert isinstance(events[-1], ev.Finished)
    assert events[-1].cancelled is False


def test_errors_carry_a_message_and_no_outcome(batch):
    events = run_batch(batch, ['raise'])

    done = [e for e in events if isinstance(e, ev.FileDone)][0]
    assert done.outcome is None
    assert 'disk on fire' in done.error
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest media_organizer/tests/test_batch_events.py -q`

Expected: collection error, `ModuleNotFoundError: No module named 'media_organizer.app.batch_events'`. That is the correct first failure — the module does not exist yet.

- [ ] **Step 3: Create the event module**

Create `media_organizer/app/batch_events.py`:

```python
"""Events a batch publishes as it runs.

The controller knows nothing about queues or Tk. It calls a plain `emit`
callable; the GUI backs that with a queue.Queue drained on the main thread,
and tests back it with a list.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Scanned:
    total: int


@dataclass(frozen=True)
class FileStarted:
    path: str


@dataclass(frozen=True)
class FileDone:
    path: str
    outcome: Optional[str]      # a Placement value, or None when errored
    error: Optional[str]
    completed: int
    total: int
    eta_seconds: int


@dataclass(frozen=True)
class LogLine:
    text: str


@dataclass(frozen=True)
class Finished:
    counts: dict
    cancelled: bool
    elapsed: float


@dataclass(frozen=True)
class ScanProgress:
    percent: float


@dataclass(frozen=True)
class ScanFound:
    path: str
    count: int


@dataclass(frozen=True)
class ScanFinished:
    total: int
```

(`ScanProgress` / `ScanFound` / `ScanFinished` are used by Task 3. Defining them here keeps all event types in one module.)

- [ ] **Step 4: Rewrite `organize_batch`**

In `media_organizer/app/ui_controller.py`, add to the imports at the top:

```python
import os
import time
from collections import Counter
from .batch_events import (
    Scanned, FileStarted, FileDone, LogLine, Finished,
)
```

Replace the whole of `organize_batch` (currently lines 37-155) with:

```python
    @staticmethod
    def _resolve_max_workers(requested):
        if requested is None:
            try:
                requested = int(os.environ.get('MEDIA_ORGANIZER_MAX_WORKERS', 3))
            except (ValueError, TypeError):
                requested = 3
        return max(1, requested)

    def organize_batch(self, source, dest, operation, dry_run, tag_order, use_earliest,
                       formats=None, max_workers=None, emit=None,
                       memory_warning_callback=None):
        """Organize files concurrently, publishing progress as events.

        `emit` is called with batch_events objects from both this thread and
        the worker threads, so it must be thread-safe. queue.Queue.put is.
        """
        emit = emit or (lambda event: None)
        check_source_dest_overlap(source, dest)
        self.cancel_flag = False
        if self.batch_db:
            self.batch_db.clear()
        else:
            self.batch_db = BatchResultsDB()

        MemoryMonitor.log_memory_stats("Before scanning")
        files = scan_media_files(source, formats=formats)
        total = len(files)
        emit(Scanned(total))

        if not check_dataset_size_and_warn(total, memory_warning_callback):
            emit(LogLine("Operation cancelled due to dataset size concerns."))
            emit(Finished({}, True, 0.0))
            return

        if total >= MemoryMonitor.LARGE_DATASET_WARNING:
            MemoryMonitor.log_memory_stats(f"After scanning {total:,} files")

        max_workers = self._resolve_max_workers(max_workers)
        emit(LogLine(f"Using up to {max_workers} concurrent workers for batch processing."))

        counts = Counter()
        completed = 0
        start_time = time.time()

        def organize_one(file_path):
            if self.cancel_flag:
                if self.batch_db is not None:
                    self.batch_db.insert_result(
                        file_path, operation, 'cancelled', {}, error='Batch cancelled')
                return 'cancelled', file_path, None, None

            emit(FileStarted(file_path))
            from .metadata_extractor import extract_metadata
            metadata = extract_metadata(file_path)
            error = None
            outcome = None
            try:
                results = organize_files(
                    [file_path], dest, operation, dry_run=dry_run,
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
                if os.environ.get('MEDIA_ORGANIZER_DEBUG'):
                    raise

            if self.batch_db is not None:
                self.batch_db.insert_result(
                    file_path, operation, status, metadata, error=error)
            return status, file_path, outcome, error

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(organize_one, f) for f in files]
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

        if total >= MemoryMonitor.LARGE_DATASET_WARNING:
            MemoryMonitor.log_memory_stats(f"After processing {total:,} files")
            pressure = MemoryMonitor.check_memory_pressure()
            if pressure:
                emit(LogLine(f"[MEMORY WARNING] {pressure}"))

        emit(Finished(dict(counts), self.cancel_flag, time.time() - start_time))
```

Three things this deletes on purpose: the `while len(futures) >= max_workers` gate (it severed futures from `as_completed`), the `time.sleep(0.05)` per submission (`ThreadPoolExecutor` already caps concurrency), and the five near-identical `except` clauses (consolidated, with the exception type preserved in the message).

- [ ] **Step 5: Update `test_batch_safety.py` for the new signature**

In `media_organizer/tests/test_batch_safety.py`, the fake must now return a list of `(path, Placement)`, and the call loses `eta_callback`. Replace `tracked_organize` and the `organize_batch` call with:

```python
    def tracked_organize(files, dest, operation, dry_run=False, tag_order=None,
                         use_earliest=False):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return [(str(files[0]), Placement.WROTE)]
```

```python
            controller.organize_batch(
                str(source), str(dest), 'copy', True, None, False,
                formats=None, max_workers=max_workers,
            )
```

Add the import at the top of that file:

```python
from media_organizer.app.organizer import Placement
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest media_organizer/tests/test_batch_events.py media_organizer/tests/test_batch_safety.py -q`

Expected: PASS, 7 tests in `test_batch_events.py` plus 1 in `test_batch_safety.py`.

Then the full suite: `python -m pytest media_organizer/tests -q`

Expected: `3 failed` (the pre-existing `exiftool_wrapper` ones) and everything else passing. `main.py` still calls the old signature at this point, so the GUI is knowingly broken until Task 4 — that is expected and is why Task 4 must land before any manual GUI check.

- [ ] **Step 7: Commit**

```bash
git add media_organizer/app/batch_events.py media_organizer/app/ui_controller.py media_organizer/tests/test_batch_events.py media_organizer/tests/test_batch_safety.py
git commit -m "Publish batch progress as events and count real outcomes"
```

---

### Task 2: Cancellation reports itself honestly

**Files:**
- Test: `media_organizer/tests/test_batch_events.py` (add)
- Modify: `media_organizer/app/ui_controller.py` (only if the tests fail)

**Interfaces:**
- Consumes: everything Task 1 produced.
- Produces: no new API. Pins the guarantee that `Finished.cancelled` is true after `cancel()` and that the loop stops early.

- [ ] **Step 1: Write the failing tests**

Append to `media_organizer/tests/test_batch_events.py`:

```python
def test_cancel_reports_cancelled_and_stops_early(batch, monkeypatch):
    source, dest = batch([Placement.WROTE] * 30)
    controller = MediaOrganizerController()
    events = []
    seen = itertools.count()

    def cancelling_organize(files, dest_, operation, dry_run=False, tag_order=None,
                            use_earliest=False):
        if next(seen) >= 2:
            controller.cancel()
        return [(str(files[0]), Placement.WROTE)]

    monkeypatch.setattr(
        'media_organizer.app.ui_controller.organize_files', cancelling_organize)

    controller.organize_batch(
        source, dest, 'copy', False, None, False,
        emit=events.append, max_workers=1,
    )

    finished = [e for e in events if isinstance(e, ev.Finished)][-1]
    assert finished.cancelled is True
    assert len([e for e in events if isinstance(e, ev.FileDone)]) < 30


def test_nothing_is_emitted_after_finished(batch):
    events = run_batch(batch, [Placement.WROTE] * 5)

    finished_at = [i for i, e in enumerate(events) if isinstance(e, ev.Finished)]
    assert finished_at == [len(events) - 1]
```

- [ ] **Step 2: Run the tests**

Run: `python -m pytest media_organizer/tests/test_batch_events.py -q -k "cancel or after_finished"`

Expected: both PASS against Task 1's implementation. If either fails, that is a real defect in Task 1's loop — fix `organize_batch`, not the test. The likely culprit would be emitting `Finished` before the memory-warning early return, producing two `Finished` events.

- [ ] **Step 3: Commit**

```bash
git add media_organizer/tests/test_batch_events.py
git commit -m "Pin cancellation semantics for the batch loop"
```

---

### Task 3: Scanning publishes events; remove dead preview code

**Files:**
- Modify: `media_organizer/app/ui_controller.py` (`scan_media_files_async`; delete `get_preview_list`)
- Delete: `media_organizer/tests/test_ui_controller.py`
- Test: `media_organizer/tests/test_batch_events.py` (add)

**Interfaces:**
- Consumes: `ScanProgress`, `ScanFound`, `ScanFinished` from Task 1's module; `scan_media_files_iter(source_folder, formats=None, progress_callback=None, cancel_flag=None)` from `media_organizer.app.scanner`.
- Produces: `MediaOrganizerController.scan_media_files_async(source, formats=None, emit=None)`. It starts a daemon thread and returns immediately. Also: `MediaOrganizerController.__init__(self)` — no longer takes `log_callback`/`progress_callback`. Task 4 already only ever constructs it as `MediaOrganizerController()`.

- [ ] **Step 1: Write the failing test**

Append to `media_organizer/tests/test_batch_events.py`:

```python
def test_async_scan_publishes_found_files_and_a_total(monkeypatch, tmp_path):
    source = tmp_path / 'src'
    source.mkdir()
    for i in range(3):
        (source / f'{i}.jpg').write_bytes(b'x')

    controller = MediaOrganizerController()
    events = []
    done = threading.Event()

    def record(event):
        events.append(event)
        if isinstance(event, ev.ScanFinished):
            done.set()

    controller.scan_media_files_async(str(source), formats=['.jpg'], emit=record)

    assert done.wait(timeout=10), "scan never finished"
    found = [e for e in events if isinstance(e, ev.ScanFound)]
    assert len(found) == 3
    assert [e.count for e in found] == [1, 2, 3]
    assert [e for e in events if isinstance(e, ev.ScanFinished)][-1].total == 3
```

Add `import threading` to that file's imports.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest media_organizer/tests/test_batch_events.py -q -k async_scan`

Expected: FAIL with `TypeError: scan_media_files_async() got an unexpected keyword argument 'emit'`.

- [ ] **Step 3: Rewrite `scan_media_files_async` and delete `get_preview_list`**

In `media_organizer/app/ui_controller.py`, add to the event imports:

```python
from .batch_events import (
    Scanned, FileStarted, FileDone, LogLine, Finished,
    ScanProgress, ScanFound, ScanFinished,
)
```

Replace `scan_media_files_async` with:

```python
    def scan_media_files_async(self, source, formats=None, emit=None):
        """Scan in a background thread, publishing events. Returns immediately."""
        emit = emit or (lambda event: None)
        from .scanner import scan_media_files_iter
        self.cancel_flag = False

        def worker():
            found = 0
            for path in scan_media_files_iter(
                source,
                formats=formats,
                progress_callback=lambda pct: emit(ScanProgress(pct)),
                cancel_flag=lambda: self.cancel_flag,
            ):
                found += 1
                emit(ScanFound(path, found))
            emit(ScanFinished(found))

        threading.Thread(target=worker, daemon=True).start()
```

Delete the entire `get_preview_list` method. Then delete its only caller-free test file:

```bash
git rm media_organizer/tests/test_ui_controller.py
```

If `get_organize_preview` is now unimported in `ui_controller.py`, drop it from the `from .organizer import ...` line, leaving `from .organizer import organize_files`.

That deleted test was the last caller of `MediaOrganizerController(log_callback=logger)`. Task 1's rewrite of `organize_batch` already stopped calling `self._log`/`self._progress`, and this task's rewrite of `scan_media_files_async` never called them either — they were only ever used by the old `organize_batch`. Now that the last external consumer of the constructor's callback form is gone, remove the dead plumbing: change `__init__` to

```python
    def __init__(self):
        self.cancel_flag = False
        self._lock = threading.Lock()
        self.batch_db = None
        atexit.register(BatchResultsDB.cleanup_old_temp_dbs)
```

and delete the `_log` and `_progress` methods entirely.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest media_organizer/tests -q`

Expected: `3 failed` (pre-existing) and everything else passing. `test_ui_controller.py` is gone, so the count drops by one.

- [ ] **Step 5: Commit**

```bash
git add media_organizer/app/ui_controller.py media_organizer/tests/test_batch_events.py
git commit -m "Publish scan progress as events; drop dead preview path"
```

---

### Task 4: Drain events on the Tk main thread

The GUI side. After this task the app runs again.

**Files:**
- Modify: `media_organizer/app/main.py` — `start_organize`, `run_with_summary` (removed), `_log_callback` / `_flush_log_buffer` (removed), `_progress_callback` (removed), `cancel_organize`, `show_summary_dialog`
- Test: `media_organizer/tests/test_ui_pump.py` (create)

**Interfaces:**
- Consumes: all event types; `MediaOrganizerController.organize_batch(..., emit=...)` from Task 1; `check_source_dest_overlap(source, dest)` from `media_organizer.app.utils`, which raises `ValueError`.
- Produces: `MediaOrganizerApp._pump_batch_events()`, `MediaOrganizerApp._on_batch_finished(finished)`, `MediaOrganizerApp._ask_memory_warning(title, message) -> bool`, and `self.summary` as a dict with keys `organized`, `skipped`, `errors`, `cancelled`.

- [ ] **Step 1: Write the failing test**

Create `media_organizer/tests/test_ui_pump.py`:

```python
"""The pump turns events into widget state, on the main thread."""
import queue
import tkinter as tk

import pytest

from media_organizer.app import batch_events as ev
from media_organizer.app.main import MediaOrganizerApp


@pytest.fixture
def app():
    root = tk.Tk()
    root.withdraw()
    instance = MediaOrganizerApp(root)
    yield instance
    root.destroy()


def test_pump_advances_progress_and_current_file(app):
    app.event_queue = queue.Queue()
    app.event_queue.put(ev.Scanned(total=4))
    app.event_queue.put(ev.FileStarted(path='C:/photos/a.jpg'))
    app.event_queue.put(ev.FileDone('C:/photos/a.jpg', 'wrote', None, 1, 4, 30))

    app._pump_batch_events()

    assert app.progress_var.get() == pytest.approx(25.0)
    assert app.current_file_var.get() == 'C:/photos/a.jpg'
    assert 'ETA' in app.eta_var.get()


def test_finished_counts_become_the_summary(app):
    app.event_queue = queue.Queue()
    app.event_queue.put(ev.Finished(
        counts={'wrote': 7, 'renamed': 2, 'skipped_identical': 5, 'error': 1},
        cancelled=False,
        elapsed=12.5,
    ))
    shown = {}
    app.show_summary_dialog = lambda: shown.update(app.summary)

    app._pump_batch_events()

    assert shown == {'organized': 9, 'skipped': 5, 'errors': 1, 'cancelled': 0}


def test_log_lines_reach_the_log_widget(app):
    app.event_queue = queue.Queue()
    app.event_queue.put(ev.LogLine(text='hello from the worker'))

    app._pump_batch_events()

    assert 'hello from the worker' in app.log_window.get('1.0', 'end')
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest media_organizer/tests/test_ui_pump.py -q`

Expected: FAIL with `AttributeError: 'MediaOrganizerApp' object has no attribute '_pump_batch_events'`.

- [ ] **Step 3: Replace the GUI's batch plumbing**

In `media_organizer/app/main.py`, add to the imports at the top:

```python
import queue
import traceback
from media_organizer.app import batch_events as ev
from media_organizer.app.utils import check_source_dest_overlap
```

Delete these three methods entirely: `_log_callback`, `_flush_log_buffer`, `_progress_callback`, and `run_with_summary`. In `__init__`, replace the two callback assignments

```python
        self.log_callback = self._log_callback
        self.progress_callback = self._progress_callback
        self.controller = MediaOrganizerController(self.log_callback, self.progress_callback)
```

with

```python
        self.controller = MediaOrganizerController()
        self.event_queue = queue.Queue()
```

Replace `start_organize`'s body after the existing validation with:

```python
        try:
            check_source_dest_overlap(source, dest)
        except ValueError as e:
            messagebox.showerror("Invalid Folders", str(e))
            return

        self.progress_var.set(0)
        self.eta_var.set("")
        self.current_file_var.set("")
        self.is_processing = True
        self.batch_cancelled = False
        self.organize_btn.config(state='disabled')
        self.cancel_btn.config(state='normal')
        self.summary = {'organized': 0, 'skipped': 0, 'errors': 0, 'cancelled': 0}
        self.event_queue = queue.Queue()

        max_workers = None
        threading.Thread(
            target=self._run_batch,
            args=(source, dest, operation, dry_run, tag_order, formats,
                  max_workers, use_earliest),
            daemon=True,
        ).start()
        self.root.after(100, self._pump_batch_events)
```

Add these four methods:

```python
    def _run_batch(self, source, dest, operation, dry_run, tag_order, formats,
                   max_workers, use_earliest):
        """Runs on a worker thread. Touches no widgets - only the queue."""
        try:
            self.controller.organize_batch(
                source, dest, operation, dry_run, tag_order, use_earliest,
                formats=formats, max_workers=max_workers,
                emit=self.event_queue.put,
                memory_warning_callback=self._ask_memory_warning,
            )
        except Exception as e:
            self.event_queue.put(ev.LogLine(f"[FATAL] {e}\n{traceback.format_exc()}"))
            self.event_queue.put(ev.Finished({'error': 1}, False, 0.0))

    def _pump_batch_events(self):
        """Runs on the Tk main thread. The only place widgets are touched."""
        finished = None
        try:
            while True:
                event = self.event_queue.get_nowait()
                if isinstance(event, ev.Scanned):
                    self.progress_var.set(0)
                    self._append_log(f"Found {event.total} media files.")
                elif isinstance(event, ev.FileStarted):
                    self.current_file_var.set(event.path)
                elif isinstance(event, ev.FileDone):
                    pct = 100 * event.completed / event.total if event.total else 100
                    self.progress_var.set(pct)
                    self.eta_var.set(
                        f"ETA: {event.eta_seconds // 60}m {event.eta_seconds % 60}s"
                        if event.eta_seconds else ""
                    )
                elif isinstance(event, ev.LogLine):
                    self._append_log(event.text)
                elif isinstance(event, ev.Finished):
                    finished = event
        except queue.Empty:
            pass

        if finished is None:
            self.root.after(100, self._pump_batch_events)
        else:
            self._on_batch_finished(finished)

    def _on_batch_finished(self, finished):
        counts = finished.counts
        self.summary = {
            'organized': counts.get('wrote', 0) + counts.get('renamed', 0),
            'skipped': counts.get('skipped_identical', 0),
            'errors': counts.get('error', 0),
            'cancelled': counts.get('cancelled', 0),
        }
        self.batch_cancelled = finished.cancelled
        self.is_processing = False
        self.organize_btn.config(state='normal')
        self.cancel_btn.config(state='disabled')
        self.current_file_var.set("")
        self.eta_var.set("")
        self.progress_var.set(100)
        if self.dry_run_var.get():
            self.show_dry_run_dialog()
        else:
            self.show_summary_dialog()

    def _append_log(self, text):
        self.log_window.config(state='normal')
        self.log_window.insert('end', text + '\n')
        self.log_window.config(state='disabled')
        self.log_window.see('end')

    def _ask_memory_warning(self, title, message):
        """Called from a worker thread; asks on the main thread and waits."""
        answered = threading.Event()
        box = {}

        def ask():
            try:
                box['answer'] = messagebox.askyesno(
                    title, message + "\n\nDo you want to continue with this operation?",
                    icon='warning')
            finally:
                answered.set()

        self.root.after(0, ask)
        if not answered.wait(timeout=300):
            return False
        return box.get('answer', False)
```

In `cancel_organize`, delete the `self.show_summary_dialog()` call — the pump now shows it when `Finished` arrives:

```python
    def cancel_organize(self):
        self.controller.cancel()
        self.cancel_btn.config(state='disabled')
        self.batch_cancelled = True
```

In `show_summary_dialog`, extend the message to include cancellations:

```python
        msg = (f"Files organized: {self.summary['organized']}\n"
               f"Files skipped: {self.summary['skipped']}\n"
               f"Errors: {self.summary['errors']}\n"
               f"Cancelled: {self.summary['cancelled']}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest media_organizer/tests/test_ui_pump.py -q`

Expected: PASS, 3 tests.

Then: `python -m pytest media_organizer/tests -q`

Expected: `3 failed` (pre-existing) and everything else passing.

- [ ] **Step 5: Verify the GUI still constructs**

Run:

```bash
python -c "import tkinter as tk; from media_organizer.app.main import MediaOrganizerApp; r=tk.Tk(); r.withdraw(); a=MediaOrganizerApp(r); print('organize_btn', a.organize_btn.cget('text')); print('pump', hasattr(a,'_pump_batch_events')); r.destroy()"
```

Expected: `organize_btn Organize` and `pump True`.

- [ ] **Step 6: Commit**

```bash
git add media_organizer/app/main.py media_organizer/tests/test_ui_pump.py
git commit -m "Drain batch events on the Tk main thread"
```

---

### Task 5: The scan dialog stops writing to widgets from a worker

**Files:**
- Modify: `media_organizer/app/main.py:105-147` (`scan_files_dialog`)
- Test: `media_organizer/tests/test_ui_pump.py` (add)

**Interfaces:**
- Consumes: `scan_media_files_async(source, formats=None, emit=None)` from Task 3; `ScanProgress`, `ScanFound`, `ScanFinished`.
- Produces: no external API. `scan_files_dialog` gains a local queue and a local pump closure.

- [ ] **Step 1: Write the failing test**

Append to `media_organizer/tests/test_ui_pump.py`:

```python
def test_scan_dialog_uses_a_queue_not_direct_callbacks(app, monkeypatch):
    """scan_media_files_async must be handed an emit, never widget callbacks."""
    captured = {}

    def fake_async(source, formats=None, emit=None):
        captured['emit'] = emit
        captured['source'] = source

    monkeypatch.setattr(app.controller, 'scan_media_files_async', fake_async)
    # scan_files_dialog imports Toplevel locally, so there is no module-level
    # name to patch. Patch the real tkinter class instead: wait_window() runs
    # its own nested Tcl event loop and blocks until the window is destroyed
    # regardless of whether mainloop() was ever called, so leaving it
    # unpatched would hang this test forever.
    monkeypatch.setattr(tk.Toplevel, 'wait_window', lambda self: None)
    app.source_var.set('C:/photos')

    app.scan_files_dialog()

    assert callable(captured['emit'])
    assert captured['source'] == 'C:/photos'
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest media_organizer/tests/test_ui_pump.py -q -k scan_dialog`

Expected: FAIL with `TypeError: fake_async() got an unexpected keyword argument 'progress_callback'`.

- [ ] **Step 3: Rewrite `scan_files_dialog`**

Replace the body of `scan_files_dialog` in `media_organizer/app/main.py` with:

```python
    def scan_files_dialog(self):
        from tkinter import Toplevel, Label, Button
        win = Toplevel(self.root)
        win.title("Scanning Files")
        win.geometry("500x300")
        progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(win, variable=progress_var, maximum=100).pack(
            fill='x', padx=10, pady=10)
        found_label = Label(win, text="Files found: 0")
        found_label.pack(padx=10, anchor='w')
        st = scrolledtext.ScrolledText(win, width=60, height=10)
        st.pack(padx=10, pady=5, fill='both', expand=True)
        cancel_btn = Button(win, text="Cancel")
        cancel_btn.pack(pady=5)

        events = queue.Queue()
        state = {'open': True}

        def close():
            state['open'] = False
            self.controller.cancel()
            win.destroy()

        cancel_btn.config(command=close)
        win.protocol("WM_DELETE_WINDOW", close)

        def pump():
            if not state['open']:
                return
            try:
                while True:
                    event = events.get_nowait()
                    if isinstance(event, ev.ScanProgress):
                        progress_var.set(event.percent)
                    elif isinstance(event, ev.ScanFound):
                        found_label.config(text=f"Files found: {event.count}")
                        if event.count <= 100:
                            st.insert('end', event.path + '\n')
                        elif event.count == 101:
                            st.insert('end', '... (showing first 100)\n')
                    elif isinstance(event, ev.ScanFinished):
                        progress_var.set(100)
                        found_label.config(text=f"Files found: {event.total}")
                        cancel_btn.config(text="Close")
                        return
            except queue.Empty:
                pass
            win.after(100, pump)

        self.controller.scan_media_files_async(
            self.source_var.get(), formats=None, emit=events.put)
        win.after(100, pump)
        win.transient(self.root)
        win.grab_set()
        win.wait_window()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest media_organizer/tests -q`

Expected: `3 failed` (pre-existing) and everything else passing.

- [ ] **Step 5: Confirm no worker thread can reach Tk**

Run: `grep -n "root.after\|win.after" media_organizer/app/main.py`

Every widget mutation during a batch or scan must sit inside a function reached from one of these, or from a direct user action. Read `_run_batch` and the `worker` closure in `scan_media_files_async` and confirm neither names a widget, a `tk.*Var`, or `messagebox` (except through `_ask_memory_warning`, which marshals via `root.after`).

- [ ] **Step 6: Commit**

```bash
git add media_organizer/app/main.py media_organizer/tests/test_ui_pump.py
git commit -m "Drain scan progress on the main thread too"
```

---

## Manual verification after Task 5

The automated tests cannot prove the GUI feels right. Run the app and confirm:

```bash
python -m media_organizer.app.main
```

1. The window opens with the Organize button already visible — no need to click Quick Scan first.
2. Point it at a folder with 50+ images, destination somewhere outside it, Copy, not dry run.
3. The progress bar advances **steadily** through the run rather than sitting at zero and jumping.
4. The ETA counts down and the current-file label changes.
5. The summary reports a non-zero "Files organized" that matches the file count.
6. Run it a second time against the same source and destination: the summary should report everything as skipped and the destination file count should not change.
7. Set the destination inside the source and press Organize: a clear error dialog, no batch started.
