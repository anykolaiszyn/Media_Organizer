from pathlib import Path

def ensure_dir(path):
    """Ensure a directory exists (like mkdir -p)."""
    Path(path).mkdir(parents=True, exist_ok=True)

def is_supported_file(path, supported_formats):
    """Check if file has a supported extension."""
    return Path(path).suffix.lower() in supported_formats

def parse_exif_date(date_str):
    """Parse ExifTool date string (YYYY:MM:DD or YYYY:MM:DD HH:MM:SS)."""
    from datetime import datetime
    try:
        return datetime.strptime(date_str.split()[0], '%Y:%m:%d')
    except Exception:
        return None
