import pytest
from media_organizer.app.ui_controller import MediaOrganizerController
from pathlib import Path

class DummyLogger:
    def __init__(self):
        self.logs = []

    def __call__(self, msg):
        self.logs.append(msg)

def fake_scan_media_files(source, formats=None):
    # Return two files
    return [str(source / 'a.jpg'), str(source / 'b.jpg')]

def fake_get_organize_preview(files, dest, tag_order=None):
    # Pretend one file is valid, one is skipped
    if len(files) == 1:
        return [(files[0], str(Path(dest) / '2022/01/a.jpg'))], []
    return [(files[0], str(Path(dest) / '2022/01/a.jpg'))], [(files[1], 'No date metadata found')]

def test_get_preview_list(tmp_path, monkeypatch):
    logger = DummyLogger()
    ctrl = MediaOrganizerController(log_callback=logger)
    monkeypatch.setattr('app.ui_controller.scan_media_files', fake_scan_media_files)
    monkeypatch.setattr('app.ui_controller.get_organize_preview', fake_get_organize_preview)
    preview, skipped = ctrl.get_preview_list(tmp_path, tmp_path, tag_order=None, formats=['.jpg'])
    assert len(preview) == 2
    assert len(skipped) == 0
    assert preview[0][0].endswith('a.jpg')
    assert preview[1][0].endswith('b.jpg')
