import argparse

import os
from media_organizer.app.exiftool_check import get_exiftool_path
os.environ['EXIFTOOL_PATH'] = get_exiftool_path()

from media_organizer.app.scanner import scan_media_files
from media_organizer.app.organizer import organize_files
from media_organizer.app.logger import logger
from media_organizer.app.exiftool_check import check_exiftool
from media_organizer.app.config import SUPPORTED_FORMATS
from media_organizer.app.utils import check_source_dest_overlap

def main():
    parser = argparse.ArgumentParser(description="Media Organizer CLI")
    parser.add_argument('--source', required=True, help='Source folder')
    parser.add_argument('--dest', required=True, help='Destination folder')
    parser.add_argument('--move', action='store_true', help='Move files instead of copying')
    parser.add_argument('--dry-run', action='store_true', help='Preview actions without making changes')
    parser.add_argument('--tags', nargs='+', default=['DateTimeOriginal', 'CreateDate', 'MediaCreateDate'], help='Metadata tag order')
    args = parser.parse_args()

    if not check_exiftool():
        logger.error("ExifTool is not installed or not found in PATH.")
        exit(1)

    try:
        check_source_dest_overlap(args.source, args.dest)
    except ValueError as e:
        logger.error(str(e))
        exit(2)

    files = scan_media_files(args.source)
    logger.info(f"Found {len(files)} media files.")
    organize_files(
        files,
        args.dest,
        operation='move' if args.move else 'copy',
        dry_run=args.dry_run,
        tag_order=args.tags
    )
    logger.info("Done.")

if __name__ == "__main__":
    main()
