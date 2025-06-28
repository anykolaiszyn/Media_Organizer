import shutil
from .logger import logger

def check_exiftool():
    """Check if exiftool is available in PATH."""
    if shutil.which('exiftool') is None:
        logger.error("ExifTool is not installed or not found in PATH. Please install ExifTool to continue.")
        return False
    return True
