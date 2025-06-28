from pathlib import Path
import shutil
from .logger import logger
from .metadata_extractor import extract_datetime
from .utils import ensure_dir, parse_exif_date

def organize_files(files, dest_folder, operation='copy', dry_run=False, tag_order=None, duplicate_mode='overwrite'):
    dest_folder = Path(dest_folder)
    for file_path in files:
        date_str = extract_datetime(file_path, tags=tag_order)
        if not date_str:
            # Move/copy to no_metadata folder
            no_meta_dir = dest_folder / "no_metadata"
            ensure_dir(no_meta_dir)
            dest_path = no_meta_dir / Path(file_path).name
            dest_path = _get_nonconflicting_path(dest_path, duplicate_mode)
            try:
                if dry_run:
                    logger.info(f"[DRY RUN] Would {operation} {file_path} -> {dest_path} (no metadata)")
                    continue
                if operation == 'move':
                    shutil.move(str(file_path), str(dest_path))
                    logger.info(f"Moved {file_path} -> {dest_path} (no metadata)")
                else:
                    shutil.copy2(str(file_path), str(dest_path))
                    logger.info(f"Copied {file_path} -> {dest_path} (no metadata)")
            except Exception as e:
                logger.error(f"Failed to {operation} {file_path} to no_metadata: {e}")
            continue
        dt = parse_exif_date(date_str)
        if not dt:
            logger.error(f"Failed to parse date for {file_path}: {date_str}")
            continue
        year = str(dt.year)
        month = f"{dt.month:02d}"
        dest_dir = dest_folder / year / month
        ensure_dir(dest_dir)
        dest_path = dest_dir / Path(file_path).name
        dest_path = _get_nonconflicting_path(dest_path, duplicate_mode)
        try:
            if dry_run:
                logger.info(f"[DRY RUN] Would {operation} {file_path} -> {dest_path}")
                continue
            if operation == 'move':
                shutil.move(str(file_path), str(dest_path))
                logger.info(f"Moved {file_path} -> {dest_path}")
            else:
                shutil.copy2(str(file_path), str(dest_path))
                logger.info(f"Copied {file_path} -> {dest_path}")
        except Exception as e:
            logger.error(f"Failed to {operation} {file_path}: {e}")

def _get_nonconflicting_path(dest_path, duplicate_mode):
    """If duplicate_mode is 'preserve', append _1, _2, ... to filename if needed."""
    if duplicate_mode != 'preserve':
        return dest_path
    orig_path = dest_path
    stem = dest_path.stem
    suffix = dest_path.suffix
    parent = dest_path.parent
    i = 1
    while dest_path.exists():
        dest_path = parent / f"{stem}_{i}{suffix}"
        i += 1
    return dest_path

def get_organize_preview(files, dest_folder, tag_order=None):
    """
    Returns a list of (source, destination) tuples for files that would be organized.
    Skips files with missing/invalid dates, just like organize_files.
    """
    dest_folder = Path(dest_folder)
    preview = []
    skipped = []
    for file_path in files:
        date_str = extract_datetime(file_path, tags=tag_order)
        if not date_str:
            # Preview for no_metadata
            no_meta_dir = dest_folder / "no_metadata"
            dest_path = no_meta_dir / Path(file_path).name
            preview.append((str(file_path), str(dest_path) + " (no metadata)"))
            continue
        dt = parse_exif_date(date_str)
        if not dt:
            skipped.append((file_path, f'Failed to parse date: {date_str}'))
            continue
        year = str(dt.year)
        month = f"{dt.month:02d}"
        dest_dir = dest_folder / year / month
        dest_path = dest_dir / Path(file_path).name
        preview.append((str(file_path), str(dest_path)))
    return preview, skipped
