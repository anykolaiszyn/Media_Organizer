from app.metadata_extractor import extract_datetime
import tempfile
from pathlib import Path
import shutil
import sys
import os

def test_extract_datetime_handles_missing(monkeypatch):
    # Patch subprocess.run to simulate exiftool not found
    monkeypatch.setattr('subprocess.run', lambda *a, **k: type('R', (), {'stdout': '', 'returncode': 0})())
    assert extract_datetime('nofile.jpg') is None
