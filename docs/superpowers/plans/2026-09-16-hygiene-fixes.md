# Hygiene Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Note on process:** these four fixes were each individually classified as **bounded** (a well-scoped change to an existing flow), not architectural — under the brainstorming skill's normal rule, bounded work gets a short in-chat design and direct implementation, no written plan or spec file. This document is a deliberate, approved exception to that "no plan doc" convention: it exists only because these fixes are meant to be picked up cold by a subagent with no live session to approve a design against, not because the classification changed. There is no separate spec file for any of these — the design is this plan.

**Goal:** Fix four independent, previously-identified defects: CSV export injection/quoting, unbounded pagination, ExifTool's all-zero placeholder date being misfiled, and settings that don't survive a restart.

**Architecture:** Four unrelated single-concern fixes. They do not depend on each other and can be done in any order relative to one another — but two of them (Tasks 3 and 4) depend on *other*, separate plans having already landed, stated individually below since they're not the same dependency.

**Tech Stack:** Python 3.13 standard library — `csv`, `sqlite3`, `json`. No new dependencies.

**Spec:** none — see the process note above.

## Global Constraints

- Python 3.13. Interpreter at `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`; `python` also resolves on PATH in a fresh terminal.
- Run tests from the **repo root**: `python -m pytest media_organizer/tests -q`.
- No new dependencies.
- Never commit `__pycache__/*.pyc`. They are tracked in this repo by mistake; stage source files explicitly, never `git add -A`.
- Tasks 1 and 2 have no dependency on any other plan and can run first, in any order, against the repo as it stands today.
- Task 3 depends on `docs/superpowers/plans/2026-09-16-extraction-performance.md` — specifically its Task 1 — having landed. It edits `select_datetime`/`select_earliest_datetime`, which that plan creates; they do not exist before it runs.
- Task 4 depends on `docs/superpowers/plans/2026-09-16-batch-events.md` having landed. It edits `start_organize`'s body, which that plan rewrites.

---

### Task 1: CSV export is safe against quoting and formula injection

**Files:**
- Modify: `media_organizer/app/utils.py` (add `write_csv_safe`)
- Modify: `media_organizer/app/main.py` (`export_preview` inside `show_dry_run_dialog`, `export_errors` inside `show_summary_dialog`)
- Test: `media_organizer/tests/test_utils.py` (append)

**Interfaces:**
- Produces: `write_csv_safe(file_path, header: list[str], rows: list[tuple]) -> None`.

Both export functions currently hand-build CSV lines with an f-string —
`f'"{filename}","{action}","{status}","{error or ""}"\n'` — which breaks the
moment any field contains a `"`, and is a formula-injection vector into
Excel/LibreOffice for a filename beginning with `=`, `+`, `-`, or `@`.

- [ ] **Step 1: Write the failing tests**

Append to `media_organizer/tests/test_utils.py`:

```python
import csv
from media_organizer.app.utils import write_csv_safe


def test_write_csv_safe_round_trips_embedded_quotes_and_commas(tmp_path):
    out = tmp_path / 'out.csv'
    write_csv_safe(out, ['filename', 'note'], [
        ('IMG "final", v2.jpg', 'has a comma, and quotes "here"'),
    ])

    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))

    assert rows[0] == ['filename', 'note']
    assert rows[1] == ['IMG "final", v2.jpg', 'has a comma, and quotes "here"']


def test_write_csv_safe_neutralizes_leading_formula_characters(tmp_path):
    out = tmp_path / 'out.csv'
    write_csv_safe(out, ['filename'], [
        ('=cmd|/c calc.exe',),
        ('+1+1',),
        ('-1',),
        ('@SUM(A1:A2)',),
        ('normal_name.jpg',),
    ])

    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))[1:]

    assert [r[0] for r in rows] == [
        "'=cmd|/c calc.exe", "'+1+1", "'-1", "'@SUM(A1:A2)", "normal_name.jpg",
    ]


def test_write_csv_safe_handles_none_as_an_empty_cell(tmp_path):
    out = tmp_path / 'out.csv'
    write_csv_safe(out, ['filename', 'error'], [('a.jpg', None)])

    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))

    assert rows[1] == ['a.jpg', '']
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest media_organizer/tests/test_utils.py -q -k write_csv_safe`

Expected: FAIL, `ImportError: cannot import name 'write_csv_safe' from 'media_organizer.app.utils'`.

- [ ] **Step 3: Add `write_csv_safe` to `utils.py`**

Add to `media_organizer/app/utils.py` (the `filecmp`/`Path` imports at the top already cover what this needs; add `import csv` alongside them):

```python
import csv
```

and, anywhere in the file after the imports:

```python
def write_csv_safe(file_path, header, rows):
    """Write rows to file_path as CSV.

    Uses the csv module so embedded quotes, commas, and newlines are escaped
    correctly -- ad-hoc f-string quoting breaks on any of those. Also guards
    against CSV/spreadsheet formula injection: a cell beginning with =, +,
    -, or @ is prefixed with a single quote, which Excel and LibreOffice
    both treat as "this is literal text," not a formula to evaluate.
    """
    def sanitize(value):
        text = '' if value is None else str(value)
        if text and text[0] in ('=', '+', '-', '@'):
            return "'" + text
        return text

    with open(file_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow([sanitize(v) for v in row])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest media_organizer/tests/test_utils.py -q -k write_csv_safe`

Expected: PASS, 3 tests.

- [ ] **Step 5: Use it from both export functions in `main.py`**

In `media_organizer/app/main.py`, inside `show_dry_run_dialog`, replace `export_preview`'s body from `try:` through the `except` block:

```python
            try:
                db = self.controller.batch_db
                all_rows = []
                offset = 0
                if db is not None:
                    while True:
                        rows = db.fetch_results(limit=page_size, offset=offset)
                        if not rows:
                            break
                        all_rows.extend(rows)
                        offset += page_size
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('filename,action,status,error\n')
                    for row in all_rows:
                        filename, action, status, metadata, error = row
                        f.write(f'"{filename}","{action}","{status}","{error or ""}"\n')
                messagebox.showinfo("Export Complete", f"Dry run results exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Could not export dry run results:\n{e}")
```

becomes

```python
            try:
                db = self.controller.batch_db
                all_rows = []
                offset = 0
                if db is not None:
                    while True:
                        rows = db.fetch_results(limit=page_size, offset=offset)
                        if not rows:
                            break
                        all_rows.extend(rows)
                        offset += page_size
                from media_organizer.app.utils import write_csv_safe
                write_csv_safe(
                    file_path,
                    ['filename', 'action', 'status', 'error'],
                    [(filename, action, status, error)
                     for filename, action, status, metadata, error in all_rows],
                )
                messagebox.showinfo("Export Complete", f"Dry run results exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Could not export dry run results:\n{e}")
```

Inside `show_summary_dialog`, replace `export_errors`'s body the same way — from `try:` through its `except` block:

```python
            try:
                db = self.controller.batch_db
                all_rows = []
                offset = 0
                if db is not None:
                    while True:
                        rows = db.fetch_results(limit=page_size, offset=offset)
                        if not rows:
                            break
                        all_rows.extend(rows)
                        offset += page_size
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('filename,action,status,error\n')
                    for row in all_rows:
                        filename, action, status, metadata, error = row
                        if error or status == 'error':
                            f.write(f'"{filename}","{action}","{status}","{error or ""}"\n')
                messagebox.showinfo("Export Complete", f"Errors and warnings exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Could not export errors/warnings:\n{e}")
```

becomes

```python
            try:
                db = self.controller.batch_db
                all_rows = []
                offset = 0
                if db is not None:
                    while True:
                        rows = db.fetch_results(limit=page_size, offset=offset)
                        if not rows:
                            break
                        all_rows.extend(rows)
                        offset += page_size
                from media_organizer.app.utils import write_csv_safe
                write_csv_safe(
                    file_path,
                    ['filename', 'action', 'status', 'error'],
                    [(filename, action, status, error)
                     for filename, action, status, metadata, error in all_rows
                     if error or status == 'error'],
                )
                messagebox.showinfo("Export Complete", f"Errors and warnings exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Could not export errors/warnings:\n{e}")
```

(`write_csv_safe` treats `None` as an empty cell itself, so the `error or ""` guard the old code needed is no longer necessary — passing `error` straight through is correct.)

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest media_organizer/tests -q`

Expected: no new failures relative to whatever the suite showed before this task (see each other plan's own constraints for what's expected to still be red at the point this task runs).

- [ ] **Step 7: Commit**

```bash
git add media_organizer/app/utils.py media_organizer/app/main.py media_organizer/tests/test_utils.py
git commit -m "Export CSV safely: correct quoting, no formula injection"
```

---

### Task 2: Pagination has a visible, enforced upper bound

**Files:**
- Modify: `media_organizer/app/batch_results_db.py` (add `count_results`)
- Modify: `media_organizer/app/main.py` (`show_dry_run_dialog`, `show_summary_dialog`)
- Test: `media_organizer/tests/test_batch_results_db.py` (append)

**Interfaces:**
- Produces: `BatchResultsDB.count_results() -> int`.

"Next" in both result dialogs has no ceiling today — past the last page it
shows an empty page with no feedback and nothing preventing further clicks.

- [ ] **Step 1: Write the failing test**

Append to `media_organizer/tests/test_batch_results_db.py`:

```python
def test_count_results_matches_what_was_inserted(tmp_path):
    from media_organizer.app.batch_results_db import BatchResultsDB

    db = BatchResultsDB(db_path=str(tmp_path / 'test.sqlite3'))
    assert db.count_results() == 0

    for i in range(7):
        db.insert_result(f'file{i}.jpg', 'copy', 'done', {})

    assert db.count_results() == 7
    db.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest media_organizer/tests/test_batch_results_db.py -q -k count_results`

Expected: FAIL, `AttributeError: 'BatchResultsDB' object has no attribute 'count_results'`.

- [ ] **Step 3: Add `count_results` to `batch_results_db.py`**

Add this method to the `BatchResultsDB` class, next to `fetch_results`:

```python
    def count_results(self):
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) FROM results")
        return c.fetchone()[0]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest media_organizer/tests/test_batch_results_db.py -q -k count_results`

Expected: PASS.

- [ ] **Step 5: Clamp pagination in `show_dry_run_dialog`**

In `media_organizer/app/main.py`, inside `show_dry_run_dialog`, replace from the `page_size = 100` line through the `next_btn.pack(...)` line:

```python
        page_size = 100
        page_var = tk.IntVar(value=0)
        results = []
        def load_page():
            st.config(state='normal')
            st.delete('1.0', 'end')
            offset = page_var.get() * page_size
            results.clear()
            db = self.controller.batch_db
            if db is not None:
                rows = db.fetch_results(limit=page_size, offset=offset)
                for row in rows:
                    filename, action, status, metadata, error = row
                    results.append(row)
                    line = f"{filename} | {action} | {status}"
                    if error:
                        line += f" | ERROR: {error}"
                    st.insert('end', line + '\n')
            st.config(state='disabled')
            page_label.config(text=f"Page {page_var.get()+1}")

        st = scrolledtext.ScrolledText(win, width=110, height=18)
        st.pack(padx=10, pady=5)

        nav_frame = tk.Frame(win)
        nav_frame.pack(pady=2)
        prev_btn = Button(nav_frame, text="Previous", command=lambda: (page_var.set(max(0, page_var.get()-1)), load_page()))
        next_btn = Button(nav_frame, text="Next", command=lambda: (page_var.set(page_var.get()+1), load_page()))
        page_label = Label(nav_frame, text="Page 1")
        prev_btn.pack(side='left', padx=2)
        page_label.pack(side='left', padx=2)
        next_btn.pack(side='left', padx=2)
```

becomes

```python
        page_size = 100
        page_var = tk.IntVar(value=0)
        results = []
        db = self.controller.batch_db
        total_results = db.count_results() if db is not None else 0
        total_pages = max(1, (total_results + page_size - 1) // page_size)

        def load_page():
            st.config(state='normal')
            st.delete('1.0', 'end')
            offset = page_var.get() * page_size
            results.clear()
            if db is not None:
                rows = db.fetch_results(limit=page_size, offset=offset)
                for row in rows:
                    filename, action, status, metadata, error = row
                    results.append(row)
                    line = f"{filename} | {action} | {status}"
                    if error:
                        line += f" | ERROR: {error}"
                    st.insert('end', line + '\n')
            st.config(state='disabled')
            page_label.config(text=f"Page {page_var.get()+1} of {total_pages}")
            prev_btn.config(state='normal' if page_var.get() > 0 else 'disabled')
            next_btn.config(state='normal' if page_var.get() < total_pages - 1 else 'disabled')

        st = scrolledtext.ScrolledText(win, width=110, height=18)
        st.pack(padx=10, pady=5)

        nav_frame = tk.Frame(win)
        nav_frame.pack(pady=2)
        prev_btn = Button(nav_frame, text="Previous",
                          command=lambda: (page_var.set(max(0, page_var.get()-1)), load_page()))
        next_btn = Button(nav_frame, text="Next",
                          command=lambda: (page_var.set(min(total_pages - 1, page_var.get()+1)), load_page()))
        page_label = Label(nav_frame, text="Page 1")
        prev_btn.pack(side='left', padx=2)
        page_label.pack(side='left', padx=2)
        next_btn.pack(side='left', padx=2)
```

(`load_page` refers to `prev_btn`/`next_btn`, which are defined after it — this is already how the original code refers to `page_label` from inside `load_page`; Python closures resolve names when the function *runs*, not when it's defined, and `load_page()` is only ever called at the very end of the dialog's setup, after every button already exists.)

- [ ] **Step 6: Clamp pagination in `show_summary_dialog`**

The equivalent block in `show_summary_dialog` is the same shape as Step 5's but is **not** byte-identical — its `ScrolledText` uses `width=90, height=15`, not `110, 18`. Replace, in `show_summary_dialog`, from the `page_size = 100` line through the `next_btn.pack(...)` line:

```python
        page_size = 100
        page_var = tk.IntVar(value=0)
        results = []
        def load_page():
            st.config(state='normal')
            st.delete('1.0', 'end')
            offset = page_var.get() * page_size
            results.clear()
            db = self.controller.batch_db
            if db is not None:
                rows = db.fetch_results(limit=page_size, offset=offset)
                for row in rows:
                    filename, action, status, metadata, error = row
                    results.append(row)
                    line = f"{filename} | {action} | {status}"
                    if error:
                        line += f" | ERROR: {error}"
                    st.insert('end', line + '\n')
            st.config(state='disabled')
            page_label.config(text=f"Page {page_var.get()+1}")

        st = scrolledtext.ScrolledText(win, width=90, height=15)
        st.pack(padx=10, pady=5)

        nav_frame = tk.Frame(win)
        nav_frame.pack(pady=2)
        prev_btn = Button(nav_frame, text="Previous", command=lambda: (page_var.set(max(0, page_var.get()-1)), load_page()))
        next_btn = Button(nav_frame, text="Next", command=lambda: (page_var.set(page_var.get()+1), load_page()))
        page_label = Label(nav_frame, text="Page 1")
        prev_btn.pack(side='left', padx=2)
        page_label.pack(side='left', padx=2)
        next_btn.pack(side='left', padx=2)
```

with:

```python
        page_size = 100
        page_var = tk.IntVar(value=0)
        results = []
        db = self.controller.batch_db
        total_results = db.count_results() if db is not None else 0
        total_pages = max(1, (total_results + page_size - 1) // page_size)

        def load_page():
            st.config(state='normal')
            st.delete('1.0', 'end')
            offset = page_var.get() * page_size
            results.clear()
            if db is not None:
                rows = db.fetch_results(limit=page_size, offset=offset)
                for row in rows:
                    filename, action, status, metadata, error = row
                    results.append(row)
                    line = f"{filename} | {action} | {status}"
                    if error:
                        line += f" | ERROR: {error}"
                    st.insert('end', line + '\n')
            st.config(state='disabled')
            page_label.config(text=f"Page {page_var.get()+1} of {total_pages}")
            prev_btn.config(state='normal' if page_var.get() > 0 else 'disabled')
            next_btn.config(state='normal' if page_var.get() < total_pages - 1 else 'disabled')

        st = scrolledtext.ScrolledText(win, width=90, height=15)
        st.pack(padx=10, pady=5)

        nav_frame = tk.Frame(win)
        nav_frame.pack(pady=2)
        prev_btn = Button(nav_frame, text="Previous",
                          command=lambda: (page_var.set(max(0, page_var.get()-1)), load_page()))
        next_btn = Button(nav_frame, text="Next",
                          command=lambda: (page_var.set(min(total_pages - 1, page_var.get()+1)), load_page()))
        page_label = Label(nav_frame, text="Page 1")
        prev_btn.pack(side='left', padx=2)
        page_label.pack(side='left', padx=2)
        next_btn.pack(side='left', padx=2)
```

- [ ] **Step 7: Manual check**

Run `python -m media_organizer.app.main`, run a dry-run batch against a folder with well under 100 files, and open the preview dialog. Confirm: the label reads "Page 1 of 1", and both Previous and Next are disabled (greyed out).

- [ ] **Step 8: Commit**

```bash
git add media_organizer/app/batch_results_db.py media_organizer/app/main.py media_organizer/tests/test_batch_results_db.py
git commit -m "Bound pagination in the result dialogs to the actual page count"
```

---

### Task 3: ExifTool's all-zero placeholder date is not a date to select

**Depends on:** `docs/superpowers/plans/2026-09-16-extraction-performance.md`, Task 1. `select_datetime`/`select_earliest_datetime` do not exist before that task runs — do not attempt this task first.

**Files:**
- Modify: `media_organizer/app/metadata_extractor.py` (`select_datetime`, `select_earliest_datetime`)
- Test: `media_organizer/tests/test_metadata_extractor.py` (append)

**Interfaces:**
- Consumes: `_key_matches_tag` (already private to `metadata_extractor.py`, from the extraction-performance plan).
- Produces: no signature change to `select_datetime`/`select_earliest_datetime` — same inputs, same outputs, just excluding one specific value.

ExifTool commonly writes `0000:00:00 00:00:00` (occasionally `0000:00:00`
alone, for a date-only tag) into a date field when a camera or file genuinely
has no date to record. That's a value present in the tag, not an absent tag
— so `select_datetime` currently returns it as a real match, and
`organize_files` routes the file to `unsorted/` (a value that failed to
parse as a real date) rather than `no_metadata/` (no usable date was found
at all), which is where it belongs.

Fixing this in `parse_exif_date` (`utils.py`) — the more obvious-looking
target — does **not** work: by the time `_destination_for` calls
`parse_exif_date`, it has already committed to the `unsorted/` branch for
anything that isn't a clean parse, with no way to distinguish "malformed"
from "known placeholder." The fix has to happen earlier, in tag selection
itself, so a placeholder value never becomes `date_str` in the first place —
which then correctly hits `_destination_for`'s existing "no date string at
all" branch, routing to `no_metadata/` as intended.

- [ ] **Step 1: Write the failing tests**

Append to `media_organizer/tests/test_metadata_extractor.py`:

```python
def test_select_datetime_skips_the_all_zero_placeholder():
    """ExifTool's all-zero date means 'no date', not a value to select."""
    metadata = {
        "EXIF:DateTimeOriginal": "0000:00:00 00:00:00",
        "EXIF:CreateDate": "2022:06:15 12:00:00",
    }
    assert select_datetime(
        metadata, tags=["DateTimeOriginal", "CreateDate"]) == "2022:06:15 12:00:00"


def test_select_datetime_returns_none_when_only_the_placeholder_is_present():
    metadata = {"EXIF:DateTimeOriginal": "0000:00:00 00:00:00"}
    assert select_datetime(metadata, tags=["DateTimeOriginal"]) is None


def test_select_earliest_datetime_ignores_the_placeholder_among_candidates():
    metadata = {
        "EXIF:CreateDate": "0000:00:00 00:00:00",
        "QuickTime:TrackCreateDate": "2020:01:01 00:00:00",
    }
    result = select_earliest_datetime(metadata, tags=["CreateDate", "TrackCreateDate"])
    assert result == "2020:01:01 00:00:00"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest media_organizer/tests/test_metadata_extractor.py -q -k placeholder`

Expected: FAIL. `test_select_datetime_skips_the_all_zero_placeholder` fails with `AssertionError: assert '0000:00:00 00:00:00' == '2022:06:15 12:00:00'` — today's code returns the placeholder itself, since it's the first tag in priority order and nothing filters its value.

- [ ] **Step 3: Filter the placeholder out of both selection functions**

In `media_organizer/app/metadata_extractor.py`, add a module-level constant near `_key_matches_tag`:

```python
_ZERO_DATE_PLACEHOLDERS = {'0000:00:00 00:00:00', '0000:00:00'}
```

Change `select_datetime` from

```python
def select_datetime(metadata, tags=None):
    """First tag in priority order that has a value in `metadata`, or None."""
    if tags is None:
        tags = ['DateTimeOriginal', 'CreateDate', 'MediaCreateDate']
    for tag in tags:
        for key, value in metadata.items():
            if _key_matches_tag(key, tag):
                return value
    return None
```

to

```python
def select_datetime(metadata, tags=None):
    """First tag in priority order that has a real value in `metadata`, or None."""
    if tags is None:
        tags = ['DateTimeOriginal', 'CreateDate', 'MediaCreateDate']
    for tag in tags:
        for key, value in metadata.items():
            if _key_matches_tag(key, tag) and value not in _ZERO_DATE_PLACEHOLDERS:
                return value
    return None
```

Change `select_earliest_datetime` from

```python
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

to

```python
def select_earliest_datetime(metadata, tags=None):
    """Earliest valid date among all matches for `tags` in `metadata`, or None."""
    from .utils import parse_exif_date
    found = []
    for tag in tags or []:
        for key, value in metadata.items():
            if _key_matches_tag(key, tag) and value not in _ZERO_DATE_PLACEHOLDERS:
                dt = parse_exif_date(value)
                if dt:
                    found.append((dt, value))
    if not found:
        return None
    found.sort(key=lambda pair: pair[0])
    return found[0][1]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest media_organizer/tests/test_metadata_extractor.py -q`

Expected: PASS, all tests (the 11 from the extraction-performance plan plus the 3 new ones here).

- [ ] **Step 5: Add an end-to-end organizer test proving the folder outcome, not just the selected value**

Append to `media_organizer/tests/test_organizer.py`:

```python
def test_a_file_with_only_the_placeholder_date_goes_to_no_metadata_not_unsorted(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    metadata = {str(f1): {"EXIF:DateTimeOriginal": "0000:00:00 00:00:00"}}

    organize_files([str(f1)], tmp_path, metadata, operation='copy')

    assert (tmp_path / 'no_metadata' / 'a.jpg').exists()
    assert not (tmp_path / 'unsorted' / 'a.jpg').exists()
```

Run: `python -m pytest media_organizer/tests/test_organizer.py -q`

Expected: PASS. This is the test that actually proves the bug is fixed — the three in Step 1 only prove `select_datetime` filters correctly, not that a file ends up in the right folder.

- [ ] **Step 6: Commit**

```bash
git add media_organizer/app/metadata_extractor.py media_organizer/tests/test_metadata_extractor.py media_organizer/tests/test_organizer.py
git commit -m "Treat ExifTool's all-zero placeholder date as no date at all"
```

---

### Task 4: Settings survive a restart

**Depends on:** `docs/superpowers/plans/2026-09-16-batch-events.md`, Task 4. That task rewrites `start_organize`'s body; this task inserts one line into the rewritten version, not today's.

**Files:**
- Modify: `media_organizer/app/main.py` (`save_last_folders`, `load_last_folders`, the `include_images`/`include_videos` construction lines, `start_organize`)

**Interfaces:**
- No new public methods. `save_last_folders`/`load_last_folders` keep their existing no-argument signatures.

Only `source`/`dest` survive a restart today. Tag order, "use earliest date,"
and the image/video filters silently reset every launch.

**The ordering trap this task must not reintroduce:** `load_last_folders()`
runs early in `__init__` (right after `self.tag_vars` is created), but
`self.include_images`/`self.include_videos` aren't created until much later
in the same method, in the widget-construction block. Calling
`self.include_images.set(...)` from inside `load_last_folders` would raise
`AttributeError` — and `load_last_folders` already wraps its whole body in a
bare `except Exception: pass`, so that failure would be silently swallowed:
no crash, but the images/videos settings would just never restore, with
nothing telling you why. The fix below avoids this by never calling `.set()`
on those two vars from `load_last_folders` at all — instead, their *initial
value* at construction time is seeded from the already-parsed config dict.

- [ ] **Step 1: Extend `save_last_folders`**

Change

```python
    def save_last_folders(self):
        data = {
            'source': self.source_var.get(),
            'dest': self.dest_var.get()
        }
        try:
            with open(self.config_path, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass
```

to

```python
    def save_last_folders(self):
        data = {
            'source': self.source_var.get(),
            'dest': self.dest_var.get(),
            'tag_order': [v.get() for v in self.tag_vars],
            'use_earliest': self.use_earliest_date.get(),
            'include_images': self.include_images.get(),
            'include_videos': self.include_videos.get(),
        }
        try:
            with open(self.config_path, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass
```

- [ ] **Step 2: Extend `load_last_folders` for the fields that already exist when it runs**

Change

```python
    def load_last_folders(self):
        try:
            with open(self.config_path) as f:
                data = json.load(f)
            self.source_var.set(data.get('source', ''))
            self.dest_var.set(data.get('dest', ''))
        except Exception:
            pass
```

to

```python
    def load_last_folders(self):
        self._loaded_settings = {}
        try:
            with open(self.config_path) as f:
                data = json.load(f)
            self._loaded_settings = data
            self.source_var.set(data.get('source', ''))
            self.dest_var.set(data.get('dest', ''))
            saved_tags = data.get('tag_order')
            if saved_tags and len(saved_tags) == len(self.tag_vars):
                for var, tag in zip(self.tag_vars, saved_tags):
                    var.set(tag)
            if 'use_earliest' in data:
                self.use_earliest_date.set(data['use_earliest'])
        except Exception:
            pass
```

`self.tag_vars` and `self.use_earliest_date` both already exist by the time
`load_last_folders()` is called (line 201, well after both are constructed
at lines 165 and 198), so setting them directly here is safe.
`self._loaded_settings` is stashed for Step 3 to use once
`include_images`/`include_videos` actually exist — initialized to `{}`
*before* the `try` block, so it's always a dict even if the config file is
missing or corrupt.

- [ ] **Step 3: Seed `include_images`/`include_videos` from the stashed settings at construction time**

Change

```python
        self.include_images = tk.BooleanVar(value=True)
        self.include_videos = tk.BooleanVar(value=True)
```

to

```python
        self.include_images = tk.BooleanVar(value=self._loaded_settings.get('include_images', True))
        self.include_videos = tk.BooleanVar(value=self._loaded_settings.get('include_videos', True))
```

- [ ] **Step 4: Save settings when a batch starts, not only when folders are browsed**

Tag order, "use earliest," and the file-type checkboxes have no natural
per-change save hook the way folder browsing does. The simplest correct
point to persist them is right before a batch actually runs, once
validation has passed. In `start_organize`, immediately after the
source/dest validation and before the batch-events plan's rewritten
execution body, insert one call:

```python
        if not source or not dest:
            messagebox.showerror("Error", "Please select both source and destination folders.")
            return

        self.save_last_folders()

        try:
            check_source_dest_overlap(source, dest)
```

(The `try: check_source_dest_overlap(...)` line and everything after it is
exactly where the batch-events plan's Task 4 rewrite of `start_organize`
begins — this only adds the `self.save_last_folders()` line immediately
before it.)

- [ ] **Step 5: Manual verification**

There is no automated test for this — persistence writes to
`~/.media_organizer_config.json`, a real file outside the repo, which is not
something worth mocking for four settings this simple. Verify by hand:

1. Run `python -m media_organizer.app.main`.
2. Change the tag order (move a tag to a different priority slot), check
   "Use earliest date," and uncheck "Videos".
3. Point it at any valid source/dest and click Organize (a dry run against
   an empty folder is fine — the point is only to trigger the save).
4. Close the app and reopen it.
5. Confirm the tag order, the earliest-date checkbox, and the file-type
   checkboxes all come back exactly as you left them.
6. Manually delete `~/.media_organizer_config.json`... no — inspect it
   instead (`type %USERPROFILE%\.media_organizer_config.json` from
   PowerShell) and confirm it's valid JSON containing `tag_order`,
   `use_earliest`, `include_images`, and `include_videos` keys alongside
   `source`/`dest`.

- [ ] **Step 6: Commit**

```bash
git add media_organizer/app/main.py
git commit -m "Persist tag order, earliest-date, and file-type filter settings"
```
