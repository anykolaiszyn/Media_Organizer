import pytest
from media_organizer.app.scanner import scan_media_files
from media_organizer.app.config import SUPPORTED_FORMATS
from pathlib import Path
import tempfile


def test_scan_media_files_finds_supported(tmp_path):
    # Create test files
    img = tmp_path / 'photo.jpg'
    vid = tmp_path / 'video.mp4'
    txt = tmp_path / 'note.txt'
    img.write_bytes(b'fake')
    vid.write_bytes(b'fake')
    txt.write_bytes(b'fake')
    # Create subfolder
    sub = tmp_path / 'sub'
    sub.mkdir()
    sub_img = sub / 'subphoto.jpeg'
    sub_img.write_bytes(b'fake')
    # Scan
    found = scan_media_files(str(tmp_path))
    assert str(img) in found
    assert str(vid) in found
    assert str(sub_img) in found
    assert str(txt) not in found
