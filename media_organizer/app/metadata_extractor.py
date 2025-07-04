
from pathlib import Path
from .logger import log
import json
import subprocess
import sys
from media_organizer.app.exiftool_check import get_exiftool_path
import threading

# Track all ExifTool processes globally for robust cleanup
_exiftool_procs = set()
_exiftool_lock = threading.Lock()

def _register_exiftool_process(proc):
    with _exiftool_lock:
        _exiftool_procs.add(proc)

def _unregister_exiftool_process(proc):
    with _exiftool_lock:
        _exiftool_procs.discard(proc)

def cancel_exiftool():
    with _exiftool_lock:
        for proc in list(_exiftool_procs):
            if proc:
                terminated = False
                if hasattr(proc, 'terminate'):
                    try:
                        proc.terminate()
                        log('[CANCEL] ExifTool process terminated by user.')
                        terminated = True
                    except Exception as e:
                        log(f'[CANCEL] Failed to terminate ExifTool process: {e}')
                # On Windows, .terminate() may not always work; try .kill() as fallback
                if not terminated and hasattr(proc, 'kill'):
                    try:
                        proc.kill()
                        log('[CANCEL] ExifTool process force-killed by user.')
                    except Exception as e:
                        log(f'[CANCEL] Failed to force-kill ExifTool process: {e}')
            _exiftool_procs.discard(proc)

def extract_metadata(file_path):
    """
    Extract all metadata from a file using the exiftool executable. Returns a dict of tag: value.
    """
    file_path = str(Path(file_path))
    exiftool_path = get_exiftool_path()
    from pathlib import Path as _Path
    debug_msg = f"[DEBUG] extract_metadata called for {file_path}\n[DEBUG] exiftool_path: {exiftool_path}"
    if not _Path(exiftool_path).exists():
        return {"error": f"ExifTool executable not found at {exiftool_path}", "debug": debug_msg}
    
    try:
        log(f"[DEBUG] Calling ExifTool executable for {file_path}")
        
        # Call exiftool with JSON output (headless on Windows)
        cmd = [exiftool_path, '-j', '-G', '-a', '-s', file_path]
        startupinfo = None
        if sys.platform.startswith('win'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, startupinfo=startupinfo)
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            return {"error": f"ExifTool returned error: {error_msg}", "debug": debug_msg, "type": "exiftool_error"}
        
        # Parse JSON output
        try:
            metadata_list = json.loads(result.stdout)
            if metadata_list and len(metadata_list) > 0:
                metadata = metadata_list[0]  # ExifTool returns a list, take first item
            else:
                metadata = {}
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse ExifTool JSON output: {e}", "debug": debug_msg, "type": "json_parse_error"}
        
        log(f"[DEBUG] ExifTool returned: {len(metadata)} metadata tags")
        if not metadata:
            return {"error": "No metadata returned.", "debug": debug_msg, "type": "no_metadata"}
        return metadata
    except subprocess.TimeoutExpired:
        msg = f"ExifTool timed out for {file_path}. The file may be corrupt or too large."
        log(f"[ERROR] {msg}")
        return {"error": msg, "debug": debug_msg, "type": "timeout"}
    except FileNotFoundError:
        msg = f"ExifTool executable not found at {exiftool_path}. Please check your installation."
        log(f"[ERROR] {msg}")
        return {"error": msg, "debug": debug_msg, "type": "missing_exiftool"}
    except Exception as e:
        msg = f"Unexpected error in extract_metadata for {file_path}: {e}"
        import traceback
        tb = traceback.format_exc()
        log(f"[ERROR] {msg}\n{tb}")
        return {"error": msg, "debug": debug_msg, "type": "unexpected"}

def extract_datetime_with_tags(tags, file_path):
    file_path = str(Path(file_path))
    exiftool_path = get_exiftool_path()
    try:
        # Call exiftool with JSON output (headless on Windows)
        cmd = [exiftool_path, '-j', '-G', '-a', '-s', file_path]
        startupinfo = None
        if sys.platform.startswith('win'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, startupinfo=startupinfo)
        
        if result.returncode != 0:
            log(f"ExifTool error for {file_path}: {result.stderr}")
            return None, None
            
        # Parse JSON output
        try:
            metadata_list = json.loads(result.stdout)
            meta = metadata_list[0] if metadata_list else {}
        except json.JSONDecodeError:
            log(f"Failed to parse ExifTool JSON for {file_path}")
            return None, None
            
        for tag in tags:
            # Try both raw and group-prefixed keys
            if tag in meta:
                log(f"Extracted {tag} for {file_path}: {meta[tag]}")
                return meta[tag], tag
            for k in meta:
                if k.lower().endswith(tag.lower()):
                    log(f"Extracted {k} for {file_path}: {meta[k]}")
                    return meta[k], k
    except subprocess.TimeoutExpired:
        log(f"ExifTool timeout for {file_path}")
    except FileNotFoundError as e:
        log(f"ExifTool executable not found for {file_path}: {e}")
    except PermissionError as e:
        log(f"Permission error accessing {file_path}: {e}")
    except Exception as e:
        log(f"Unexpected ExifTool error for {file_path}: {e}")
        # Log traceback in debug mode
        import os
        if os.environ.get('MEDIA_ORGANIZER_DEBUG'):
            import traceback
            log(f"Traceback: {traceback.format_exc()}")
    log(f"No valid datetime found for {file_path}")
    return None, None

def extract_datetime(file_path, tags=None):
    # Default order if not specified
    if tags is None:
        tags = [
            'DateTimeOriginal',
            'CreateDate',
            'MediaCreateDate'
        ]
    value, _ = extract_datetime_with_tags(tags, file_path)
    return value

def extract_earliest_datetime(file_path, tags=None):
    """
    Returns the earliest valid date string found among the given tags in the file's metadata.
    If no valid date is found, returns None.
    """
    from .utils import parse_exif_date
    file_path = str(Path(file_path))
    exiftool_path = get_exiftool_path()
    try:
        # Call exiftool with JSON output (headless on Windows)
        cmd = [exiftool_path, '-j', '-G', '-a', '-s', file_path]
        startupinfo = None
        if sys.platform.startswith('win'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, startupinfo=startupinfo)
        
        if result.returncode != 0:
            log(f"ExifTool error for {file_path} (earliest): {result.stderr}")
            return None
            
        # Parse JSON output
        try:
            metadata_list = json.loads(result.stdout)
            meta = metadata_list[0] if metadata_list else {}
        except json.JSONDecodeError:
            log(f"Failed to parse ExifTool JSON for {file_path} (earliest)")
            return None
            
        found_dates = []
        for tag in tags or []:
            # Try both raw and group-prefixed keys
            if tag in meta:
                dt = parse_exif_date(meta[tag])
                if dt:
                    found_dates.append((dt, meta[tag], tag))
            for k in meta:
                if k.lower().endswith(tag.lower()):
                    dt = parse_exif_date(meta[k])
                    if dt:
                        found_dates.append((dt, meta[k], k))
        if found_dates:
            found_dates.sort(key=lambda x: x[0])  # sort by datetime
            log(f"[EARLIEST] {file_path}: {found_dates[0][1]} from {found_dates[0][2]}")
            return found_dates[0][1]  # return the date string
    except subprocess.TimeoutExpired:
        log(f"ExifTool timeout for {file_path} (earliest)")
    except FileNotFoundError as e:
        log(f"ExifTool executable not found for {file_path} (earliest): {e}")
    except Exception as e:
        log(f"Unexpected ExifTool error for {file_path} (earliest): {e}")
        # Log traceback in debug mode
        import traceback
        log(f"[DEBUG] {traceback.format_exc()}")
    return None
