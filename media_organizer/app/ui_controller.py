import threading
import time
import atexit
import os
from collections import Counter
from .scanner import scan_media_files
from .organizer import organize_files, get_organize_preview
from .logger import logger
from .batch_results_db import BatchResultsDB
from .memory_monitor import MemoryMonitor, check_dataset_size_and_warn
from .utils import check_source_dest_overlap
from .batch_events import (
    Scanned, FileStarted, FileDone, LogLine, Finished,
)
from concurrent.futures import ThreadPoolExecutor, as_completed

class MediaOrganizerController:
    def __init__(self, log_callback=None, progress_callback=None):
        self.log_callback = log_callback or (lambda msg: None)
        self.progress_callback = progress_callback or (lambda pct: None)
        self.cancel_flag = False
        self._lock = threading.Lock()
        self.batch_db = None
        # Clean up old temp DBs on app exit
        atexit.register(BatchResultsDB.cleanup_old_temp_dbs)

    def scan_media_files_async(self, source, formats=None, progress_callback=None, found_callback=None, done_callback=None):
        """Scan files in a background thread, reporting progress and found files to the UI."""
        from .scanner import scan_media_files_iter
        self.cancel_flag = False
        def cancel():
            return self.cancel_flag
        def worker():
            for f in scan_media_files_iter(source, formats=formats, progress_callback=progress_callback, cancel_flag=cancel):
                if found_callback:
                    found_callback(f)
            if done_callback:
                done_callback()
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    @staticmethod
    def _resolve_max_workers(requested):
        if requested is None:
            try:
                requested = int(os.environ.get('MEDIA_ORGANIZER_MAX_WORKERS', 3))
            except (ValueError, TypeError):
                requested = 3
        return max(1, requested)

    def organize_batch(self, source, dest, operation, dry_run, tag_order, use_earliest,
                       formats=None, max_workers=None, emit=None,
                       memory_warning_callback=None):
        """Organize files concurrently, publishing progress as events.

        `emit` is called with batch_events objects from both this thread and
        the worker threads, so it must be thread-safe. queue.Queue.put is.
        """
        emit = emit or (lambda event: None)
        check_source_dest_overlap(source, dest)
        self.cancel_flag = False
        if self.batch_db:
            self.batch_db.clear()
        else:
            self.batch_db = BatchResultsDB()

        MemoryMonitor.log_memory_stats("Before scanning")
        files = scan_media_files(source, formats=formats)
        total = len(files)
        emit(Scanned(total))

        if not check_dataset_size_and_warn(total, memory_warning_callback):
            emit(LogLine("Operation cancelled due to dataset size concerns."))
            emit(Finished({}, True, 0.0))
            return

        if total >= MemoryMonitor.LARGE_DATASET_WARNING:
            MemoryMonitor.log_memory_stats(f"After scanning {total:,} files")

        max_workers = self._resolve_max_workers(max_workers)
        emit(LogLine(f"Using up to {max_workers} concurrent workers for batch processing."))

        counts = Counter()
        completed = 0
        start_time = time.time()

        def organize_one(file_path):
            if self.cancel_flag:
                if self.batch_db is not None:
                    with self._lock:
                        self.batch_db.insert_result(
                            file_path, operation, 'cancelled', {}, error='Batch cancelled')
                return 'cancelled', file_path, None, None

            emit(FileStarted(file_path))
            from .metadata_extractor import extract_metadata
            metadata = extract_metadata(file_path)
            error = None
            outcome = None
            try:
                results = organize_files(
                    [file_path], dest, operation, dry_run=dry_run,
                    tag_order=tag_order, use_earliest=use_earliest)
                if results:
                    outcome = results[0][1].value
                    status = outcome
                else:
                    status = 'error'
                    error = 'File was not placed'
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                status = 'error'
                emit(LogLine(f"ERROR: {file_path}: {error}"))
                if os.environ.get('MEDIA_ORGANIZER_DEBUG'):
                    raise

            if self.batch_db is not None:
                # BatchResultsDB shares one sqlite3 connection across worker
                # threads; concurrent access without this lock raises
                # sqlite3.InterfaceError ("bad parameter or other API misuse").
                with self._lock:
                    self.batch_db.insert_result(
                        file_path, operation, status, metadata, error=error)
            return status, file_path, outcome, error

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(organize_one, f) for f in files]
            for future in as_completed(futures):
                status, path, outcome, error = future.result()
                with self._lock:
                    completed += 1
                    counts[status] += 1
                    elapsed = time.time() - start_time
                    eta = int((elapsed / completed) * (total - completed)) if completed else 0
                emit(FileDone(path, outcome, error, completed, total, eta))
                if self.cancel_flag:
                    emit(LogLine("Operation cancelled by user."))
                    break

        if total >= MemoryMonitor.LARGE_DATASET_WARNING:
            MemoryMonitor.log_memory_stats(f"After processing {total:,} files")
            pressure = MemoryMonitor.check_memory_pressure()
            if pressure:
                emit(LogLine(f"[MEMORY WARNING] {pressure}"))

        emit(Finished(dict(counts), self.cancel_flag, time.time() - start_time))

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
        # Attempt to cancel ExifTool if running
        try:
            from .metadata_extractor import cancel_exiftool
            cancel_exiftool()
        except Exception as e:
            self._log(f"[CANCEL] Error attempting to cancel ExifTool: {e}")

    def _log(self, message):
        logger.info(message)
        self.log_callback(message)

    def _progress(self, percent):
        self.progress_callback(percent)
