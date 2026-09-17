import threading
import time
import atexit
import os
from collections import Counter
from .scanner import scan_media_files
from .organizer import organize_files
from .metadata_extractor import extract_metadata_batch
from .logger import logger
from .batch_results_db import BatchResultsDB
from .memory_monitor import MemoryMonitor, check_dataset_size_and_warn
from .utils import check_source_dest_overlap
from .batch_events import (
    Scanned, FileStarted, FileDone, LogLine, Finished,
    ScanProgress, ScanFound, ScanFinished, ExtractionProgress,
)
from concurrent.futures import ThreadPoolExecutor, as_completed

class MediaOrganizerController:
    def __init__(self):
        self.cancel_flag = False
        self._lock = threading.Lock()
        self.batch_db = None
        atexit.register(BatchResultsDB.cleanup_old_temp_dbs)

    def scan_media_files_async(self, source, formats=None, emit=None):
        """Scan in a background thread, publishing events. Returns immediately."""
        emit = emit or (lambda event: None)
        from .scanner import scan_media_files_iter
        self.cancel_flag = False

        def worker():
            found = 0
            for path in scan_media_files_iter(
                source,
                formats=formats,
                progress_callback=lambda pct: emit(ScanProgress(pct)),
                cancel_flag=lambda: self.cancel_flag,
            ):
                found += 1
                emit(ScanFound(path, found))
            emit(ScanFinished(found))

        threading.Thread(target=worker, daemon=True).start()

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

        try:
            chunk_size = max(1, int(os.environ.get('MEDIA_ORGANIZER_CHUNK_SIZE', 200)))
        except (ValueError, TypeError):
            chunk_size = 200
        chunks = [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]

        counts = Counter()
        completed = 0
        cancelled_logged = False
        start_time = time.time()

        def organize_one(file_path, metadata_by_path):
            if self.cancel_flag:
                if self.batch_db is not None:
                    with self._lock:
                        self.batch_db.insert_result(
                            file_path, operation, 'cancelled', {}, error='Batch cancelled')
                return 'cancelled', file_path, None, None

            emit(FileStarted(file_path))
            metadata = metadata_by_path.get(file_path, {})
            error = None
            outcome = None
            if 'error' in metadata:
                status = 'error'
                error = metadata['error']
                emit(LogLine(f"ERROR: {file_path}: {error}"))
            else:
                try:
                    results = organize_files(
                        [file_path], dest, metadata_by_path, operation, dry_run=dry_run,
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
                    self.batch_db.insert_result(file_path, operation, status, {}, error=error)
            return status, file_path, outcome, error

        files_extracted = 0
        for chunk_index, chunk in enumerate(chunks):
            if self.cancel_flag:
                break
            # Not forwarding `emit` into extract_metadata_batch here: called
            # once per outer chunk, its own internal view is always "chunk 1
            # of 1" -- meaningless for a UI showing progress across the whole
            # batch. Compute that from this loop's own position instead.
            metadata_by_path = extract_metadata_batch(chunk, chunk_size=chunk_size)
            files_extracted += len(chunk)
            emit(ExtractionProgress(
                chunks_done=chunk_index + 1, chunks_total=len(chunks),
                files_done=files_extracted, files_total=total,
            ))
            if self.cancel_flag:
                break
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(organize_one, f, metadata_by_path) for f in chunk]
                for future in as_completed(futures):
                    status, path, outcome, error = future.result()
                    with self._lock:
                        completed += 1
                        counts[status] += 1
                        elapsed = time.time() - start_time
                        eta = int((elapsed / completed) * (total - completed)) if completed else 0
                    emit(FileDone(path, outcome, error, completed, total, eta))
                    # Do NOT break here: ThreadPoolExecutor.__exit__ already
                    # blocks (shutdown(wait=True)) until every submitted
                    # future in THIS chunk finishes running, cancelled or
                    # not, so breaking early saves no wall-clock time -- it
                    # only stops us from counting results we're going to
                    # wait for anyway. Draining keeps counts[] accurate.
                    if self.cancel_flag and not cancelled_logged:
                        cancelled_logged = True
                        emit(LogLine("Operation cancelled by user."))

        if total >= MemoryMonitor.LARGE_DATASET_WARNING:
            MemoryMonitor.log_memory_stats(f"After processing {total:,} files")
            pressure = MemoryMonitor.check_memory_pressure()
            if pressure:
                emit(LogLine(f"[MEMORY WARNING] {pressure}"))

        emit(Finished(dict(counts), self.cancel_flag, time.time() - start_time))

    def cancel(self):
        self.cancel_flag = True
        # Attempt to cancel ExifTool if running
        try:
            from .metadata_extractor import cancel_exiftool
            cancel_exiftool()
        except Exception as e:
            logger.info(f"[CANCEL] Error attempting to cancel ExifTool: {e}")
