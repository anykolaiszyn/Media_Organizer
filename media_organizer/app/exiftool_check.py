
import shutil
import sys
from pathlib import Path
from .logger import logger

def get_exiftool_path():
    """Return the path to the bundled exiftool.exe in ExifTool folder (works for both EXE and dev)."""
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle: exiftool.exe is in ExifTool subfolder next to the EXE
        base_path = Path(sys.executable).parent / 'ExifTool'
        exiftool_path = base_path / 'exiftool.exe'
    else:
        # Dev mode: look in ExifTool subfolder
        base_path = Path(__file__).parent.parent / 'ExifTool'
        exiftool_path = base_path / 'exiftool.exe'
    return str(exiftool_path)

def check_exiftool():
    """Check if exiftool is available (bundled or in PATH)."""
    exiftool_path = get_exiftool_path()
    if Path(exiftool_path).exists():
        return True
    if shutil.which('exiftool') is not None:
        return True
    logger.error(f"ExifTool is not installed or not found at {exiftool_path} or in PATH. Please install or bundle ExifTool to continue.")
    return False
