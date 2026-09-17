import os
import threading
import time

from media_organizer.app.organizer import Placement
from media_organizer.app.ui_controller import MediaOrganizerController


def test_batch_never_exceeds_the_worker_limit(monkeypatch, tmp_path):
    source = tmp_path / 'src'
    dest = tmp_path / 'lib'
    source.mkdir()
    files = [source / f"file_{i}.jpg" for i in range(10)]
    for f in files:
        f.write_text("fake data")

    # Patch the names ui_controller actually holds: it does `from .scanner import
    # scan_media_files`, so patching the scanner module would miss.
    monkeypatch.setattr(
        "media_organizer.app.ui_controller.scan_media_files",
        lambda src, formats=None: [str(f) for f in files],
    )
    monkeypatch.setattr(
        "media_organizer.app.ui_controller.extract_metadata_batch",
        lambda paths, chunk_size=None: {p: {} for p in paths},
    )

    active = 0
    max_active = 0
    lock = threading.Lock()

    def tracked_organize(files, dest, metadata_by_path, operation, dry_run=False,
                         tag_order=None, use_earliest=False):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return [(str(files[0]), Placement.WROTE)]

    monkeypatch.setattr("media_organizer.app.ui_controller.organize_files", tracked_organize)

    controller = MediaOrganizerController()
    try:
        for max_workers in (1, 2, 3):
            os.environ['MEDIA_ORGANIZER_MAX_WORKERS'] = str(max_workers)
            max_active = 0

            controller.organize_batch(
                str(source), str(dest), 'copy', True, None, False,
                formats=None, max_workers=max_workers,
            )

            assert max_active > 0, "organize_files was never called - test proves nothing"
            assert max_active <= max_workers, (
                f"Too many concurrent workers: {max_active} (limit {max_workers})"
            )
    finally:
        os.environ.pop('MEDIA_ORGANIZER_MAX_WORKERS', None)
