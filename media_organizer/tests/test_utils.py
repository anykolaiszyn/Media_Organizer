from media_organizer.app.utils import ensure_dir, is_supported_file, parse_exif_date
from pathlib import Path
import tempfile

def test_ensure_dir_creates(tmp_path):
    d = tmp_path / 'foo' / 'bar'
    ensure_dir(d)
    assert d.exists() and d.is_dir()

def test_is_supported_file():
    assert is_supported_file('photo.jpg', ['.jpg'])
    assert not is_supported_file('doc.txt', ['.jpg'])

def test_parse_exif_date():
    assert parse_exif_date('2022:01:02 12:00:00').year == 2022
    assert parse_exif_date('2022:01:02').month == 1
    assert parse_exif_date('bad string') is None
