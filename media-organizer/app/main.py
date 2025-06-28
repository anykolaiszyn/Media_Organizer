import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
from .ui_controller import MediaOrganizerController
from .exiftool_check import check_exiftool
from .config import IMAGE_FORMATS, VIDEO_FORMATS
import json
import os

APP_VERSION = "1.0.0"

# --- UI Setup ---
class MediaOrganizerApp:
        # Duplicate handling option
        self.duplicate_mode = tk.StringVar(value='overwrite')
        dup_frame = tk.Frame(org_frame)
        dup_frame.grid(row=4, column=2, rowspan=1, sticky='ne', padx=5)
        tk.Label(dup_frame, text="If file exists:").pack(anchor='w')
        tk.Radiobutton(dup_frame, text="Overwrite", variable=self.duplicate_mode, value='overwrite').pack(anchor='w')
        tk.Radiobutton(dup_frame, text="Preserve (append _1, _2, ...)", variable=self.duplicate_mode, value='preserve').pack(anchor='w')
        # Info label for overwrite
        self.dup_info_label = tk.Label(dup_frame, text="If a file with the same name exists in the destination, it will be overwritten.", fg='orange', wraplength=180, justify='left')
        self.dup_info_label.pack(anchor='w', pady=(2,0))
    def __init__(self, root):
        self.root = root
        self.log_callback = self._log_callback
        self.progress_callback = self._progress_callback
        self.controller = MediaOrganizerController(self.log_callback, self.progress_callback)
        root.title("Media Organizer")

        # Add menu bar with Help/About
        menubar = tk.Menu(root)
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="About / Help...", command=self.show_about_dialog)
        menubar.add_cascade(label="Help", menu=helpmenu)
        root.config(menu=menubar)

        self.config_path = os.path.join(os.path.expanduser('~'), '.media_organizer_config.json')
        self.source_var = tk.StringVar()
        self.dest_var = tk.StringVar()
        self.op_var = tk.StringVar(value='copy')
        self.dry_run_var = tk.BooleanVar(value=False)
        # Metadata date tags (expanded list)
        self.date_tag_options = [
            "DateTimeOriginal",
            "MediaCreateDate",
            "CreateDate",
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
        self.tag_vars = [tk.StringVar(value=tag) for tag in self.date_tag_options[:5]]
        self.is_processing = False

        self.load_last_folders()

        # --- Tabbed UI ---
        import tkinter.ttk as ttk
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=True, fill="both")

        # --- Organizer Tab ---
        org_frame = tk.Frame(self.notebook, padx=10, pady=10)
        self.notebook.add(org_frame, text="Organizer")

        for i in range(3):
            org_frame.grid_columnconfigure(i, weight=1)
        for i in range(10):
            org_frame.grid_rowconfigure(i, weight=0)
        org_frame.grid_rowconfigure(8, weight=1)

        tk.Label(org_frame, text="Source Folder:").grid(row=0, column=0, sticky='e')
        tk.Entry(org_frame, textvariable=self.source_var, width=40).grid(row=0, column=1, sticky='ew')
        tk.Button(org_frame, text="Browse", command=self.browse_source).grid(row=0, column=2, sticky='ew')

        tk.Label(org_frame, text="Destination Folder:").grid(row=1, column=0, sticky='e')
        tk.Entry(org_frame, textvariable=self.dest_var, width=40).grid(row=1, column=1, sticky='ew')
        tk.Button(org_frame, text="Browse", command=self.browse_dest).grid(row=1, column=2, sticky='ew')

        op_frame = tk.Frame(org_frame)
        op_frame.grid(row=2, column=1, pady=5, sticky='w')
        tk.Radiobutton(op_frame, text="Copy", variable=self.op_var, value='copy').pack(side='left')
        tk.Radiobutton(op_frame, text="Move", variable=self.op_var, value='move').pack(side='left')

        self.dry_run_cb = tk.Checkbutton(org_frame, text="Dry Run (no file changes)", variable=self.dry_run_var)
        self.dry_run_cb.grid(row=3, column=1, sticky='w')

        tag_frame = tk.Frame(org_frame)
        tag_frame.grid(row=4, column=0, columnspan=3, sticky='ew', pady=2)
        tag_frame.grid_columnconfigure(0, weight=1)
        tk.Label(tag_frame, text="Metadata date tag order (top = first):").pack(anchor='w')
        self.tag_combos = []
        for i, var in enumerate(self.tag_vars):
            combo = ttk.Combobox(tag_frame, textvariable=var, width=22, values=self.date_tag_options)
            combo.pack(side='left', padx=2)
            combo['state'] = 'normal'
            self.tag_combos.append(combo)

        # Duplicate handling option (radio buttons)
        self.duplicate_mode = tk.StringVar(value='overwrite')
        dup_frame = tk.Frame(org_frame)
        dup_frame.grid(row=4, column=2, rowspan=1, sticky='ne', padx=5)
        tk.Label(dup_frame, text="If file exists:").pack(anchor='w')
        tk.Radiobutton(dup_frame, text="Overwrite", variable=self.duplicate_mode, value='overwrite').pack(anchor='w')
        tk.Radiobutton(dup_frame, text="Preserve (append _1, _2, ...)", variable=self.duplicate_mode, value='preserve').pack(anchor='w')
        # Info label for overwrite
        self.dup_info_label = tk.Label(dup_frame, text="If a file with the same name exists in the destination, it will be overwritten.", fg='orange', wraplength=180, justify='left')
        self.dup_info_label.pack(anchor='w', pady=(2,0))

        self.organize_btn = tk.Button(org_frame, text="Organize", command=self.start_organize, width=20)
        self.organize_btn.grid(row=5, column=1, pady=10, sticky='ew')
        self.preview_btn = tk.Button(org_frame, text="Preview", command=self.show_preview_dialog, width=10)
        self.preview_btn.grid(row=5, column=0, pady=10, sticky='ew')
        self.cancel_btn = tk.Button(org_frame, text="Cancel", command=self.cancel_organize, width=10, state='disabled')
        self.cancel_btn.grid(row=5, column=2, pady=10, sticky='ew')

        self.progress_var = tk.DoubleVar(value=0)
        self.progress = tk.ttk.Progressbar(org_frame, variable=self.progress_var, maximum=100)
        self.progress.grid(row=6, column=1, sticky='ew', pady=5)
        self.eta_var = tk.StringVar(value="")
        self.eta_label = tk.Label(org_frame, textvariable=self.eta_var, anchor='w', fg='green')
        self.eta_label.grid(row=6, column=2, sticky='w')
        self.current_file_var = tk.StringVar(value="")
        self.current_file_label = tk.Label(org_frame, textvariable=self.current_file_var, anchor='w', fg='blue')
        self.current_file_label.grid(row=7, column=0, columnspan=3, sticky='ew')
        self.log_window = scrolledtext.ScrolledText(org_frame, width=60, height=10, state='disabled')
        self.log_window.grid(row=8, column=0, columnspan=3, pady=5, sticky='nsew')
        self.include_images = tk.BooleanVar(value=True)
        self.include_videos = tk.BooleanVar(value=True)
        filter_frame = tk.Frame(org_frame)
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

        self.meta_text = scrolledtext.ScrolledText(meta_frame, width=90, height=28, state='normal')
        self.meta_text.pack(fill='both', expand=True, pady=5)
        self.meta_text.insert('end', 'Select a file and click "View Metadata" to see all available metadata.')
        self.meta_text.config(state='disabled')
    def browse_meta_file(self):
        path = filedialog.askopenfilename(title="Select media file")
        if path:
            self.meta_file_var.set(path)

    def view_metadata(self):
        from .metadata_extractor import extract_metadata
        file_path = self.meta_file_var.get()
        self.meta_text.config(state='normal')
        self.meta_text.delete('1.0', 'end')
        if not file_path:
            self.meta_text.insert('end', 'No file selected.')
            self.meta_text.config(state='disabled')
            return
        try:
            meta = extract_metadata(file_path)
            if not meta:
                self.meta_text.insert('end', 'No metadata found or file not supported.')
            else:
                for k in sorted(meta.keys()):
                    self.meta_text.insert('end', f'{k}: {meta[k]}\n')
        except Exception as e:
            self.meta_text.insert('end', f'Error reading metadata: {e}')
        self.meta_text.config(state='disabled')

    def _log_callback(self, msg):
        # Example: append to log window if available
        if hasattr(self, 'log_window') and self.log_window:
            self.log_window.config(state='normal')
            self.log_window.insert('end', msg + '\n')
            self.log_window.config(state='disabled')
            self.log_window.see('end')
        # Optionally print to console
        # print(msg)

    def _progress_callback(self, pct):
        if hasattr(self, 'progress_var'):
            self.progress_var.set(pct)

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
        duplicate_mode = self.duplicate_mode.get()
        threading.Thread(target=self.run_with_summary, args=(source, dest, operation, dry_run, tag_order, formats, duplicate_mode), daemon=True).start()

    def cancel_organize(self):
        self.controller.cancel()
        self.cancel_btn.config(state='disabled')

    def run_with_summary(self, source, dest, operation, dry_run, tag_order, formats=None, duplicate_mode='overwrite'):
        def eta_callback(eta):
            if eta > 0:
                self.eta_var.set(f"ETA: {eta//60}m {eta%60}s")
            else:
                self.eta_var.set("")
        self.skipped_files = []
        self.error_files = []
        def log_hook(msg):
            self.log_callback(msg)
            if msg.startswith("Copied") or msg.startswith("Moved"):
                self.summary['organized'] += 1
            elif "Skipping" in msg:
                self.summary['skipped'] += 1
                self.skipped_files.append(msg)
            elif "Failed" in msg or "error" in msg.lower():
                self.summary['errors'] += 1
                self.error_files.append(msg)
        orig_log = self.controller.log_callback
        self.controller.log_callback = log_hook
        self.controller.run_organizer(source, dest, operation, dry_run, tag_order, eta_callback=eta_callback, formats=formats, duplicate_mode=duplicate_mode)
        self.controller.log_callback = orig_log
        self.is_processing = False
        self.organize_btn.config(state='normal')
        self.cancel_btn.config(state='disabled')
        self.show_summary_dialog()

    def show_summary_dialog(self):
        import tkinter as tk
        from tkinter import Toplevel, Label, Button, scrolledtext
        msg = f"Files organized: {self.summary['organized']}\nFiles skipped: {self.summary['skipped']}\nErrors: {self.summary['errors']}"
        win = Toplevel(self.root)
        win.title("Summary")
        Label(win, text=msg, anchor='w', justify='left').pack(padx=10, pady=5, anchor='w')
        if self.skipped_files or self.error_files:
            st = scrolledtext.ScrolledText(win, width=70, height=10)
            st.pack(padx=10, pady=5)
            if self.skipped_files:
                st.insert('end', 'Skipped files:\n' + '\n'.join(self.skipped_files) + '\n\n')
            if self.error_files:
                st.insert('end', 'Error files:\n' + '\n'.join(self.error_files) + '\n')
            st.configure(state='disabled')
        Button(win, text="OK", command=win.destroy).pack(pady=5)

    def show_preview_dialog(self):
        source = self.source_var.get()
        dest = self.dest_var.get()
        tag_order = [v.get().strip() for v in self.tag_vars if v.get().strip()]
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
        # Setup cancel flag for preview
        self.preview_cancel_flag = threading.Event()
        self.progress_var.set(0)
        self.cancel_btn.config(state='disabled')  # Disable main cancel during preview

        # Show a minimal progress/cancel dialog during preview scan
        preview_progress_win = tk.Toplevel(self.root)
        preview_progress_win.title("Previewing...")
        tk.Label(preview_progress_win, text="Scanning files for preview...").pack(padx=10, pady=5)
        progress_bar = tk.ttk.Progressbar(preview_progress_win, variable=self.progress_var, maximum=100, length=300)
        progress_bar.pack(padx=10, pady=5)
        cancel_btn = tk.Button(preview_progress_win, text="Cancel", width=12, command=lambda: self.preview_cancel_flag.set())
        cancel_btn.pack(pady=5)

        def preview_progress_callback(pct):
            self.progress_var.set(pct)
            self.root.update_idletasks()

        def do_preview():
            preview, skipped = self.controller.get_preview_list(
                source, dest, tag_order=tag_order, formats=formats,
                progress_callback=preview_progress_callback, cancel_flag=self.preview_cancel_flag)
            self.root.after(0, lambda: [preview_progress_win.destroy(), self._show_preview_dialog(preview, skipped)])

        threading.Thread(target=do_preview, daemon=True).start()

    def _show_preview_dialog(self, preview, skipped):
        from tkinter import Toplevel, Label, Button, scrolledtext
        win = Toplevel(self.root)
        win.title("Preview - Files to be Organized")
        msg = f"Files to be organized: {len(preview)}\nFiles skipped: {len(skipped)}"
        Label(win, text=msg, anchor='w', justify='left').pack(padx=10, pady=5, anchor='w')
        st = scrolledtext.ScrolledText(win, width=90, height=20)
        st.pack(padx=10, pady=5)
        if preview:
            st.insert('end', 'Source → Destination:\n')
            for src, dst in preview:
                st.insert('end', f'{src}  →  {dst}\n')
        if skipped:
            st.insert('end', '\nSkipped files:\n')
            for src, reason in skipped:
                st.insert('end', f'{src}  ({reason})\n')
        st.configure(state='disabled')
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=5)
        def start_and_close():
            win.destroy()
            self.start_organize()
        Button(btn_frame, text="Start", command=start_and_close, width=12).pack(side='left', padx=5)
        Button(btn_frame, text="Cancel", command=win.destroy, width=12).pack(side='left', padx=5)

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
    root = tk.Tk()
    import tkinter.ttk  # Needed for Progressbar
    app = MediaOrganizerApp(root)
    # Add color tags for log window
    app.log_window.tag_config('error', foreground='red')
    app.log_window.tag_config('warning', foreground='orange')
    root.mainloop()
