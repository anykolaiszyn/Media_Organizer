
import pytest
from media_organizer.app.metadata_extractor import extract_metadata, extract_datetime_with_tags

class DummyExifTool:
    def __init__(self, result=None, raise_exc=False):
        self.result = result
        self.raise_exc = raise_exc
    def __enter__(self):
        if self.raise_exc:
            raise RuntimeError("exiftool error")
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    def process_json(self, file_path):
        if self.raise_exc:
            raise RuntimeError("exiftool error")
        return self.result or {}

def test_extract_metadata_success(monkeypatch):
    monkeypatch.setattr('exiftool_wrapper.ExifToolWrapper', lambda *a, **k: DummyExifTool(result={'A': 1}))
    assert extract_metadata('file.jpg') == {'A': 1}

def test_extract_metadata_error(monkeypatch):
    monkeypatch.setattr('exiftool_wrapper.ExifToolWrapper', lambda *a, **k: DummyExifTool(raise_exc=True))
    assert extract_metadata('file.jpg') == {}

def test_extract_metadata_empty(monkeypatch):
    monkeypatch.setattr('exiftool_wrapper.ExifToolWrapper', lambda *a, **k: DummyExifTool(result={}))
    assert extract_metadata('file.jpg') == {}
