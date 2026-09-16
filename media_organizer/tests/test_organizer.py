import tempfile
from pathlib import Path
from media_organizer.app.organizer import Placement, organize_files, get_organize_preview
from media_organizer.app.utils import ensure_dir
import shutil
import os
import pytest

def fake_extract_datetime(file_path, tags=None):
    # Return a fixed date for .jpg, None for .bad
    if str(file_path).endswith('.jpg'):
        return '2022:01:02 12:00:00'
    return None

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
    monkeypatch.setattr('media_organizer.app.organizer.extract_datetime', fake_extract_datetime)
    monkeypatch.setattr('media_organizer.app.organizer.parse_exif_date', fake_parse_exif_date)

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

def test_organize_files_is_idempotent_across_runs(tmp_path):
    """The 'top up' guarantee: re-organizing the same source adds nothing."""
    src = tmp_path / 'src' / 'a.jpg'
    src.parent.mkdir()
    src.write_bytes(b'photo')
    dest = tmp_path / 'lib'

    first = organize_files([str(src)], dest, operation='copy')
    second = organize_files([str(src)], dest, operation='copy')

    month = dest / '2022' / '01'
    assert [p.name for p in month.iterdir()] == ['a.jpg']
    # Overwriting would also leave one file, so assert it was *skipped*.
    assert [outcome for _, outcome in first] == [Placement.WROTE]
    assert [outcome for _, outcome in second] == [Placement.SKIPPED_IDENTICAL]


def test_organize_files_keeps_distinct_files_sharing_a_name(tmp_path):
    a = tmp_path / 'one' / 'a.jpg'
    a.parent.mkdir()
    a.write_bytes(b'first photo')
    b = tmp_path / 'two' / 'a.jpg'
    b.parent.mkdir()
    b.write_bytes(b'second photo')
    dest = tmp_path / 'lib'

    organize_files([str(a), str(b)], dest, operation='copy')

    month = dest / '2022' / '01'
    assert sorted(p.name for p in month.iterdir()) == ['a.jpg', 'a_1.jpg']
    assert sorted(p.read_bytes() for p in month.iterdir()) == [b'first photo', b'second photo']


def test_organize_files_skip(tmp_path):
    f1 = tmp_path / 'a.bad'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, operation='copy', dry_run=False)
    # Should not create any dest file for skipped
    dest = tmp_path / '2022' / '01' / 'a.bad'
    assert not dest.exists()
