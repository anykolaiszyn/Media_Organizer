import tempfile
from pathlib import Path
from media_organizer.app.organizer import organize_files, get_organize_preview
from media_organizer.app.utils import ensure_dir
import shutil
import os
import pytest

def fake_extract_datetime(file_path, tags=None):
    # Return a fixed date for .jpg, fail for .bad
    if str(file_path).endswith('.jpg'):
        return '2022:01:02 12:00:00'
    if str(file_path).endswith('.bad'):
        return None
    return '2022:01:02'

def fake_parse_exif_date(date_str):
    from datetime import datetime
    try:
        return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    except Exception:
        try:
            return datetime.strptime(date_str, '%Y:%m:%d')
        except Exception:
            return None

@pytest.fixture(autouse=True)
def patch_extract(monkeypatch):
    monkeypatch.setattr('app.organizer.extract_datetime', fake_extract_datetime)
    monkeypatch.setattr('app.organizer.parse_exif_date', fake_parse_exif_date)

def test_get_organize_preview(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f2 = tmp_path / 'b.bad'
    f1.write_bytes(b'x')
    f2.write_bytes(b'x')
    preview, skipped = get_organize_preview([str(f1), str(f2)], tmp_path)
    assert (str(f1), str(tmp_path / '2022' / '01' / 'a.jpg')) in preview
    # .bad file should be in preview as no_metadata, not in skipped
    assert (str(f2), str(tmp_path / 'no_metadata' / 'b.bad') + ' (no metadata)') in preview

def test_organize_files_dry_run(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, operation='copy', dry_run=True)
    # File should not be copied in dry run
    dest = tmp_path / '2022' / '01' / 'a.jpg'
    assert not dest.exists()

def test_organize_files_copy(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, operation='copy', dry_run=False)
    dest = tmp_path / '2022' / '01' / 'a.jpg'
    assert dest.exists()
    assert f1.exists()  # Copy does not remove source

def test_organize_files_move(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, operation='move', dry_run=False)
    dest = tmp_path / '2022' / '01' / 'a.jpg'
    assert dest.exists()
    assert not f1.exists()  # Move removes source

def test_organize_files_skip(tmp_path):
    f1 = tmp_path / 'a.bad'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, operation='copy', dry_run=False)
    # Should not create any dest file for skipped
    dest = tmp_path / '2022' / '01' / 'a.bad'
    assert not dest.exists()
