# Batch events and the worker/UI boundary

Date: 2026-09-16
Status: approved, not yet implemented

## Problem

Two defects, confirmed against real runs rather than inferred.

**Progress and ETA are meaningless.** `organize_batch` submits work through a
hand-rolled gate:

```python
while len(futures) >= max_workers:
    done, _ = next(iter(futures.items()))
    done.result(timeout=0.1)     # may time out
    del futures[done]            # deleted regardless
```

It takes an arbitrary future, waits 0.1s, then drops it from tracking whether or
not it finished. `as_completed(futures)` therefore only ever sees the last
`max_workers` futures, so `completed` never exceeds ~3. The bar sits near zero
for the whole run and snaps to 100% at the end. The gate is also redundant:
`ThreadPoolExecutor(max_workers=...)` already bounds concurrency.

**Summary counts are always zero.** `run_with_summary`'s `log_hook` infers
counts by substring-matching log text for "copied"/"moved"/"skipped". Those
lines are emitted by `organizer.py` through the module logger, which only
prints; they never reach the controller's `log_callback`. The hook sees only
"Processing:" and "ERROR:", so `organized` and `skipped` are structurally stuck
at 0. Substring matching is fragile regardless — a path containing "Removed"
matches "moved".

**Latent, not yet observed:** `run_with_summary` runs on a worker thread and
touches Tk directly — `eta_var.set`, `update_idletasks`, `messagebox.askyesno`,
`_flush_log_buffer` writing to the log widget, and `show_summary_dialog`
building a Toplevel. Tk is not thread-safe. `scan_files_dialog`'s `on_found`
has the same defect, inserting into a `ScrolledText` from a worker.

`max_workers` is also dead as a parameter: line 70 overwrites the argument with
the environment variable, so the UI's "Using up to 4 concurrent ExifTool
processes" message is false whenever the default 3 applies.

## Goals

- Progress and ETA track real completion.
- Summary counts come from recorded outcomes, not log text.
- Worker threads cannot touch Tk at all — structurally, not by discipline.
- The `max_workers` argument is honoured.

## Non-goals

- ExifTool performance. The double extraction per file and the `-stay_open`
  rewrite are a separate sub-project, deliberately sequenced after this one so
  there is something correct to report progress into.
- Giving the CLI a progress display. It does not call `organize_batch` today;
  unifying them is out of scope.

## Design

### Event model

New module `app/batch_events.py`, frozen dataclasses:

| Event | Fields |
|---|---|
| `Scanned` | `total` |
| `FileStarted` | `path` |
| `FileDone` | `path`, `outcome` (`Placement` or `None`), `error`, `completed`, `total`, `eta_seconds` |
| `LogLine` | `text` |
| `Finished` | `counts`, `cancelled`, `elapsed` |

`outcome` is `None` exactly when `error` is set.

### Controller API

`organize_batch` takes `emit: Callable[[BatchEvent], None]` and stops using the
three callbacks it reports through today: `eta_callback` is replaced by
`FileDone.eta_seconds`, `progress_callback` by `FileDone.completed`/`total`, and
`log_callback` by `LogLine`. The controller gains no knowledge of queues or Tk —
the GUI passes `queue.put`, tests pass `list.append`, callers wanting nothing
pass a no-op.

`scan_media_files_async` changes the same way: its `progress_callback` /
`found_callback` / `done_callback` trio becomes a single `emit`, so the scan
dialog can drain a queue on the main thread instead of having its worker write
into a `ScrolledText` directly.

`MediaOrganizerController.__init__` keeps `log_callback` / `progress_callback`
for now only if something still uses them after the conversion; if nothing does,
they are removed with the rest of the dead plumbing.

`memory_warning_callback` stays, because it asks a question rather than
reporting. See below.

### Batch loop

```python
futures = {executor.submit(organize_one, f): f for f in files}
for future in as_completed(futures):
    completed += 1
    emit(FileDone(...))
    if self.cancel_flag:
        break
```

The `while` gate and the `time.sleep(0.05)` both go. `max_workers` uses the
argument, falling back to `MEDIA_ORGANIZER_MAX_WORKERS` (default 3) only when
the argument is `None`, clamped to at least 1. The startup log line reports the
number actually in force.

### Counting

`organize_one` already receives `[(path, Placement)]` from `organize_files`. It
writes that to `batch_db` and attaches it to `FileDone`. The controller
accumulates a `Counter`, which becomes `Finished.counts`. Its keys are plain
strings throughout, never a mix of enum and string: the three `Placement` values
(`'wrote'`, `'renamed'`, `'skipped_identical'`) plus `'error'` and
`'cancelled'`. The summary dialog maps it:

- organized = `WROTE` + `RENAMED`
- skipped = `SKIPPED_IDENTICAL`
- errors = error count
- cancelled = cancelled count

All regex counting in `log_hook` is deleted.

### UI pump

`start_organize` creates a `queue.Queue`, starts the worker thread, and
schedules `root.after(100, self._pump)`. `_pump` drains everything queued,
updates widgets on the main thread, and reschedules until it sees `Finished`,
at which point it builds the summary (or dry-run) dialog — also on the main
thread. This replaces the `_log_buffer` / `_flush_log_buffer` throttling, since
draining is already batched.

`scan_files_dialog` is converted the same way, with its own queue and pump.

### Memory-pressure confirmation

Kept blocking, preserving current behaviour. The worker emits a request and
waits on a `threading.Event`; the pump shows the dialog on the main thread and
sets the event with the answer. One helper in `main.py`, used in one place. The
wait times out after 300 seconds so a closed or unresponsive window cannot wedge
the worker forever; on timeout it proceeds as if the user had declined, which
cancels the batch rather than steamrolling a memory warning nobody saw.

## Removals

- `get_preview_list` and `test_ui_controller.py`. Nothing has called the method
  since the Preview button was removed, so the only test of it was giving false
  coverage comfort.
- `_log_buffer` / `_flush_log_buffer` in `main.py`.
- The `while len(futures) >= max_workers` gate and its `time.sleep`.

## Testing

Controller tests need no Tk — a list sink captures events:

- `completed` reaches `total` for a full run. Direct regression for the broken
  gate; fails against current code, which stops at ~`max_workers`.
- `Finished.counts` matches a known mix of wrote / skipped / errored files.
- The `max_workers` argument is honoured even when the environment variable is
  set to something else.
- Cancel mid-batch yields `Finished.cancelled` true, with no `FileDone` after.
- Events arrive in a sane order: `Scanned` first, `Finished` last.

The pump is tested against a real hidden `Tk` root, as the existing GUI
verification does.

## Risks

- Submitting every future up front rather than in waves means N queued tasks for
  N files. Futures are small and `organize_one` checks `cancel_flag` first, so
  cancellation still drains quickly, but this is the one memory characteristic
  that changes.
- The blocking memory prompt is the single remaining cross-thread wait. The
  timeout is what keeps it from being a deadlock.
