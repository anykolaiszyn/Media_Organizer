"""Events a batch publishes as it runs.

The controller knows nothing about queues or Tk. It calls a plain `emit`
callable; the GUI backs that with a queue.Queue drained on the main thread,
and tests back it with a list.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Scanned:
    total: int


@dataclass(frozen=True)
class FileStarted:
    path: str


@dataclass(frozen=True)
class FileDone:
    path: str
    outcome: Optional[str]      # a Placement value, or None when errored
    error: Optional[str]
    completed: int
    total: int
    eta_seconds: int


@dataclass(frozen=True)
class LogLine:
    text: str


@dataclass(frozen=True)
class Finished:
    counts: dict
    cancelled: bool
    elapsed: float


@dataclass(frozen=True)
class ScanProgress:
    percent: float


@dataclass(frozen=True)
class ScanFound:
    path: str
    count: int


@dataclass(frozen=True)
class ScanFinished:
    total: int


@dataclass(frozen=True)
class ExtractionProgress:
    chunks_done: int
    chunks_total: int
    files_done: int
    files_total: int
