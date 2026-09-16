"""Refusing layouts where organizing would re-scan its own output.

Only nesting the destination *inside* the source is harmful: the recursive scan
then picks up already-filed photos on every later run. The reverse (a staging
folder living inside the library) is a legitimate layout and must stay allowed.
"""
import pytest

from media_organizer.app.utils import check_source_dest_overlap


def test_rejects_destination_inside_source(tmp_path):
    source = tmp_path / 'Photos'
    source.mkdir()
    dest = source / 'Sorted'

    with pytest.raises(ValueError):
        check_source_dest_overlap(source, dest)


def test_rejects_source_and_destination_being_the_same(tmp_path):
    with pytest.raises(ValueError):
        check_source_dest_overlap(tmp_path, tmp_path)


def test_allows_source_inside_destination(tmp_path):
    dest = tmp_path / 'Library'
    source = dest / 'Inbox'
    source.mkdir(parents=True)

    check_source_dest_overlap(source, dest)


def test_allows_siblings(tmp_path):
    source = tmp_path / 'Inbox'
    dest = tmp_path / 'Library'
    source.mkdir()
    dest.mkdir()

    check_source_dest_overlap(source, dest)


def test_organize_batch_refuses_before_touching_anything(tmp_path):
    """The guard must fire at batch start, not per file."""
    from media_organizer.app.ui_controller import MediaOrganizerController

    source = tmp_path / 'Photos'
    source.mkdir()
    (source / 'a.jpg').write_bytes(b'photo')
    dest = source / 'Sorted'

    controller = MediaOrganizerController()
    with pytest.raises(ValueError):
        controller.organize_batch(
            str(source), str(dest), 'copy', False, None, False,
        )

    assert not dest.exists()


def test_error_names_both_paths(tmp_path):
    source = tmp_path / 'Photos'
    source.mkdir()
    dest = source / 'Sorted'

    with pytest.raises(ValueError) as excinfo:
        check_source_dest_overlap(source, dest)

    message = str(excinfo.value)
    assert 'Sorted' in message
    assert 'Photos' in message
