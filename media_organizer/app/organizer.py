from enum import Enum
import os
from pathlib import Path
import shutil
import threading
from uuid import uuid4
from .logger import logger
from .metadata_extractor import select_datetime, select_earliest_datetime
from .utils import ensure_dir, files_identical, parse_exif_date

_MAX_RENAME_ATTEMPTS = 10000

# A destination being claimed or filled is briefly unreadable on Windows and
# briefly empty everywhere. Serialising per directory keeps workers from
# comparing against another worker's half-written file.
_placement_locks = {}
_placement_locks_guard = threading.Lock()


def _placement_lock(directory):
    key = str(directory)
    with _placement_locks_guard:
        lock = _placement_locks.get(key)
        if lock is None:
            lock = _placement_locks[key] = threading.Lock()
        return lock


class Placement(Enum):
    WROTE = 'wrote'
    SKIPPED_IDENTICAL = 'skipped_identical'
    RENAMED = 'renamed'


def _candidate_paths(dest_path):
    yield dest_path, Placement.WROTE
    for i in range(1, _MAX_RENAME_ATTEMPTS):
        yield dest_path.parent / f"{dest_path.stem}_{i}{dest_path.suffix}", Placement.RENAMED


def place_file(src, dest_path, operation='copy', dry_run=False):
    """Put src at dest_path, never overwriting content that differs from it.

    Returns (Placement, final_path). An occupied name whose content matches src
    is left alone; one whose content differs pushes src to the next free
    `_1`, `_2`, ... name. Names are claimed with O_CREAT|O_EXCL so concurrent
    workers cannot both win the same one.
    """
    src = Path(src)
    dest_path = Path(dest_path)

    with _placement_lock(dest_path.parent):
        for candidate, outcome in _candidate_paths(dest_path):
            if dry_run:
                if not candidate.exists():
                    return outcome, candidate
                if files_identical(src, candidate):
                    return Placement.SKIPPED_IDENTICAL, candidate
                continue

            ensure_dir(candidate.parent)
            try:
                os.close(os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            except FileExistsError:
                if files_identical(src, candidate):
                    if operation == 'move':
                        os.remove(src)
                    return Placement.SKIPPED_IDENTICAL, candidate
                continue

            _fill_claimed_path(src, candidate, operation)
            return outcome, candidate

    raise RuntimeError(
        f"No free name for {dest_path} after {_MAX_RENAME_ATTEMPTS} attempts"
    )


def _fill_claimed_path(src, candidate, operation):
    """Populate a name we already own, never leaving a partial file under it."""
    if operation == 'move':
        try:
            os.replace(src, candidate)
            return
        except OSError:
            pass  # different volume; fall back to copy then delete

    tmp = candidate.parent / f".mo_tmp_{uuid4().hex}"
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, candidate)
    except BaseException:
        for leftover in (tmp, candidate):
            try:
                leftover.unlink()
            except OSError:
                pass
        raise
    if operation == 'move':
        os.remove(src)

def organize_files(files, dest_folder, metadata_by_path, operation='copy', dry_run=False,
                   tag_order=None, use_earliest=False):
    """File each path under dest_folder/YYYY/MM using its already-extracted metadata.

    Returns a list of (source_path, Placement) so callers can report accurate
    counts instead of inferring them from log text.
    """
    dest_folder = Path(dest_folder)
    results = []
    for file_path in files:
        metadata = metadata_by_path.get(str(file_path), {})
        dest_path = _destination_for(file_path, dest_folder, metadata, tag_order, use_earliest)
        try:
            outcome, final_path = place_file(file_path, dest_path, operation, dry_run)
        except Exception as e:
            logger.error(f"Failed to {operation} {file_path}: {e}")
            continue
        results.append((str(file_path), outcome))
        _log_placement(file_path, final_path, operation, outcome, dry_run)
    return results


def _destination_for(file_path, dest_folder, metadata, tag_order, use_earliest):
    """Where this file belongs: a dated folder, or a fallback bucket."""
    if 'error' in metadata:
        logger.warning(f"No usable metadata for {file_path}: {metadata['error']}")
        return dest_folder / "no_metadata" / Path(file_path).name

    if use_earliest:
        date_str = select_earliest_datetime(metadata, tags=tag_order)
    else:
        date_str = select_datetime(metadata, tags=tag_order)

    name = Path(file_path).name
    if not date_str:
        return dest_folder / "no_metadata" / name
    dt = parse_exif_date(date_str)
    if not dt:
        return dest_folder / "unsorted" / name
    return dest_folder / str(dt.year) / f"{dt.month:02d}" / name


def _log_placement(src, final_path, operation, outcome, dry_run):
    prefix = "[DRY RUN] Would " if dry_run else ""
    if outcome is Placement.SKIPPED_IDENTICAL:
        logger.info(f"{prefix}skip {src}: identical file already at {final_path}")
    else:
        logger.info(f"{prefix}{operation} {src} -> {final_path}")
