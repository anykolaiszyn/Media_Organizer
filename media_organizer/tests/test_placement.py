"""Collision-safe file placement.

The organizer must never lose a photo. Two distinct files that want the same
destination name must both survive; the same photo arriving twice must not be
duplicated. These are the guarantees that make repeated "top up" runs safe.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest

from media_organizer.app.organizer import Placement, place_file
from media_organizer.app.utils import files_identical


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class TestFilesIdentical:
    def test_identical_content(self, tmp_path):
        a = write(tmp_path / 'a.jpg', b'same bytes')
        b = write(tmp_path / 'b.jpg', b'same bytes')
        assert files_identical(a, b) is True

    def test_same_size_different_content(self, tmp_path):
        a = write(tmp_path / 'a.jpg', b'aaaa')
        b = write(tmp_path / 'b.jpg', b'bbbb')
        assert files_identical(a, b) is False

    def test_different_size(self, tmp_path):
        a = write(tmp_path / 'a.jpg', b'short')
        b = write(tmp_path / 'b.jpg', b'considerably longer content')
        assert files_identical(a, b) is False


class TestPlaceFile:
    def test_writes_to_a_free_path(self, tmp_path):
        src = write(tmp_path / 'src' / 'IMG.jpg', b'photo')
        dest = tmp_path / 'lib' / '2022' / '01' / 'IMG.jpg'

        outcome, final = place_file(src, dest, operation='copy')

        assert outcome is Placement.WROTE
        assert final == dest
        assert dest.read_bytes() == b'photo'

    def test_skips_when_an_identical_file_is_already_there(self, tmp_path):
        src = write(tmp_path / 'src' / 'IMG.jpg', b'photo')
        dest = write(tmp_path / 'lib' / 'IMG.jpg', b'photo')

        outcome, final = place_file(src, dest, operation='copy')

        assert outcome is Placement.SKIPPED_IDENTICAL
        assert final == dest
        assert [p.name for p in dest.parent.iterdir()] == ['IMG.jpg']

    def test_renames_when_a_different_file_holds_the_name(self, tmp_path):
        src = write(tmp_path / 'src' / 'IMG.jpg', b'new photo')
        dest = write(tmp_path / 'lib' / 'IMG.jpg', b'old photo')

        outcome, final = place_file(src, dest, operation='copy')

        assert outcome is Placement.RENAMED
        assert final == tmp_path / 'lib' / 'IMG_1.jpg'
        assert final.read_bytes() == b'new photo'
        assert dest.read_bytes() == b'old photo'

    def test_rename_keeps_counting_past_an_occupied_suffix(self, tmp_path):
        src = write(tmp_path / 'src' / 'IMG.jpg', b'third distinct')
        dest = write(tmp_path / 'lib' / 'IMG.jpg', b'first')
        write(tmp_path / 'lib' / 'IMG_1.jpg', b'second')

        outcome, final = place_file(src, dest, operation='copy')

        assert outcome is Placement.RENAMED
        assert final.name == 'IMG_2.jpg'

    def test_move_removes_the_source(self, tmp_path):
        src = write(tmp_path / 'src' / 'IMG.jpg', b'photo')
        dest = tmp_path / 'lib' / 'IMG.jpg'

        outcome, final = place_file(src, dest, operation='move')

        assert outcome is Placement.WROTE
        assert not src.exists()
        assert final.read_bytes() == b'photo'

    def test_move_removes_a_source_already_filed_identically(self, tmp_path):
        src = write(tmp_path / 'src' / 'IMG.jpg', b'photo')
        dest = write(tmp_path / 'lib' / 'IMG.jpg', b'photo')

        outcome, _ = place_file(src, dest, operation='move')

        assert outcome is Placement.SKIPPED_IDENTICAL
        assert not src.exists()
        assert dest.read_bytes() == b'photo'

    def test_copy_keeps_a_source_already_filed_identically(self, tmp_path):
        src = write(tmp_path / 'src' / 'IMG.jpg', b'photo')
        dest = write(tmp_path / 'lib' / 'IMG.jpg', b'photo')

        place_file(src, dest, operation='copy')

        assert src.exists()

    def test_dry_run_mutates_nothing(self, tmp_path):
        src = write(tmp_path / 'src' / 'IMG.jpg', b'photo')
        dest = tmp_path / 'lib' / 'IMG.jpg'

        outcome, final = place_file(src, dest, operation='move', dry_run=True)

        assert outcome is Placement.WROTE
        assert final == dest
        assert src.exists()
        assert not dest.parent.exists()

    def test_dry_run_still_reports_an_identical_file_as_skipped(self, tmp_path):
        src = write(tmp_path / 'src' / 'IMG.jpg', b'photo')
        dest = write(tmp_path / 'lib' / 'IMG.jpg', b'photo')

        outcome, _ = place_file(src, dest, operation='move', dry_run=True)

        assert outcome is Placement.SKIPPED_IDENTICAL
        assert src.exists()

    def test_placing_the_same_source_twice_is_idempotent(self, tmp_path):
        src = write(tmp_path / 'src' / 'IMG.jpg', b'photo')
        dest = tmp_path / 'lib' / 'IMG.jpg'

        first, _ = place_file(src, dest, operation='copy')
        second, _ = place_file(src, dest, operation='copy')

        assert first is Placement.WROTE
        assert second is Placement.SKIPPED_IDENTICAL
        assert [p.name for p in dest.parent.iterdir()] == ['IMG.jpg']


class TestConcurrentPlacement:
    def test_distinct_files_sharing_a_name_all_survive(self, tmp_path):
        """The race the old exists()-then-write logic lost files to."""
        lib = tmp_path / 'lib'
        count = 24
        sources = [
            write(tmp_path / 'src' / str(i) / 'IMG.jpg', f'photo-{i:02d}'.encode())
            for i in range(count)
        ]

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda s: place_file(s, lib / 'IMG.jpg', operation='copy'), sources))

        written = sorted(p.read_bytes() for p in lib.iterdir() if p.is_file())
        assert written == sorted(f'photo-{i:02d}'.encode() for i in range(count))

    def test_identical_files_racing_for_a_name_are_deduped_to_one(self, tmp_path):
        """Idempotency must survive concurrency, not just sequential re-runs."""
        lib = tmp_path / 'lib'
        count = 16
        sources = [
            write(tmp_path / 'src' / str(i) / 'IMG.jpg', b'the very same photo')
            for i in range(count)
        ]

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = [
                outcome for outcome, _ in
                pool.map(lambda s: place_file(s, lib / 'IMG.jpg', operation='copy'), sources)
            ]

        assert [p.name for p in lib.iterdir()] == ['IMG.jpg']
        assert outcomes.count(Placement.WROTE) == 1
        assert outcomes.count(Placement.SKIPPED_IDENTICAL) == count - 1

    def test_leaves_no_temp_files_behind(self, tmp_path):
        lib = tmp_path / 'lib'
        sources = [
            write(tmp_path / 'src' / str(i) / 'IMG.jpg', f'photo-{i}'.encode())
            for i in range(8)
        ]

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda s: place_file(s, lib / 'IMG.jpg', operation='copy'), sources))

        assert [p.name for p in lib.iterdir() if p.name.startswith('.mo_tmp')] == []
