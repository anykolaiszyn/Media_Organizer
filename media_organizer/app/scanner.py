from pathlib import Path
from .config import SUPPORTED_FORMATS
from .utils import is_supported_file


def scan_media_files(source_folder, formats=None):
    """Synchronous: returns all matching files as a list (legacy)."""
    if formats is None:
        formats = SUPPORTED_FORMATS
    source = Path(source_folder)
    return [str(p) for p in source.rglob('*') if is_supported_file(p, formats)]

def scan_media_files_iter(source_folder, formats=None, progress_callback=None, cancel_flag=None):
    """Async/generator: yields files as they are found, supports progress and cancellation."""
    if formats is None:
        formats = SUPPORTED_FORMATS
    source = Path(source_folder)
    all_files = list(source.rglob('*'))
    total = len(all_files)
    for idx, p in enumerate(all_files):
        if cancel_flag and cancel_flag():
            break
        if is_supported_file(p, formats):
            yield str(p)
        if progress_callback:
            progress_callback(100 * (idx + 1) / total if total else 100)
