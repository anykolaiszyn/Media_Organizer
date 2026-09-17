"""A batch reports what actually happened, through events only."""
import itertools
import threading

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
            'media_organizer.app.ui_controller.extract_metadata_batch',
            lambda paths, chunk_size=None: {p: {} for p in paths},
        )
        by_path = dict(zip(paths, outcomes))

        def fake_organize(files, dest_, metadata_by_path, operation, dry_run=False, tag_order=None,
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
    # BatchResultsDB names its temp file by PID, so every controller in this
    # process shares one path. Close explicitly (rather than waiting on GC)
    # so Windows releases the file handle before another test's
    # BatchResultsDB opens the same path.
    if controller.batch_db is not None:
        controller.batch_db.close()
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


def test_cancel_reports_cancelled_and_short_circuits_remaining_files(batch, monkeypatch):
    """Cancelling partway through stops *real organizing* early (later files
    are short-circuited to 'cancelled' instead of actually being organized),
    but every file -- organized or short-circuited -- is still reported via
    a FileDone event and counted in Finished.counts. See
    test_cancel_counts_every_actually_cancelled_file for the exact-count
    regression test.
    """
    source, dest = batch([Placement.WROTE] * 30)
    controller = MediaOrganizerController()
    events = []
    seen = itertools.count()

    def cancelling_organize(files, dest_, metadata_by_path, operation, dry_run=False,
                            tag_order=None, use_earliest=False):
        if next(seen) >= 2:
            controller.cancel()
        return [(str(files[0]), Placement.WROTE)]

    monkeypatch.setattr(
        'media_organizer.app.ui_controller.organize_files', cancelling_organize)

    controller.organize_batch(
        source, dest, 'copy', False, None, False,
        emit=events.append, max_workers=1,
    )

    try:
        finished = [e for e in events if isinstance(e, ev.Finished)][-1]
        assert finished.cancelled is True
        # Every one of the 30 files is still reported, even though not all
        # of them were actually organized (some are short-circuited to
        # 'cancelled' by organize_one's own cancel_flag check).
        assert len([e for e in events if isinstance(e, ev.FileDone)]) == 30
        assert finished.counts.get('cancelled', 0) > 0
        assert finished.counts.get('wrote', 0) < 30
        assert sum(finished.counts.values()) == 30
    finally:
        if controller.batch_db is not None:
            controller.batch_db.close()


def test_cancel_counts_every_actually_cancelled_file(batch, monkeypatch):
    """Regression: Finished.counts['cancelled'] must count every file that
    ends up with 'cancelled' status in batch_db, not just whichever future
    happened to be `.result()`ed right before the aggregation loop broke
    early. The old code `break`s out of `as_completed` as soon as it sees
    `cancel_flag`, but `ThreadPoolExecutor.__exit__` still waits (via
    `shutdown(wait=True)`) for every other submitted future to finish
    running -- so those files really do get organized (or short-circuited
    to 'cancelled') and written to batch_db, they just never get counted.

    To make the split between "already running" and "still queued" files
    deterministic (rather than racing the aggregation loop against however
    fast the worker threads happen to be scheduled), this pins exactly
    `max_workers` files inside `organize_files` on a barrier/event pair
    before cancelling, so the remaining files are provably still queued
    -- not yet even past organize_one's own cancel_flag check -- at the
    moment cancellation happens.
    """
    total = 6
    max_workers = 2
    source, dest = batch([Placement.WROTE] * total)
    controller = MediaOrganizerController()
    events = []

    # +1 party for the test thread itself, so entered.wait() below only
    # returns once both workers have entered organize_files and are
    # blocked on `release`.
    entered = threading.Barrier(max_workers + 1)
    release = threading.Event()

    def blocking_organize(files, dest_, metadata_by_path, operation, dry_run=False,
                          tag_order=None, use_earliest=False):
        entered.wait(timeout=5)
        assert release.wait(timeout=5), "test never released blocked workers"
        return [(str(files[0]), Placement.WROTE)]

    monkeypatch.setattr(
        'media_organizer.app.ui_controller.organize_files', blocking_organize)

    worker_thread = threading.Thread(
        target=controller.organize_batch,
        args=(source, dest, 'copy', False, None, False),
        kwargs=dict(emit=events.append, max_workers=max_workers),
    )
    worker_thread.start()

    # Both workers are now blocked inside organize_files, having already
    # passed organize_one's cancel_flag check while it was still False.
    # The other (total - max_workers) files are still sitting in the
    # executor's queue, not yet processed at all.
    entered.wait(timeout=5)
    controller.cancel()
    release.set()
    worker_thread.join(timeout=10)

    try:
        assert not worker_thread.is_alive(), "organize_batch did not finish"
        finished = [e for e in events if isinstance(e, ev.Finished)][-1]
        assert finished.counts == {
            'wrote': max_workers, 'cancelled': total - max_workers,
        }
        assert sum(finished.counts.values()) == total

        cancel_lines = [
            e for e in events
            if isinstance(e, ev.LogLine) and 'cancelled by user' in e.text
        ]
        assert len(cancel_lines) == 1, cancel_lines
    finally:
        if controller.batch_db is not None:
            controller.batch_db.close()


def test_nothing_is_emitted_after_finished(batch):
    events = run_batch(batch, [Placement.WROTE] * 5)

    finished_at = [i for i, e in enumerate(events) if isinstance(e, ev.Finished)]
    assert finished_at == [len(events) - 1]


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
    try:
        controller.organize_batch(
            source, dest, 'copy', False, None, False, emit=events.append)
    finally:
        if controller.batch_db is not None:
            controller.batch_db.close()

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
    try:
        controller.organize_batch(
            source, dest, 'copy', False, None, False, emit=events.append)
    finally:
        if controller.batch_db is not None:
            controller.batch_db.close()

    assert extraction_calls == [5], "a second chunk's extraction must not start after cancel"
    finished = [e for e in events if isinstance(e, ev.Finished)][-1]
    assert finished.cancelled is True


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
