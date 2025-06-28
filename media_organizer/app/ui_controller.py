from .scanner import scan_media_files
from .organizer import organize_files, get_organize_preview
from .logger import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

class MediaOrganizerController:
    def __init__(self, log_callback=None, progress_callback=None):
        self.log_callback = log_callback or (lambda msg: None)
        self.progress_callback = progress_callback or (lambda pct: None)
        self.cancel_flag = False
        self._lock = threading.Lock()

    def run_organizer(self, source, dest, operation, dry_run, tag_order=None, max_workers=4, eta_callback=None, formats=None, duplicate_mode='overwrite'):
        self.cancel_flag = False
        self._log(f"Scanning {source} for media files...")
        files = scan_media_files(source, formats=formats)
        self._log(f"Found {len(files)} media files.")
        total = len(files)
        completed = 0
        start_time = time.time()
        def organize_one(file_path):
            if self.cancel_flag:
                return 'cancelled', file_path
            self._log(f"Processing: {file_path}")
            organize_files([file_path], dest, operation, dry_run=dry_run, tag_order=tag_order, duplicate_mode=duplicate_mode)
            return 'done', file_path
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(organize_one, f): f for f in files}
            for future in as_completed(futures):
                with self._lock:
                    completed += 1
                    elapsed = time.time() - start_time
                    avg_time = elapsed / completed if completed else 0
                    remaining = total - completed
                    eta = int(avg_time * remaining)
                    if eta_callback:
                        eta_callback(eta)
                    self._progress(100 * completed / total if total else 100)
                if self.cancel_flag:
                    self._log("Operation cancelled by user.")
                    break
        if eta_callback:
            eta_callback(0)
        self._log("Done.")
        self._progress(100)

    def get_preview_list(self, source, dest, tag_order=None, formats=None, progress_callback=None, cancel_flag=None):
        """
        Returns (preview_list, skipped_list):
        preview_list: list of (source, dest) tuples
        skipped_list: list of (source, reason) tuples
        progress_callback: function(percent) to update progress bar
        cancel_flag: threading.Event or similar, set to cancel
        """
        files = scan_media_files(source, formats=formats)
        total = len(files)
        preview = []
        skipped = []
        for idx, file in enumerate(files):
            if cancel_flag and cancel_flag.is_set():
                self._log("Preview cancelled by user.")
                break
            # get_organize_preview expects a list, returns (preview, skipped)
            p, s = get_organize_preview([file], dest, tag_order=tag_order)
            preview.extend(p)
            skipped.extend(s)
            if progress_callback:
                progress_callback(100 * (idx + 1) / total if total else 100)
        return preview, skipped

    def cancel(self):
        self.cancel_flag = True

    def _log(self, message):
        logger.info(message)
        self.log_callback(message)

    def _progress(self, percent):
        self.progress_callback(percent)
