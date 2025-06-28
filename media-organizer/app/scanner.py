from pathlib import Path
from .config import SUPPORTED_FORMATS
from .utils import is_supported_file

def scan_media_files(source_folder, formats=None):
    if formats is None:
        formats = SUPPORTED_FORMATS
    source = Path(source_folder)
    return [str(p) for p in source.rglob('*') if is_supported_file(p, formats)]
