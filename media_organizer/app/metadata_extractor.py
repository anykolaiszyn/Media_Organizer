
from pathlib import Path
from .logger import log
import json
import subprocess
import sys
import threading
from media_organizer.app.exiftool_check import get_exiftool_path
from media_organizer.app.batch_events import ExtractionProgress

_current_chunk_process = None
_current_chunk_process_lock = threading.Lock()


def cancel_exiftool():
    global _current_chunk_process
    with _current_chunk_process_lock:
        proc = _current_chunk_process
    if proc is None:
        return
    try:
        proc.terminate()
        log('[CANCEL] ExifTool process terminated by user.')
    except Exception as e:
        log(f'[CANCEL] Failed to terminate ExifTool process: {e}')
        try:
            proc.kill()
            log('[CANCEL] ExifTool process force-killed by user.')
        except Exception as e2:
            log(f'[CANCEL] Failed to force-kill ExifTool process: {e2}')


def _startupinfo():
    if not sys.platform.startswith('win'):
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return info


def _run_chunk(paths, timeout):
    """One ExifTool invocation over `paths`. Returns (json_text_or_None, error_dict_or_None)."""
    global _current_chunk_process
    exiftool_path = get_exiftool_path()
    if not Path(exiftool_path).exists():
        msg = f"ExifTool executable not found at {exiftool_path}"
        return None, {"error": msg, "type": "missing_exiftool"}

    cmd = [exiftool_path, '-j', '-G', '-a', '-s'] + list(paths)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        startupinfo=_startupinfo(),
    )
    with _current_chunk_process_lock:
        _current_chunk_process = proc
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            # Drain any buffered output so the pipes don't leak. Best-effort:
            # a second failure here doesn't change the outcome, which is
            # already "timeout" either way.
            proc.communicate()
        except Exception:
            pass
        msg = f"ExifTool timed out extracting {len(paths)} file(s)"
        return None, {"error": msg, "type": "timeout"}
    finally:
        with _current_chunk_process_lock:
            _current_chunk_process = None

    if proc.returncode != 0:
        msg = stderr.strip() if stderr else f"ExifTool exited with code {proc.returncode}"
        return None, {"error": f"ExifTool returned error: {msg}", "type": "exiftool_error"}

    return stdout, None


def _extract_chunk(paths, timeout, results):
    """Extract `paths` as one chunk, bisecting into results on failure."""
    stdout, error = _run_chunk(paths, timeout)
    if error is not None:
        if len(paths) == 1:
            results[paths[0]] = error
            return
        mid = len(paths) // 2
        _extract_chunk(paths[:mid], timeout, results)
        _extract_chunk(paths[mid:], timeout, results)
        return

    try:
        entries = json.loads(stdout)
    except json.JSONDecodeError as e:
        if len(paths) == 1:
            results[paths[0]] = {
                "error": f"Failed to parse ExifTool JSON output: {e}",
                "type": "json_parse_error",
            }
            return
        mid = len(paths) // 2
        _extract_chunk(paths[:mid], timeout, results)
        _extract_chunk(paths[mid:], timeout, results)
        return

    by_source = {entry.get("SourceFile"): entry for entry in entries}
    for p in paths:
        if p in by_source:
            results[p] = by_source[p]
        else:
            results[p] = {"error": "ExifTool returned no entry for this file",
                          "type": "exiftool_error"}


def extract_metadata_batch(file_paths, chunk_size=None, emit=None):
    """Extract metadata for every path in file_paths, one ExifTool call per chunk.

    Returns {path: metadata_dict_or_error_dict}. A chunk that fails outright
    (bad exit, timeout, unparseable JSON) is bisected until the one bad file
    is isolated as a per-file error; every other file in that chunk still
    gets a real result.
    """
    import os
    if chunk_size is None:
        try:
            chunk_size = int(os.environ.get('MEDIA_ORGANIZER_CHUNK_SIZE', 200))
        except (ValueError, TypeError):
            chunk_size = 200
    chunk_size = max(1, chunk_size)

    file_paths = [str(p) for p in file_paths]
    chunks = [file_paths[i:i + chunk_size] for i in range(0, len(file_paths), chunk_size)]
    results = {}
    files_done = 0

    for i, chunk in enumerate(chunks):
        timeout = 10 + 0.5 * len(chunk)
        _extract_chunk(chunk, timeout, results)
        files_done += len(chunk)
        if emit:
            emit(ExtractionProgress(
                chunks_done=i + 1, chunks_total=len(chunks),
                files_done=files_done, files_total=len(file_paths),
            ))

    return results


def extract_metadata(file_path):
    """Single-file extraction, for the interactive Metadata Viewer tab."""
    path = str(file_path)
    return extract_metadata_batch([path], chunk_size=1)[path]


def _key_matches_tag(key, tag):
    if key.lower() == tag.lower():
        return True
    if ':' in key and key.rsplit(':', 1)[-1].lower() == tag.lower():
        return True
    return False


_ZERO_DATE_PLACEHOLDERS = {'0000:00:00 00:00:00', '0000:00:00'}


def select_datetime(metadata, tags=None):
    """First tag in priority order that has a real value in `metadata`, or None."""
    if tags is None:
        tags = ['DateTimeOriginal', 'CreateDate', 'MediaCreateDate']
    for tag in tags:
        for key, value in metadata.items():
            if _key_matches_tag(key, tag) and value not in _ZERO_DATE_PLACEHOLDERS:
                return value
    return None


def select_earliest_datetime(metadata, tags=None):
    """Earliest valid date among all matches for `tags` in `metadata`, or None."""
    from .utils import parse_exif_date
    found = []
    for tag in tags or []:
        for key, value in metadata.items():
            if _key_matches_tag(key, tag) and value not in _ZERO_DATE_PLACEHOLDERS:
                dt = parse_exif_date(value)
                if dt:
                    found.append((dt, value))
    if not found:
        return None
    found.sort(key=lambda pair: pair[0])
    return found[0][1]
