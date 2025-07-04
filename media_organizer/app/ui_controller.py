import threading
import time
import atexit
from .scanner import scan_media_files
from .organizer import organize_files, get_organize_preview
from .logger import logger
from .batch_results_db import BatchResultsDB
from .memory_monitor import MemoryMonitor, check_dataset_size_and_warn
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

    def organize_batch(self, source, dest, operation, dry_run, tag_order, duplicate_mode, use_earliest, formats=None, eta_callback=None, max_workers=4, memory_warning_callback=None):
        """Organize files in batch mode with concurrency and progress reporting."""
        import time
        self.cancel_flag = False
        if self.batch_db:
            self.batch_db.clear()
        else:
            self.batch_db = BatchResultsDB()
        
        # Log initial memory state
        MemoryMonitor.log_memory_stats("Before scanning")
        
        self._log(f"Scanning {source} for media files...")
        files = scan_media_files(source, formats=formats)
        file_count = len(files)
        self._log(f"Found {file_count} media files.")
        
        # Check for large dataset and memory warnings
        if not check_dataset_size_and_warn(file_count, memory_warning_callback):
            self._log("Operation cancelled due to dataset size concerns.")
            return
        
        # Log memory after file scanning
        if file_count >= MemoryMonitor.LARGE_DATASET_WARNING:
            MemoryMonitor.log_memory_stats(f"After scanning {file_count:,} files")
        
        total = file_count
        completed = 0
        start_time = time.time()
        import os
        # SAFETY: Set default max_workers to 3
        try:
            max_workers = int(os.environ.get('MEDIA_ORGANIZER_MAX_WORKERS', 3))
        except (ValueError, TypeError) as e:
            self._log(f"Warning: Invalid MEDIA_ORGANIZER_MAX_WORKERS value, using default (3): {e}")
            max_workers = 3
        if max_workers < 1:
            max_workers = 1
        self._log(f"Using up to {max_workers} concurrent workers for batch processing.")
        def organize_one(file_path):
            if self.cancel_flag:
                if self.batch_db is not None:
                    self.batch_db.insert_result(file_path, operation, 'cancelled', {}, error='Batch cancelled')
                return 'cancelled', file_path
            self._log(f"Processing: {file_path}")
            from .metadata_extractor import extract_metadata
            metadata = extract_metadata(file_path)
            error = None
            status = 'done'
            try:
                organize_files([file_path], dest, operation, dry_run=dry_run, tag_order=tag_order, duplicate_mode=duplicate_mode, use_earliest=use_earliest)
            except FileNotFoundError as e:
                error = f"File not found: {e}"
                status = 'error'
                self._log(f"ERROR: File not found - {file_path}: {e}")
            except PermissionError as e:
                error = f"Permission denied: {e}"
                status = 'error'
                self._log(f"ERROR: Permission denied - {file_path}: {e}")
            except OSError as e:
                error = f"File system error: {e}"
                status = 'error'
                self._log(f"ERROR: File system error - {file_path}: {e}")
            except ValueError as e:
                error = f"Invalid file or metadata: {e}"
                status = 'error'
                self._log(f"ERROR: Invalid data - {file_path}: {e}")
            except Exception as e:
                error = f"Unexpected error: {e}"
                status = 'error'
                self._log(f"ERROR: Unexpected error - {file_path}: {e}")
                # Re-raise for debugging in development, but log for production
                import os
                if os.environ.get('MEDIA_ORGANIZER_DEBUG'):
                    raise
            if self.batch_db is not None:
                self.batch_db.insert_result(file_path, operation, status, metadata, error=error)
            return status, file_path
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for f in files:
                while len(futures) >= max_workers:
                    done, _ = next(iter(futures.items()))
                    try:
                        done.result(timeout=0.1)
                    except Exception:
                        pass
                    del futures[done]
                futures[executor.submit(organize_one, f)] = f
                # SAFETY: Throttle ExifTool launches to avoid system stress
                time.sleep(0.05)
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
        
        # Log final memory state for large datasets
        if file_count >= MemoryMonitor.LARGE_DATASET_WARNING:
            MemoryMonitor.log_memory_stats(f"After processing {file_count:,} files")
            
            # Check for memory pressure after processing
            memory_warning = MemoryMonitor.check_memory_pressure()
            if memory_warning:
                self._log(f"[MEMORY WARNING] {memory_warning}")
        
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
