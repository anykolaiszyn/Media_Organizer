import os
from media_organizer.app.exiftool_check import get_exiftool_path
# Set EXIFTOOL_PATH to the folder, not the exe itself
os.environ['EXIFTOOL_PATH'] = os.path.dirname(get_exiftool_path())

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import tkinter.ttk as ttk
import threading
from media_organizer.app.ui_controller import MediaOrganizerController
from media_organizer.app.exiftool_check import check_exiftool
from media_organizer.app.config import IMAGE_FORMATS, VIDEO_FORMATS
from media_organizer.app.logger import logger
import json
from typing import Optional

APP_VERSION = "1.0.0"

# --- UI Setup ---
class MediaOrganizerApp:
    def cleanup_on_exit(self):
        # Attempt to cancel any running batch and ExifTool process
        try:
            self.controller.cancel()
        except Exception:
            pass
        # Optionally, wait a short time for threads/processes to exit
        self.root.after(200, self.root.destroy)
    def show_dry_run_dialog(self):
        """Show a paginated dialog of dry run/preview results (simulated actions)."""
        import tkinter as tk
        from tkinter import Toplevel, Label, Button, scrolledtext, filedialog, messagebox
        from media_organizer.app.batch_results_db import BatchResultsDB
        win = Toplevel(self.root)
        win.title("Dry Run Preview (Simulated Actions)")
        win.geometry("900x400")
        page_size = 100
        page_var = tk.IntVar(value=0)
        results = []
        def load_page():
            st.config(state='normal')
            st.delete('1.0', 'end')
            offset = page_var.get() * page_size
            results.clear()
            db = self.controller.batch_db
            if db is not None:
                rows = db.fetch_results(limit=page_size, offset=offset)
                for row in rows:
                    filename, action, status, metadata, error = row
                    results.append(row)
                    line = f"{filename} | {action} | {status}"
                    if error:
                        line += f" | ERROR: {error}"
                    st.insert('end', line + '\n')
            st.config(state='disabled')
            page_label.config(text=f"Page {page_var.get()+1}")

        st = scrolledtext.ScrolledText(win, width=110, height=18)
        st.pack(padx=10, pady=5)

        nav_frame = tk.Frame(win)
        nav_frame.pack(pady=2)
        prev_btn = Button(nav_frame, text="Previous", command=lambda: (page_var.set(max(0, page_var.get()-1)), load_page()))
        next_btn = Button(nav_frame, text="Next", command=lambda: (page_var.set(page_var.get()+1), load_page()))
        page_label = Label(nav_frame, text="Page 1")
        prev_btn.pack(side='left', padx=2)
        page_label.pack(side='left', padx=2)
        next_btn.pack(side='left', padx=2)

        def export_preview():
            file_path = filedialog.asksaveasfilename(
                title="Export Dry Run Results",
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv"), ("Text Files", "*.txt"), ("All Files", "*.*")]
            )
            if not file_path:
                return
            try:
                db = self.controller.batch_db
                all_rows = []
                offset = 0
                if db is not None:
                    while True:
                        rows = db.fetch_results(limit=page_size, offset=offset)
                        if not rows:
                            break
                        all_rows.extend(rows)
                        offset += page_size
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('filename,action,status,error\n')
                    for row in all_rows:
                        filename, action, status, metadata, error = row
                        f.write(f'"{filename}","{action}","{status}","{error or ""}"\n')
                messagebox.showinfo("Export Complete", f"Dry run results exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Could not export dry run results:\n{e}")

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=5)
        Button(btn_frame, text="OK", command=win.destroy).pack(side='left', padx=5)
        Button(btn_frame, text="Export Results", command=export_preview).pack(side='left', padx=5)

        load_page()

    def scan_files_dialog(self):
        import tkinter as tk
        from tkinter import Toplevel, Label, Button, scrolledtext, messagebox
        win = Toplevel(self.root)
        win.title("Scanning Files")
        win.geometry("500x300")
        progress_var = tk.DoubleVar(value=0)
        progress = ttk.Progressbar(win, variable=progress_var, maximum=100)
        progress.pack(fill='x', padx=10, pady=10)
        found_label = Label(win, text="Files found: 0")
        found_label.pack(padx=10, anchor='w')
        st = scrolledtext.ScrolledText(win, width=60, height=10)
        st.pack(padx=10, pady=5, fill='both', expand=True)
        cancel_btn = Button(win, text="Cancel", command=win.destroy)
        cancel_btn.pack(pady=5)
        found_files = []
        cancelled = [False]
        def on_progress(pct):
            progress_var.set(pct)
        def on_found(f):
            found_files.append(f)
            found_label.config(text=f"Files found: {len(found_files)}")
            if len(found_files) <= 100:
                st.insert('end', f + '\n')
            if len(found_files) == 100:
                st.insert('end', '... (showing first 100)\n')
        def on_done():
            progress_var.set(100)
            cancel_btn.config(text="Close")
        def cancel():
            cancelled[0] = True
            win.destroy()
        cancel_btn.config(command=cancel)
        self.controller.scan_media_files_async(
            self.source_var.get(),
            formats=None,
            progress_callback=on_progress,
            found_callback=on_found,
            done_callback=on_done
        )
        win.transient(self.root)
        win.grab_set()
        win.wait_window()
    def __init__(self, root):
        self.root = root
        self.log_callback = self._log_callback
        self.progress_callback = self._progress_callback
        self.controller = MediaOrganizerController(self.log_callback, self.progress_callback)
        root.title("Media Organizer")
        # Ensure cleanup on window close
        root.protocol("WM_DELETE_WINDOW", self.cleanup_on_exit)

        # Add menu bar with Help/About
        menubar = tk.Menu(root)
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="About / Help...", command=self.show_about_dialog)
        menubar.add_cascade(label="Help", menu=helpmenu)
        root.config(menu=menubar)

        # Checkbox: Use earliest date from available tags
        self.use_earliest_date = tk.BooleanVar(value=False)

        self.config_path = os.path.join(os.path.expanduser('~'), '.media_organizer_config.json')
        self.source_var = tk.StringVar()
        self.dest_var = tk.StringVar()
        self.op_var = tk.StringVar(value='copy')
        self.dry_run_var = tk.BooleanVar(value=False)
        # Metadata date tags (expanded list)
        self.date_tag_options = [
            "DateTimeOriginal",
            "CreateDate",
            "MediaCreateDate",
            "SubSecDateTimeOriginal",
            "TrackCreateDate",
            "QuickTime:CreationDate",
            "ModifyDate",
            "MetadataDate",
            "FileCreateDate",
            "FileModifyDate",
            "DigitalCreationDate",
            "DateCreated",
            "OriginalReleaseTime",
            "ContentCreateDate",
            "CreationDate"
        ]
        # Recommended default order for CR2/JPG: DateTimeOriginal, CreateDate, MediaCreateDate, SubSecDateTimeOriginal, FileCreateDate
        default_tag_order = [
            "DateTimeOriginal",
            "CreateDate",
            "MediaCreateDate",
            "SubSecDateTimeOriginal",
            "FileCreateDate"
        ]
        self.tag_vars = [tk.StringVar(value=tag) for tag in default_tag_order]
        self.is_processing = False

        self.load_last_folders()

        # --- Tabbed UI ---
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=True, fill="both")

        # --- Organizer Tab ---

        org_frame = tk.Frame(self.notebook, padx=10, pady=10)
        self.org_frame = org_frame
        self.notebook.add(self.org_frame, text="Organizer")


        for i in range(3):
            self.org_frame.grid_columnconfigure(i, weight=1)
        for i in range(10):
            self.org_frame.grid_rowconfigure(i, weight=0)
        self.org_frame.grid_rowconfigure(8, weight=1)


        tk.Label(self.org_frame, text="Source Folder:").grid(row=0, column=0, sticky='e')
        tk.Entry(self.org_frame, textvariable=self.source_var, width=40).grid(row=0, column=1, sticky='ew')
        tk.Button(self.org_frame, text="Browse", command=self.browse_source).grid(row=0, column=2, sticky='ew')

        tk.Label(self.org_frame, text="Destination Folder:").grid(row=1, column=0, sticky='e')
        tk.Entry(self.org_frame, textvariable=self.dest_var, width=40).grid(row=1, column=1, sticky='ew')
        tk.Button(self.org_frame, text="Browse", command=self.browse_dest).grid(row=1, column=2, sticky='ew')

        op_frame = tk.Frame(self.org_frame)
        op_frame.grid(row=2, column=1, pady=5, sticky='w')
        tk.Radiobutton(op_frame, text="Copy", variable=self.op_var, value='copy').grid(row=0, column=0, sticky='w')
        tk.Radiobutton(op_frame, text="Move", variable=self.op_var, value='move').grid(row=0, column=1, sticky='w')


        # --- Preview/Scan and Dry Run Buttons ---

        preview_btn = tk.Button(self.org_frame, text="Quick Scan (Async)", width=18, command=self.show_scan_info)
        preview_btn.grid(row=3, column=0, sticky='ew', pady=2)
        self.dry_run_cb = tk.Checkbutton(self.org_frame, text="Dry Run (Full Simulation, No File Changes)", variable=self.dry_run_var)
        self.dry_run_cb.grid(row=3, column=1, sticky='w')

        tag_frame = tk.Frame(self.org_frame)
        tag_frame.grid(row=4, column=0, columnspan=2, sticky='ew', pady=2)
        tag_frame.grid_columnconfigure(0, weight=0)
        tag_frame.grid_columnconfigure(1, weight=1)
        label_tag_order = tk.Label(tag_frame, text="Metadata date tag order (top = first):")
        label_tag_order.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0,2))
        # Add dropdowns for tag order selection (use grid for visibility and alignment)
        for i, var in enumerate(self.tag_vars):
            tk.Label(tag_frame, text=f"{i+1}.").grid(row=i+1, column=0, sticky='e', padx=(10,2), pady=1)
            om = tk.OptionMenu(tag_frame, var, *self.date_tag_options)
            om.grid(row=i+1, column=1, sticky='ew', padx=(0,10), pady=1)
        # Checkbox for using earliest date from available tags
        tk.Checkbutton(tag_frame, text="Use earliest date from available tags (ignore order)", variable=self.use_earliest_date).grid(row=len(self.tag_vars)+2, column=0, columnspan=2, sticky='w', pady=(6,0))

        # Duplicate handling is automatic: a destination holding identical content
        # is left alone, and one holding different content pushes this file to the
        # next free _1, _2, ... name. Nothing is ever overwritten.
        dup_frame = tk.Frame(self.org_frame)
        dup_frame.grid(row=4, column=2, rowspan=1, sticky='ne', padx=5, pady=2)
        tk.Label(dup_frame, text="If file exists:").grid(row=0, column=0, sticky='w')
        tk.Label(
            dup_frame,
            text="Identical files are skipped. Different files with the same name "
                 "are kept alongside as _1, _2, ...",
            fg='gray', wraplength=180, justify='left',
        ).grid(row=1, column=0, sticky='w', pady=(2, 0))


        self.organize_btn = tk.Button(self.org_frame, text="Organize", command=self.start_organize, width=20)
        self.organize_btn.grid(row=5, column=1, pady=10, sticky='ew')
        # Preview button removed; dry run provides similar functionality
        self.cancel_btn = tk.Button(self.org_frame, text="Cancel", command=self.cancel_organize, width=10, state='disabled')
        self.cancel_btn.grid(row=5, column=2, pady=10, sticky='ew')

        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(self.org_frame, variable=self.progress_var, maximum=100)
        self.progress.grid(row=6, column=1, sticky='ew', pady=5)
        self.eta_var = tk.StringVar(value="")
        self.eta_label = tk.Label(self.org_frame, textvariable=self.eta_var, anchor='w', fg='green')
        self.eta_label.grid(row=6, column=2, sticky='w')
        self.current_file_var = tk.StringVar(value="")
        self.current_file_label = tk.Label(self.org_frame, textvariable=self.current_file_var, anchor='w', fg='blue')
        self.current_file_label.grid(row=7, column=0, columnspan=3, sticky='ew')
        self.log_window = scrolledtext.ScrolledText(self.org_frame, width=60, height=10, state='disabled')
        self.log_window.grid(row=8, column=0, columnspan=3, pady=5, sticky='nsew')
        # Add color tags for log window
        self.log_window.tag_config('error', foreground='red')
        self.log_window.tag_config('warning', foreground='orange')
        self.include_images = tk.BooleanVar(value=True)
        self.include_videos = tk.BooleanVar(value=True)
        filter_frame = tk.Frame(self.org_frame)
        filter_frame.grid(row=9, column=0, columnspan=3, sticky='w')
        tk.Label(filter_frame, text="File types:").pack(side='left')
        tk.Checkbutton(filter_frame, text="Images", variable=self.include_images).pack(side='left')
        tk.Checkbutton(filter_frame, text="Videos", variable=self.include_videos).pack(side='left')

        # --- Metadata Viewer Tab ---
        meta_frame = tk.Frame(self.notebook, padx=10, pady=10)
        self.notebook.add(meta_frame, text="Metadata Viewer")

        meta_file_frame = tk.Frame(meta_frame)
        meta_file_frame.pack(fill='x', pady=5)
        self.meta_file_var = tk.StringVar()
        tk.Label(meta_file_frame, text="Select File:").pack(side='left')
        tk.Entry(meta_file_frame, textvariable=self.meta_file_var, width=50).pack(side='left', padx=2)
        tk.Button(meta_file_frame, text="Browse", command=self.browse_meta_file).pack(side='left', padx=2)
        tk.Button(meta_file_frame, text="View Metadata", command=self.view_metadata).pack(side='left', padx=2)

        # --- Metadata Search and Table ---
        search_frame = tk.Frame(meta_frame)
        search_frame.pack(fill='x', pady=(0, 5))
        tk.Label(search_frame, text="Search:").pack(side='left')
        self.meta_search_var = tk.StringVar()
        self.meta_search_var.trace_add('write', lambda *args: self.filter_metadata_table())
        search_entry = tk.Entry(search_frame, textvariable=self.meta_search_var, width=30)
        search_entry.pack(side='left', padx=(2, 10))
        # Table for metadata
        self.meta_table = ttk.Treeview(meta_frame, columns=("Key", "Value"), show="headings", height=25)
        self.meta_table.heading("Key", text="Key")
        self.meta_table.heading("Value", text="Value")
        self.meta_table.column("Key", width=200, anchor='w')
        self.meta_table.column("Value", width=500, anchor='w')
        self.meta_table.pack(fill='both', expand=True, pady=5)
        # Add tag for highlighting important keys
        self.meta_table.tag_configure('highlight', foreground='blue', font=('TkDefaultFont', 10, 'bold'))
        # Info label
        self.meta_info_label = tk.Label(meta_frame, text='Select a file and click "View Metadata" to see all available metadata.', anchor='w', fg='gray')
        self.meta_info_label.pack(fill='x', pady=(0, 5))

    def show_scan_info(self):
        """Show async scan dialog with clear explanation."""
        from tkinter import messagebox
        msg = (
            "Quick Scan (Async):\n\n"
            "- Quickly lists all supported files in the source folder using a fast, memory-efficient scan.\n"
            "- Lets you preview and cancel before organizing.\n"
            "- Does NOT simulate file moves/copies or show destination paths.\n\n"
            "For a full simulation of the batch operation (including destination paths, duplicate handling, and errors), use Dry Run."
        )
        if messagebox.askokcancel("Quick Scan Info", msg):
            self.scan_files_dialog()

    def browse_meta_file(self):
        path = filedialog.askopenfilename(title="Select media file")
        if path:
            self.meta_file_var.set(path)

    def view_metadata(self):
        try:
            if not hasattr(self, 'meta_table'):
                logger.debug('VIEW_METADATA CLICKED (no meta_table widget)')
                return
            self.meta_table.delete(*self.meta_table.get_children())
            self.meta_info_label.config(text='')
            from media_organizer.app.metadata_extractor import extract_metadata
            import sys, os, traceback
            file_path = self.meta_file_var.get()
            if not file_path:
                self.meta_info_label.config(text='No file selected.', fg='red')
                return
            # --- Extract metadata ---
            try:
                meta = extract_metadata(file_path)
            except Exception as e:
                tb = traceback.format_exc()
                from tkinter import messagebox
                messagebox.showerror("Metadata Viewer Error", f"Error in metadata viewer:\n{e}\n\n{tb}")
                self.meta_info_label.config(text=f'Error: {e}', fg='red')
                return
            if meta is None:
                self.meta_info_label.config(text='No metadata found or file not supported.', fg='red')
                return
            if isinstance(meta, dict) and 'error' in meta:
                from tkinter import messagebox
                error_type = meta.get('type')
                user_msg = meta['error']
                if error_type == 'timeout':
                    messagebox.showerror("Metadata Extraction Timeout", user_msg)
                elif error_type == 'missing_exiftool':
                    messagebox.showerror("ExifTool Not Found", user_msg)
                elif error_type == 'corrupt_or_unsupported':
                    messagebox.showerror("Metadata Extraction Error", user_msg)
                else:
                    messagebox.showerror("Metadata Extraction Error", user_msg)
                self.meta_info_label.config(text=f"Error extracting metadata: {meta['error']}", fg='red')
                return
            if isinstance(meta, dict):
                # Highlight important tags
                important_tags = {"DateTimeOriginal", "CreateDate", "MediaCreateDate", "SubSecDateTimeOriginal", "TrackCreateDate", "QuickTime:CreationDate", "ModifyDate", "MetadataDate", "FileCreateDate", "FileModifyDate", "DigitalCreationDate", "DateCreated", "OriginalReleaseTime", "ContentCreateDate", "CreationDate"}
                self._meta_table_data = []
                for k in sorted(meta.keys()):
                    v = meta[k]
                    tag = 'highlight' if k in important_tags else ''
                    self.meta_table.insert('', 'end', values=(k, v), tags=(tag,))
                    self._meta_table_data.append((k, v, tag))
                self.meta_info_label.config(text=f"{len(meta)} metadata tags found.", fg='gray')
            else:
                self.meta_info_label.config(text=f"Unexpected metadata type: {type(meta)}", fg='red')
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.meta_info_label.config(text=f'Error: {e}', fg='red')
            logger.error(f'view_metadata exception: {e}\n{tb}')

    def filter_metadata_table(self):
        # Filter the metadata table based on the search box
        if not hasattr(self, '_meta_table_data'):
            return
        query = self.meta_search_var.get().strip().lower()
        self.meta_table.delete(*self.meta_table.get_children())
        for k, v, tag in self._meta_table_data:
            if query in k.lower() or query in str(v).lower():
                self.meta_table.insert('', 'end', values=(k, v), tags=(tag,))

    def _log_callback(self, msg):
        # Throttle log updates: buffer messages and flush every 100ms or if buffer is large
        if not hasattr(self, '_log_buffer'):
            self._log_buffer = []
            self._log_flush_scheduled = False
        self._log_buffer.append(msg)
        # Log to debug for troubleshooting
        logger.debug(f"Log callback received: {msg}")
        if len(self._log_buffer) >= 20:
            self._flush_log_buffer()
        elif not self._log_flush_scheduled:
            self._log_flush_scheduled = True
            self.root.after(100, self._flush_log_buffer)

    def _flush_log_buffer(self):
        if not hasattr(self, '_log_buffer') or not self._log_buffer:
            self._log_flush_scheduled = False
            return
        # Log flush event at debug level
        logger.debug(f"Flushing {len(self._log_buffer)} log buffer messages")
        if hasattr(self, 'log_window') and self.log_window:
            self.log_window.config(state='normal')
            for msg in self._log_buffer:
                self.log_window.insert('end', msg + '\n')
            self.log_window.config(state='disabled')
            self.log_window.see('end')
        self._log_buffer.clear()
        self._log_flush_scheduled = False

    def _progress_callback(self, pct):
        if hasattr(self, 'progress_var'):
            self.progress_var.set(pct)
            # Force UI update for smoother progress
            self.root.update_idletasks()

    def browse_source(self):
        path = filedialog.askdirectory(initialdir=self.source_var.get() or None)
        if path:
            self.source_var.set(path)
            self.save_last_folders()

    def browse_dest(self):
        path = filedialog.askdirectory(initialdir=self.dest_var.get() or None)
        if path:
            self.dest_var.set(path)
            self.save_last_folders()

    def save_last_folders(self):
        data = {
            'source': self.source_var.get(),
            'dest': self.dest_var.get()
        }
        try:
            with open(self.config_path, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass

    def load_last_folders(self):
        try:
            with open(self.config_path) as f:
                data = json.load(f)
            self.source_var.set(data.get('source', ''))
            self.dest_var.set(data.get('dest', ''))
        except Exception:
            pass

    def start_organize(self):
        if self.is_processing:
            return
        source = self.source_var.get()
        dest = self.dest_var.get()
        operation = self.op_var.get()
        dry_run = self.dry_run_var.get()
        tag_order = [v.get().strip() for v in self.tag_vars if v.get().strip()]
        use_earliest = self.use_earliest_date.get()
        # File type filter
        formats = []
        if self.include_images.get():
            formats += IMAGE_FORMATS
        if self.include_videos.get():
            formats += VIDEO_FORMATS
        if not formats:
            messagebox.showerror("Error", "Please select at least one file type (images or videos).")
            return
        if not source or not dest:
            messagebox.showerror("Error", "Please select both source and destination folders.")
            return
        self.progress_var.set(0)
        self.eta_var.set("")
        self.is_processing = True
        self.organize_btn.config(state='disabled')
        self.cancel_btn.config(state='normal')
        self.current_file_var.set("")
        self.summary = {'organized': 0, 'skipped': 0, 'errors': 0}
        # Allow user to configure max workers (concurrent ExifTool processes)
        import os
        max_workers = 4
        try:
            max_workers = int(os.environ.get('MEDIA_ORGANIZER_MAX_WORKERS', 4))
        except Exception:
            max_workers = 4
        # Show status in log window
        self.log_callback(f"[INFO] Using up to {max_workers} concurrent ExifTool processes.")
        # Force immediate log flush so user sees output right away
        self._flush_log_buffer()
        def run_with_error_handling():
            try:
                self.run_with_summary(source, dest, operation, dry_run, tag_order, formats, max_workers, use_earliest)
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                err_msg = f"[FATAL ERROR] Batch operation failed: {e}\n{tb}"
                self.log_callback(err_msg)
                try:
                    from tkinter import messagebox
                    self.root.after(0, lambda: messagebox.showerror("Batch Error", err_msg))
                except Exception:
                    pass
        threading.Thread(target=run_with_error_handling, daemon=True).start()

    def cancel_organize(self):
        self.controller.cancel()
        self.cancel_btn.config(state='disabled')
        self.is_processing = False
        self.batch_cancelled = True
        self.organize_btn.config(state='normal')
        # Show summary dialog after cancel so user sees what was done
        self.show_summary_dialog()

    def run_with_summary(self, source, dest, operation, dry_run, tag_order, formats=None, max_workers=4, use_earliest=False):
        self.batch_cancelled = False
        def eta_callback(eta):
            if eta > 0:
                self.eta_var.set(f"ETA: {eta//60}m {eta%60}s")
            else:
                self.eta_var.set("")
            self.root.update_idletasks()
        self.skipped_files = []
        self.error_files = []
        def log_hook(msg):
            self.log_callback(msg)
            lower_msg = msg.lower()
            # Show current file in UI if possible
            if hasattr(self, 'current_file_var') and ("processing:" in lower_msg or "processing" in lower_msg):
                import re
                m = re.search(r'processing: (.+)', lower_msg)
                if m:
                    self.current_file_var.set(m.group(1))
                    self.root.update_idletasks()
            # Match for successful file operations
            if any(word in lower_msg for word in ["copied", "moved", "moved file", "copied file", "file moved", "file copied"]):
                self.summary['organized'] += 1
            # Match for skipped files
            elif any(word in lower_msg for word in ["skipping", "skipped", "already exists", "duplicate", "no date found", "unsupported"]):
                self.summary['skipped'] += 1
                self.skipped_files.append(msg)
            # Match for errors
            elif any(word in lower_msg for word in ["failed", "error", "could not", "permission denied", "exception"]):
                self.summary['errors'] += 1
                self.error_files.append(msg)
        # Memory warning callback for large datasets
        def memory_warning_callback(title, message):
            """Show memory warning dialog and return user's choice."""
            return messagebox.askyesno(
                title,
                message + "\n\nDo you want to continue with this operation?",
                icon='warning'
            )
        
        orig_log = self.controller.log_callback
        self.controller.log_callback = log_hook
        self.controller.organize_batch(
            source, dest, operation, dry_run, tag_order, use_earliest,
            formats=formats, eta_callback=eta_callback, max_workers=max_workers,
            memory_warning_callback=memory_warning_callback
        )
        self.controller.log_callback = orig_log
        self.is_processing = False
        self.organize_btn.config(state='normal')
        self.cancel_btn.config(state='disabled')
        if dry_run:
            self.show_dry_run_dialog()
        else:
            self.show_summary_dialog()


    def show_summary_dialog(self):
        import tkinter as tk
        from tkinter import Toplevel, Label, Button, scrolledtext, filedialog, messagebox
        from media_organizer.app.batch_results_db import BatchResultsDB
        msg = f"Files organized: {self.summary['organized']}\nFiles skipped: {self.summary['skipped']}\nErrors: {self.summary['errors']}"
        if hasattr(self, 'batch_cancelled') and self.batch_cancelled:
            msg = "Batch cancelled by user!\n" + msg
        win = Toplevel(self.root)
        win.title("Summary")
        Label(win, text=msg, anchor='w', justify='left', fg='red' if getattr(self, 'batch_cancelled', False) else 'black').pack(padx=10, pady=5, anchor='w')

        # Pagination controls
        page_size = 100
        page_var = tk.IntVar(value=0)
        results = []
        def load_page():
            st.config(state='normal')
            st.delete('1.0', 'end')
            offset = page_var.get() * page_size
            results.clear()
            db = self.controller.batch_db
            if db is not None:
                rows = db.fetch_results(limit=page_size, offset=offset)
                for row in rows:
                    filename, action, status, metadata, error = row
                    results.append(row)
                    line = f"{filename} | {action} | {status}"
                    if error:
                        line += f" | ERROR: {error}"
                    st.insert('end', line + '\n')
            st.config(state='disabled')
            page_label.config(text=f"Page {page_var.get()+1}")

        st = scrolledtext.ScrolledText(win, width=90, height=15)
        st.pack(padx=10, pady=5)

        nav_frame = tk.Frame(win)
        nav_frame.pack(pady=2)
        prev_btn = Button(nav_frame, text="Previous", command=lambda: (page_var.set(max(0, page_var.get()-1)), load_page()))
        next_btn = Button(nav_frame, text="Next", command=lambda: (page_var.set(page_var.get()+1), load_page()))
        page_label = Label(nav_frame, text="Page 1")
        prev_btn.pack(side='left', padx=2)
        page_label.pack(side='left', padx=2)
        next_btn.pack(side='left', padx=2)

        def export_errors():
            file_path = filedialog.asksaveasfilename(
                title="Export Errors/Warnings",
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv"), ("Text Files", "*.txt"), ("All Files", "*.*")]
            )
            if not file_path:
                return
            try:
                db = self.controller.batch_db
                all_rows = []
                offset = 0
                if db is not None:
                    while True:
                        rows = db.fetch_results(limit=page_size, offset=offset)
                        if not rows:
                            break
                        all_rows.extend(rows)
                        offset += page_size
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('filename,action,status,error\n')
                    for row in all_rows:
                        filename, action, status, metadata, error = row
                        if error or status == 'error':
                            f.write(f'"{filename}","{action}","{status}","{error or ""}"\n')
                messagebox.showinfo("Export Complete", f"Errors and warnings exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Could not export errors/warnings:\n{e}")

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=5)
        Button(btn_frame, text="OK", command=win.destroy).pack(side='left', padx=5)
        Button(btn_frame, text="Export Errors/Warnings", command=export_errors).pack(side='left', padx=5)

        load_page()


    # Preview functionality removed; dry run provides similar functionality


    # Preview dialog removed; dry run provides similar functionality

    def show_about_dialog(self):
        from tkinter import Toplevel, Label, Button, scrolledtext
        win = Toplevel(self.root)
        win.title("About / Help")
        win.geometry("600x400")
        info = f"""
Media Organizer v{APP_VERSION}

A modular Python app to organize your photos and videos by date using ExifTool.

Quick Usage Tips:
- Select a source and destination folder.
- Choose Move or Copy.
- Optionally adjust the metadata tag order for date extraction.
- Use Preview to see what will be organized before starting.
- Use Dry Run to simulate without making changes.
- Filter by file type (images/videos).
- Progress, ETA, and logs are shown during operation.
- Files are organized into /YYYY/MM/ subfolders by date.
- Skipped files (missing/invalid date) are shown in the summary.

Supported formats:
- Images: {', '.join(IMAGE_FORMATS)}
- Videos: {', '.join(VIDEO_FORMATS)}

Requirements:
- Python 3.10+
- ExifTool (https://exiftool.org/)

For more info, see the README or project repository.
"""
        st = scrolledtext.ScrolledText(win, width=70, height=20)
        st.pack(padx=10, pady=10, fill='both', expand=True)
        st.insert('end', info)
        st.configure(state='disabled')
        Button(win, text="OK", command=win.destroy).pack(pady=5)

# Check for ExifTool at startup
if not check_exiftool():
    messagebox.showerror("ExifTool Missing", "ExifTool is not installed or not found in PATH. Please install ExifTool to use this app.")
    exit(1)

# Main entry point
if __name__ == "__main__":
    root: Optional[tk.Tk] = None
    try:
        root = tk.Tk()
        import tkinter.ttk  # Needed for Progressbar
        app = MediaOrganizerApp(root)
        # log_window tags are now set in __init__
        root.mainloop()
    except Exception as e:
        import traceback
        import tkinter as tk
        from tkinter import messagebox
        err = f"Startup error: {e}\n\n{traceback.format_exc()}"
        try:
            # Only create a new Tk root if one does not already exist
            if root is not None:
                root.withdraw()
                messagebox.showerror("Startup Error", err)
                root.destroy()
            else:
                temp_root = tk.Tk()
                temp_root.withdraw()
                messagebox.showerror("Startup Error", err)
                temp_root.destroy()
        except Exception:
            logger.error(err)

# Handle optional exiftool import
try:
    import exiftool
    from media_organizer.app.exiftool_check import get_exiftool_path
    # Note: PyExifTool uses a different API than exiftool_wrapper
    logger.info("ExifTool library available")
except ImportError:
    logger.warning("exiftool library not available - some functionality may be limited")

