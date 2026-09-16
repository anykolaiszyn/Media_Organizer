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

    try:
        finished = [e for e in events if isinstance(e, ev.Finished)][-1]
        assert finished.cancelled is True
        assert len([e for e in events if isinstance(e, ev.FileDone)]) < 30
    finally:
        if controller.batch_db is not None:
            controller.batch_db.close()


def test_nothing_is_emitted_after_finished(batch):
    events = run_batch(batch, [Placement.WROTE] * 5)

    finished_at = [i for i, e in enumerate(events) if isinstance(e, ev.Finished)]
    assert finished_at == [len(events) - 1]


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
