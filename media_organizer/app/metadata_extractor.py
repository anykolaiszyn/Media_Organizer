
# --- Ensure ExifTool subprocesses are headless on Windows ---
import sys
import subprocess
if sys.platform == 'win32':
    _orig_popen = subprocess.Popen
    def _popen_no_window(*args, **kwargs):
        kwargs.setdefault('creationflags', 0)
        kwargs['creationflags'] |= getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
        return _orig_popen(*args, **kwargs)
    subprocess.Popen = _popen_no_window


from pathlib import Path
from .logger import log
import exiftool_wrapper as exiftool
from media_organizer.app.exiftool_check import get_exiftool_path

def extract_metadata(file_path):
    """
    Extract all metadata from a file using the exiftool Python package. Returns a dict of tag: value.
    """
    file_path = str(Path(file_path))
    exiftool_path = get_exiftool_path()
    from pathlib import Path as _Path
    # UI debug: always show this message in the metadata viewer
    debug_msg = f"[DEBUG] extract_metadata called for {file_path}\n[DEBUG] exiftool_path: {exiftool_path}"
    if not _Path(exiftool_path).exists():
        return {"error": f"ExifTool executable not found at {exiftool_path}", "debug": debug_msg}
    try:
        log(f"[DEBUG] Calling ExifToolWrapper for {file_path}")
        et = exiftool.ExifToolWrapper()
        result = et.process_json(file_path)
        log(f"[DEBUG] process_json returned: {result}")
        if not result:
            return {"error": "No metadata returned.", "debug": debug_msg}
        return result
    except Exception as e:
        log(f"ExifTool error for {file_path}: {e}")
        print(f"ExifTool error for {file_path}: {e}")
        return {"error": str(e), "debug": debug_msg}

def extract_datetime_with_tags(tags, file_path):
    file_path = str(Path(file_path))
    exiftool_path = get_exiftool_path()
    try:
        et = exiftool.ExifToolWrapper()
        meta = et.process_json(file_path)
        for tag in tags:
            # Try both raw and group-prefixed keys
            if tag in meta:
                log(f"Extracted {tag} for {file_path}: {meta[tag]}")
                return meta[tag], tag
            for k in meta:
                if k.lower().endswith(tag.lower()):
                    log(f"Extracted {k} for {file_path}: {meta[k]}")
                    return meta[k], k
    except Exception as e:
        log(f"ExifTool error for {file_path}: {e}")
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
