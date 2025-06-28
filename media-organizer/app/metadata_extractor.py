import subprocess
import sys
from pathlib import Path
from .logger import log
from .exiftool_check import get_exiftool_path

def extract_metadata(file_path):
    """
    Extract all metadata from a file using ExifTool. Returns a dict of tag: value.
    """
    file_path = str(Path(file_path))
    try:
        exiftool = get_exiftool_path()
        result = subprocess.run([
            exiftool, "-j", file_path
        ], capture_output=True, text=True, check=True)
        import json
        data = json.loads(result.stdout)
        if data and isinstance(data, list):
            return data[0]
        return {}
    except Exception as e:
        log(f"ExifTool error for {file_path}: {e}")
        return {}
import subprocess
from pathlib import Path
from .logger import log

def extract_datetime_with_tags(tags, file_path):
    file_path = str(Path(file_path))
    exiftool = get_exiftool_path()
    for tag in tags:
        try:
            result = subprocess.run(
                [exiftool, f"-{tag}", "-s3", file_path],
                capture_output=True, text=True, check=True
            )
            value = result.stdout.strip()
            if value:
                log(f"Extracted {tag} for {file_path}: {value}")
                return value, tag
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
