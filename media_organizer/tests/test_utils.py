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


import csv
from media_organizer.app.utils import write_csv_safe


def test_write_csv_safe_round_trips_embedded_quotes_and_commas(tmp_path):
    out = tmp_path / 'out.csv'
    write_csv_safe(out, ['filename', 'note'], [
        ('IMG "final", v2.jpg', 'has a comma, and quotes "here"'),
    ])

    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))

    assert rows[0] == ['filename', 'note']
    assert rows[1] == ['IMG "final", v2.jpg', 'has a comma, and quotes "here"']


def test_write_csv_safe_neutralizes_leading_formula_characters(tmp_path):
    out = tmp_path / 'out.csv'
    write_csv_safe(out, ['filename'], [
        ('=cmd|/c calc.exe',),
        ('+1+1',),
        ('-1',),
        ('@SUM(A1:A2)',),
        ('normal_name.jpg',),
    ])

    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))[1:]

    assert [r[0] for r in rows] == [
        "'=cmd|/c calc.exe", "'+1+1", "'-1", "'@SUM(A1:A2)", "normal_name.jpg",
    ]


def test_write_csv_safe_handles_none_as_an_empty_cell(tmp_path):
    out = tmp_path / 'out.csv'
    write_csv_safe(out, ['filename', 'error'], [('a.jpg', None)])

    with open(out, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))

    assert rows[1] == ['a.jpg', '']
