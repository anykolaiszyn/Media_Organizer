"""Batch extraction: one ExifTool call per chunk, exact tag matching, real cancel."""
import json
import subprocess

import pytest

from media_organizer.app import batch_events as ev
from media_organizer.app.metadata_extractor import (
    cancel_exiftool,
    extract_metadata,
    extract_metadata_batch,
    select_datetime,
    select_earliest_datetime,
)


class FakeCompletedProcess:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class FakePopen:
    """Stands in for subprocess.Popen: records the command, answers communicate()."""
    instances = []

    def __init__(self, cmd, stdout=None, stderr=None, text=None, startupinfo=None):
        self.cmd = cmd
        self.returncode = 0
        self.terminated = False
        self.killed = False
        FakePopen.instances.append(self)

    def communicate(self, timeout=None):
        raise NotImplementedError("set via monkeypatch per test")

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def _json_for(paths, extra=None):
    """Build the JSON array ExifTool -j would emit for these paths."""
    extra = extra or {}
    return json.dumps([
        {"SourceFile": p, "DateTimeOriginal": "2024:01:02 03:04:05", **extra.get(p, {})}
        for p in paths
    ])


@pytest.fixture(autouse=True)
def reset_fake_popen():
    FakePopen.instances.clear()
    yield
    FakePopen.instances.clear()


def test_a_healthy_chunk_takes_exactly_one_popen_call(monkeypatch, tmp_path):
    paths = [str(tmp_path / f"{i}.jpg") for i in range(5)]

    def fake_communicate(self, timeout=None):
        return _json_for(paths), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    result = extract_metadata_batch(paths, chunk_size=10)

    assert len(FakePopen.instances) == 1
    assert set(result.keys()) == set(paths)
    assert all("error" not in v for v in result.values())


def test_results_are_matched_by_sourcefile_not_position(monkeypatch, tmp_path):
    paths = [str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg")]

    def fake_communicate(self, timeout=None):
        # Deliberately return them in reverse order.
        return _json_for(list(reversed(paths))), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    result = extract_metadata_batch(paths, chunk_size=10)

    assert result[paths[0]]["SourceFile"] == paths[0]
    assert result[paths[1]]["SourceFile"] == paths[1]


def test_one_bad_file_is_isolated_by_bisection(monkeypatch, tmp_path):
    """A chunk that fails as a whole must not fail every file in it."""
    paths = [str(tmp_path / f"{i}.jpg") for i in range(4)]
    bad = paths[2]

    def fake_communicate(self, timeout=None):
        called_paths = [c for c in self.cmd if c in paths]
        if bad in called_paths and len(called_paths) > 1:
            raise subprocess.TimeoutExpired(cmd=self.cmd, timeout=1)
        if called_paths == [bad]:
            raise subprocess.TimeoutExpired(cmd=self.cmd, timeout=1)
        return _json_for(called_paths), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    result = extract_metadata_batch(paths, chunk_size=10)

    assert len(result) == 4
    assert "error" in result[bad]
    assert result[bad]["type"] == "timeout"
    for p in paths:
        if p != bad:
            assert "error" not in result[p]


def test_bisection_never_runs_two_popens_concurrently(monkeypatch, tmp_path):
    """Cancellation depends on at most one process being in flight at a time.

    Forces full bisection down to single files (any chunk with more than one
    real file path fails) so recursion is actually exercised, then checks no
    two communicate() calls were ever open at once.
    """
    paths = [str(tmp_path / f"{i}.jpg") for i in range(4)]
    concurrent = {"count": 0, "max": 0}

    def fake_communicate(self, timeout=None):
        concurrent["count"] += 1
        concurrent["max"] = max(concurrent["max"], concurrent["count"])
        try:
            real_paths = [c for c in self.cmd if c in paths]
            if len(real_paths) > 1:
                raise subprocess.TimeoutExpired(cmd=self.cmd, timeout=1)
            return _json_for(real_paths), ""
        finally:
            concurrent["count"] -= 1

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    extract_metadata_batch(paths, chunk_size=10)

    assert concurrent["max"] == 1


def test_extraction_progress_is_emitted_per_chunk(monkeypatch, tmp_path):
    paths = [str(tmp_path / f"{i}.jpg") for i in range(6)]

    def fake_communicate(self, timeout=None):
        called_paths = [c for c in self.cmd if c in paths]
        return _json_for(called_paths), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    events = []
    extract_metadata_batch(paths, chunk_size=2, emit=events.append)

    progress = [e for e in events if isinstance(e, ev.ExtractionProgress)]
    assert len(progress) == 3
    assert progress[-1].chunks_done == 3
    assert progress[-1].chunks_total == 3
    assert progress[-1].files_done == 6


def test_cancel_exiftool_terminates_the_registered_process(monkeypatch, tmp_path):
    paths = [str(tmp_path / "a.jpg")]
    registered = {}

    def fake_communicate(self, timeout=None):
        registered['proc'] = self
        cancel_exiftool()
        return _json_for(paths), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    extract_metadata_batch(paths, chunk_size=10)

    assert registered['proc'].terminated is True


def test_extract_metadata_single_file_uses_chunk_size_one(monkeypatch, tmp_path):
    path = str(tmp_path / "a.jpg")

    def fake_communicate(self, timeout=None):
        assert len([c for c in self.cmd if c == path]) == 1
        return _json_for([path]), ""

    monkeypatch.setattr(FakePopen, "communicate", fake_communicate)
    monkeypatch.setattr("media_organizer.app.metadata_extractor.subprocess.Popen", FakePopen)

    result = extract_metadata(path)

    assert result["SourceFile"] == path


def test_select_datetime_matches_the_exact_tag_only():
    """Regression for the endswith bug: CreateDate must not resolve to MediaCreateDate."""
    metadata = {
        "QuickTime:MediaCreateDate": "2020:01:01 00:00:00",
        "EXIF:CreateDate": "2022:06:15 12:00:00",
    }

    assert select_datetime(metadata, tags=["CreateDate"]) == "2022:06:15 12:00:00"


def test_select_datetime_returns_none_when_nothing_matches():
    assert select_datetime({"EXIF:ModifyDate": "2022:01:01"}, tags=["CreateDate"]) is None


def test_select_earliest_datetime_does_not_double_count_an_exact_match():
    metadata = {"EXIF:CreateDate": "2022:06:15 12:00:00"}

    # A single matching tag must not appear twice and break sorting/selection.
    result = select_earliest_datetime(metadata, tags=["CreateDate"])

    assert result == "2022:06:15 12:00:00"


def test_select_earliest_datetime_picks_the_earliest_across_tags():
    metadata = {
        "EXIF:CreateDate": "2022:06:15 12:00:00",
        "QuickTime:TrackCreateDate": "2020:01:01 00:00:00",
    }

    result = select_earliest_datetime(metadata, tags=["CreateDate", "TrackCreateDate"])

    assert result == "2020:01:01 00:00:00"
