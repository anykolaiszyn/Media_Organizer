# ExifTool extraction: chunked calls, exact tag matching, real cancellation

Date: 2026-09-16
Status: approved, not yet implemented
Depends on: `docs/superpowers/specs/2026-09-16-batch-events-design.md` and its
implementation plan being landed first. This design adds new event types to
that mechanism and re-touches `organize_batch`, which that plan already
rewrote once.

## Problem

Confirmed by reading, not yet observed at scale, but arithmetic makes the
case. `ui_controller.organize_one` calls `extract_metadata(file_path)` — one
ExifTool subprocess — then calls `organize_files([file_path], ...)`, whose
internal `_destination_for` calls `extract_datetime`/`extract_earliest_datetime`
— a **second**, independent subprocess for the same file. Process spawn on
Windows is roughly 100-300ms even for a small executable; for 10,000 files
that is two spawns each, plausibly 30+ minutes of pure process-launch overhead
before any file I/O happens.

Three further defects share this code:

**Loose tag matching.** `extract_datetime_with_tags` falls back to
`k.lower().endswith(tag.lower())` when no exact key matches. Requesting
`CreateDate` also matches `MediaCreateDate`, `TrackCreateDate`, and
`SubSecCreateDate` — whichever the dict happens to iterate to first — silently
overriding the tag-priority order the user configured in the GUI.
`extract_earliest_datetime` has the same `endswith` fallback, and additionally
double-counts: its `if tag in meta:` branch doesn't `continue`, so an exact
match can be appended to `found_dates` twice (once from the exact check, once
from the `for k in meta` loop matching the same key).

**Dead cancellation.** `_register_exiftool_process`/`_exiftool_procs` exist in
`metadata_extractor.py` but nothing ever calls `_register_exiftool_process` —
every extraction uses `subprocess.run`, which returns only a
`CompletedProcess`, never a `Popen` handle to register. `cancel_exiftool()`
always iterates an empty set. Today's only stop mechanism is the
`cancel_flag` check between files in `organize_one`; a hung 30-second call on
one corrupt file is uninterruptible.

**Untested since the API moved on.** `test_metadata_extractor.py` monkeypatches
`exiftool_wrapper.ExifToolWrapper`, a module that does not exist anywhere in
this project or on PyPI (leftover from a documented-but-abandoned migration —
see `TYPE_SAFETY_FIXES.md`). All three tests fail with `ModuleNotFoundError`.
Since `metadata_extractor.py`'s public surface changes in this work regardless,
this is where those tests get replaced rather than carried forward broken.

## Goals

- One ExifTool spawn per ~200 files instead of one (or two) per file.
- Exact tag matching: a requested tag never silently resolves to a different
  one.
- A batch can actually be cancelled while extraction is in flight, not only
  between files.
- One corrupt file degrades to a per-file error, never aborts a whole chunk.
- Real test coverage of `metadata_extractor.py`, replacing the dead
  `exiftool_wrapper` tests.

## Non-goals

- `-stay_open` persistent-process mode. Considered and rejected here: it
  removes spawn overhead entirely, but turns metadata extraction into a
  strict single-writer pipe — every worker thread's request serializes
  through one process — and adds crash/restart handling if a pathological
  file kills the persistent process mid-batch. Chunking captures the large
  majority of the win (spawn count drops ~200x) with a fraction of the
  protocol-level maintenance. If chunking ever proves insufficient in
  practice, `-stay_open` is the documented next step, not a redesign.
- Overlapping the extraction and organize phases of a chunk (a producer/
  consumer pipeline where chunk N+1 extracts while chunk N's files are still
  being copied). The simpler serial-chunk design below already eliminates
  the dominant cost (spawn overhead); overlapping is a further optimization
  worth revisiting only if chunking alone is not enough.
- Giving the CLI a chunk-progress display. It gains the same correctness
  (single extraction pass, exact tag matching) but not new UI.

## Design

### `metadata_extractor.py`: batch extraction

```python
def extract_metadata_batch(file_paths, chunk_size=None, emit=None) -> dict[str, dict]:
```

`chunk_size` defaults to `MEDIA_ORGANIZER_CHUNK_SIZE` (env var, default 200),
mirroring how `MEDIA_ORGANIZER_MAX_WORKERS` already works. Splits
`file_paths` into chunks, and for each chunk:

1. Runs `exiftool -j -G -a -s <chunk files...>` via `Popen`, registering the
   handle (see Cancellation below).
2. `communicate(timeout=10 + 0.5 * len(chunk))` — 110s for a 200-file chunk,
   scaling with chunk size so a large chunk isn't penalized by a timeout sized
   for a small one.
3. Parses the JSON array. ExifTool includes `SourceFile` in every object;
   results are matched back to input paths by that field, never by list
   position — order is not guaranteed to be preserved.
4. On any failure (non-zero exit, timeout, unparseable JSON): if
   `len(chunk) > 1`, bisect into two halves and recurse on each **one at a
   time, first half then second** — never concurrently, which is what keeps
   the single-process cancellation invariant in the next section true even
   during bisection. At `len(chunk) == 1`, the failure becomes that file's
   result: `{"error": <message>, "type": "timeout" | "exiftool_error" |
   "json_parse_error"}` — the same error-dict shape `extract_metadata` already
   produces today, so every downstream consumer keeps working against one
   shape.
5. If `emit` is given, publishes `ExtractionProgress(chunks_done, chunks_total,
   files_done, files_total)` after each chunk (whole chunk, following
   bisection if any occurred).

`extract_metadata(file_path)` — the single-file form the Metadata Viewer tab
in `main.py` calls interactively — becomes a thin wrapper:

```python
def extract_metadata(file_path):
    return extract_metadata_batch([str(file_path)], chunk_size=1)[str(file_path)]
```

Preserving this signature means `main.py`'s `view_metadata` needs no change.

`select_datetime(metadata, tags=None)` and `select_earliest_datetime(metadata,
tags=None)` replace `extract_datetime`/`extract_datetime_with_tags`/
`extract_earliest_datetime`. Both are pure — no subprocess, no I/O — operating
on an already-fetched dict. Matching is exact: a key matches a requested tag
when the key equals the tag, or when the key's suffix after its **last** `:`
equals the tag exactly. Never `endswith`. `select_earliest_datetime` collects
each tag's match once (the `continue` the old code was missing) before sorting
by parsed date.

`extract_datetime`, `extract_datetime_with_tags`, and
`extract_earliest_datetime` are deleted, not deprecated — every caller in this
codebase is being updated in this same pass, so keeping them as forwarding
shims would only be dead code.

### Cancellation

Because chunks are processed one at a time (see Controller integration below),
at most one ExifTool chunk process is ever in flight. The existing
`_exiftool_procs` set — always empty, since nothing ever populated it — is
replaced by a single optional handle guarded by a lock:

```python
_current_chunk_process = None
_current_chunk_process_lock = threading.Lock()
```

set immediately after each chunk's `Popen` call and cleared right after
`communicate()` returns. `cancel_exiftool()` takes the lock, and if a process
is registered, calls `.terminate()` then `.kill()` as a fallback — the same
two-step it already attempts today, just now against a handle that actually
exists.

### `organizer.py`: metadata passed in, not fetched

`organize_files` gains a required parameter and stops calling ExifTool
itself:

```python
def organize_files(files, dest_folder, metadata_by_path, operation='copy',
                   dry_run=False, tag_order=None, use_earliest=False):
```

`_destination_for` becomes `_destination_for(file_path, dest_folder, metadata,
tag_order, use_earliest)`, calling `select_datetime`/`select_earliest_datetime`
against the passed-in dict instead of importing and calling the extraction
functions.

`get_organize_preview` is deleted. It has had no real caller since the Preview
button was removed — the current dry-run flow calls `organize_files(...,
dry_run=True)` directly — and its own test (`test_get_organize_preview` in
`test_organizer.py`) was the only thing exercising it. Keeping a
metadata-taking version of a function nothing calls would be dead code by
construction.

### `ui_controller.py`: chunk, then organize, repeat

`organize_batch` (already rewritten once by the batch-events plan to publish
events instead of calling three separate callbacks) is restructured again,
this time around chunk boundaries:

```python
chunk_size = _resolve_chunk_size()   # env var, default 200, same pattern as _resolve_max_workers
for chunk in _chunks(files, chunk_size):
    metadata_by_path = extract_metadata_batch(chunk, chunk_size=chunk_size, emit=emit)
    if self.cancel_flag:
        break
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(organize_one, f, metadata_by_path) for f in chunk]
        for future in as_completed(futures):
            ...  # unchanged from the batch-events plan: count, emit FileDone, check cancel_flag
```

One chunk's extraction and its organize phase do not overlap — extraction for
chunk N+1 does not start until chunk N's files have all been copied/moved.
This is deliberately the simpler of the two shapes discussed in Non-goals; it
already removes the dominant cost.

`organize_one` stops importing or calling `extract_metadata`; it receives
`metadata_by_path` and looks up its own file's entry:

```python
def organize_one(file_path, metadata_by_path):
    ...
    metadata = metadata_by_path.get(file_path, {"error": "not extracted"})
    if 'error' in metadata:
        status, error = 'error', metadata['error']
    else:
        results = organize_files([file_path], dest, metadata_by_path, operation, ...)
        ...
```

`batch_db.insert_result` is called with `{}` for the metadata argument, not
the full extracted dict. Every consumer of that column (`show_summary_dialog`,
`show_dry_run_dialog`, both CSV exports) destructures the row as `filename,
action, status, metadata, error` and never displays `metadata` — it has been
written to SQLite and never read back since the dialogs were built. This is a
direct consequence of touching this exact call site, not a separate hygiene
pass: skip storing data nothing reads.

### `cli.py`: extract once, then organize

The CLI never had the double-extraction bug in quite the same shape (it calls
`organize_files` once directly, without a separate `extract_metadata` call
first) but it does still call ExifTool once per file today via
`organize_files`'s internal extraction. It picks up the batch win directly:

```python
metadata_by_path = extract_metadata_batch(files)
organize_files(files, args.dest, metadata_by_path, operation=..., dry_run=..., tag_order=args.tags)
```

## Testing

`test_metadata_extractor.py` is rewritten from scratch against the new API —
no monkeypatching a module that doesn't exist:

- A chunk of files that all succeed → one `Popen` call, results keyed by
  `SourceFile`, in a dict covering every input path.
- A chunk where ExifTool's process fails (non-zero exit) → bisection recurses
  until the single bad file is isolated; every other file in the original
  chunk still gets a real result.
- A chunk that times out → same bisection guarantee.
- `select_datetime` with tag `CreateDate` against a metadata dict that also
  contains `MediaCreateDate` → returns only the `CreateDate` value. Direct
  regression test for the `endswith` bug.
- `select_earliest_datetime` given a metadata dict with one exact tag match →
  returns exactly one date, not the same value counted twice.
- `cancel_exiftool()` while a chunk's `Popen` is registered → the process
  receives `terminate()`.
- `extract_metadata(single_path)` still returns the same shape it does today,
  for the Metadata Viewer tab.

`test_organizer.py`'s `patch_extract` fixture (which monkeypatches
`media_organizer.app.organizer.extract_datetime` — a function that no longer
exists after this change) is replaced by tests that build a
`metadata_by_path` dict directly and pass it to `organize_files`.
`test_get_organize_preview` is deleted along with the function.

Controller-level tests (in `test_batch_events.py`, extending the fixture
built by the batch-events plan) add: a batch of more files than one chunk size
produces multiple `ExtractionProgress` events with `chunks_total` matching the
expected count; cancelling between chunks stops before the next chunk's
extraction begins.

## Risks

- Bisection's worst case (every file in a chunk individually broken) is
  O(chunk_size) ExifTool invocations for that one chunk — no worse than
  today's per-file model, and only reached when the chunk is genuinely full of
  bad files.
- `SourceFile` matching assumes ExifTool includes that field by default under
  `-j`, which it does; this is documented, standard behavior, not an
  assumption specific to this codebase.
