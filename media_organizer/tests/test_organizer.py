from pathlib import Path
from media_organizer.app.organizer import Placement, organize_files
import pytest


def meta_for(path, date_str=None):
    return {path: ({"EXIF:CreateDate": date_str} if date_str else {})}


def test_organize_files_dry_run(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, meta_for(str(f1), '2022:01:02 12:00:00'),
                   operation='copy', dry_run=True)
    dest = tmp_path / '2022' / '01' / 'a.jpg'
    assert not dest.exists()


def test_organize_files_copy(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, meta_for(str(f1), '2022:01:02 12:00:00'),
                   operation='copy', dry_run=False)
    dest = tmp_path / '2022' / '01' / 'a.jpg'
    assert dest.exists()
    assert f1.exists()


def test_organize_files_move(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, meta_for(str(f1), '2022:01:02 12:00:00'),
                   operation='move', dry_run=False)
    dest = tmp_path / '2022' / '01' / 'a.jpg'
    assert dest.exists()
    assert not f1.exists()


def test_organize_files_no_date_goes_to_no_metadata(tmp_path):
    f1 = tmp_path / 'a.bad'
    f1.write_bytes(b'x')
    organize_files([str(f1)], tmp_path, meta_for(str(f1)), operation='copy', dry_run=False)
    dest = tmp_path / 'no_metadata' / 'a.bad'
    assert dest.exists()


def test_organize_files_is_idempotent_across_runs(tmp_path):
    src = tmp_path / 'src' / 'a.jpg'
    src.parent.mkdir()
    src.write_bytes(b'photo')
    dest = tmp_path / 'lib'
    metadata = meta_for(str(src), '2022:01:02 12:00:00')

    first = organize_files([str(src)], dest, metadata, operation='copy')
    second = organize_files([str(src)], dest, metadata, operation='copy')

    month = dest / '2022' / '01'
    assert [p.name for p in month.iterdir()] == ['a.jpg']
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
    metadata = {**meta_for(str(a), '2022:01:02'), **meta_for(str(b), '2022:01:02')}

    organize_files([str(a), str(b)], dest, metadata, operation='copy')

    month = dest / '2022' / '01'
    assert sorted(p.name for p in month.iterdir()) == ['a.jpg', 'a_1.jpg']


def test_organize_files_uses_earliest_when_requested(tmp_path):
    f1 = tmp_path / 'a.jpg'
    f1.write_bytes(b'x')
    metadata = {str(f1): {
        "EXIF:CreateDate": "2022:06:15",
        "QuickTime:TrackCreateDate": "2020:01:01",
    }}

    organize_files([str(f1)], tmp_path, metadata, operation='copy',
                   tag_order=["CreateDate", "TrackCreateDate"], use_earliest=True)

    assert (tmp_path / '2020' / '01' / 'a.jpg').exists()
