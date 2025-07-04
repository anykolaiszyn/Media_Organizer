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
    
    if not date_str or not isinstance(date_str, str):
        return None
        
    try:
        # Handle the main ExifTool date format
        return datetime.strptime(date_str.split()[0], '%Y:%m:%d')
    except ValueError as e:
        # Handle malformed date strings
        from .logger import log
        log(f"Invalid date format '{date_str}': {e}")
        return None
    except IndexError as e:
        # Handle empty or malformed input
        from .logger import log
        log(f"Cannot parse date string '{date_str}': {e}")
        return None
    except Exception as e:
        # Catch any other unexpected parsing errors
        from .logger import log
        log(f"Unexpected error parsing date '{date_str}': {e}")
        return None
