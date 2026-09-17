import filecmp
from pathlib import Path
import csv

def write_csv_safe(file_path, header, rows):
    """Write rows to file_path as CSV.

    Uses the csv module so embedded quotes, commas, and newlines are escaped
    correctly -- ad-hoc f-string quoting breaks on any of those. Also guards
    against CSV/spreadsheet formula injection: a cell beginning with =, +,
    -, or @ is prefixed with a single quote, which Excel and LibreOffice
    both treat as "this is literal text," not a formula to evaluate.
    """
    def sanitize(value):
        text = '' if value is None else str(value)
        if text and text[0] in ('=', '+', '-', '@'):
            return "'" + text
        return text

    with open(file_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow([sanitize(v) for v in row])

def ensure_dir(path):
    """Ensure a directory exists (like mkdir -p)."""
    Path(path).mkdir(parents=True, exist_ok=True)

def files_identical(a, b):
    """True when two files hold byte-identical content.

    Compares sizes before content and stops at the first differing byte, so it
    is cheaper than hashing when the answer is 'no'.
    """
    return filecmp.cmp(str(a), str(b), shallow=False)


def check_source_dest_overlap(source, dest):
    """Raise ValueError if the destination sits inside the source.

    The source is scanned recursively, so a destination nested inside it would
    be re-scanned on every later run, re-processing already-filed photos. The
    reverse nesting (a staging folder inside the library) is harmless.
    """
    src = Path(source).resolve()
    dst = Path(dest).resolve()
    if src == dst:
        raise ValueError(f"Source and destination are the same folder: {src}")
    if dst.is_relative_to(src):
        raise ValueError(
            f"Destination {dst} is inside source {src}. Every later run would "
            f"re-scan its own output. Choose a destination outside the source."
        )


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
