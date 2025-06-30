import threading
import time
import pytest
from media_organizer.app.ui_controller import MediaOrganizerController

def test_scan_media_files_async(tmp_path):
    # Create dummy files
    files = [tmp_path / f"file{i}.jpg" for i in range(10)]
    for f in files:
        f.write_text("test")
    found = []
    progress = []
    done = []
    controller = MediaOrganizerController()
    def found_cb(f):
        found.append(f)
    def progress_cb(p):
        progress.append(p)
    def done_cb():
        done.append(True)
    controller.scan_media_files_async(str(tmp_path), formats=['.jpg'], progress_callback=progress_cb, found_callback=found_cb, done_callback=done_cb)
    # Wait for thread to finish
    for _ in range(50):
        if done:
            break
        time.sleep(0.05)
    assert len(found) == 10
    assert progress[-1] == 100
    assert done
