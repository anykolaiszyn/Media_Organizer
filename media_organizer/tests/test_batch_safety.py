import os
import pytest
from media_organizer.app.ui_controller import MediaOrganizerController
import threading

import time
import sys

def test_batch_safety(monkeypatch, tmp_path):
    # Simulate a large number of files
    files = [tmp_path / f"file_{i}.jpg" for i in range(10)]
    for f in files:
        f.write_text("fake data")

    # Patch scan_media_files to return our fake files
    monkeypatch.setattr(
        "media_organizer.app.scanner.scan_media_files",
        lambda source, formats=None: [str(f) for f in files]
    )

    # Track concurrent calls
    active = 0
    max_active = 0
    lock = threading.Lock()
    def tracked_organize(files, dest, operation, dry_run=False, tag_order=None, duplicate_mode='overwrite'):
        nonlocal active, max_active
        with lock:
            active += 1
            if active > max_active:
                max_active = active
        time.sleep(0.1)
        with lock:
            active -= 1
    monkeypatch.setattr("media_organizer.app.organizer.organize_files", tracked_organize)

    controller = MediaOrganizerController()
    # Test several concurrency levels
    for max_workers in (1, 2, 3):
        os.environ['MEDIA_ORGANIZER_MAX_WORKERS'] = str(max_workers)
        max_active = 0
        # Call organize_batch with required arguments
        controller.organize_batch(
            str(tmp_path),  # source
            str(tmp_path),  # dest
            'copy',         # operation
            True,           # dry_run
            None,           # tag_order
            'overwrite',    # duplicate_mode
            False,          # use_earliest
            formats=None,
            eta_callback=None,
            max_workers=max_workers
        )
        assert max_active <= max_workers, f"Too many concurrent workers: {max_active} (limit {max_workers})"
    if 'MEDIA_ORGANIZER_MAX_WORKERS' in os.environ:
        del os.environ['MEDIA_ORGANIZER_MAX_WORKERS']
