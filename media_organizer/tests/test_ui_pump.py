"""The pump turns events into widget state, on the main thread."""
import json
import os
import queue
import tkinter as tk

import pytest

from media_organizer.app import batch_events as ev
from media_organizer.app.main import MediaOrganizerApp


@pytest.fixture(scope='module')
def root():
    """One Tk interpreter for the whole file.

    Creating and destroying a tk.Tk() per test causes real Tcl-interpreter
    churn; occasionally (rare, but reproducible over dozens of runs) a new
    interpreter created shortly after the previous one was torn down hits
    `_tkinter.TclError: invalid command name "tcl_findLibrary"` during
    construction. Sharing one root across the module's tests avoids that
    churn. Each test still gets its own fresh `MediaOrganizerApp` (see the
    `app` fixture below), which rebuilds the whole widget tree on this root
    and tears it down again, so no state leaks between tests.
    """
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def app(root):
    instance = MediaOrganizerApp(root)
    yield instance
    # Tear down every widget this test's instance built on the shared root
    # (menu included), so the next test starts from a bare root again.
    for child in list(root.children.values()):
        child.destroy()


def test_pump_advances_progress_and_current_file(app):
    app.event_queue = queue.Queue()
    app.event_queue.put(ev.Scanned(total=4))
    app.event_queue.put(ev.FileStarted(path='C:/photos/a.jpg'))
    app.event_queue.put(ev.FileDone('C:/photos/a.jpg', 'wrote', None, 1, 4, 30))

    app._pump_batch_events()

    assert app.progress_var.get() == pytest.approx(25.0)
    assert app.current_file_var.get() == 'C:/photos/a.jpg'
    assert 'ETA' in app.eta_var.get()


def test_finished_counts_become_the_summary(app):
    app.event_queue = queue.Queue()
    app.event_queue.put(ev.Finished(
        counts={'wrote': 7, 'renamed': 2, 'skipped_identical': 5, 'error': 1},
        cancelled=False,
        elapsed=12.5,
    ))
    shown = {}
    app.show_summary_dialog = lambda: shown.update(app.summary)

    app._pump_batch_events()

    assert shown == {'organized': 9, 'skipped': 5, 'errors': 1, 'cancelled': 0}


def test_log_lines_reach_the_log_widget(app):
    app.event_queue = queue.Queue()
    app.event_queue.put(ev.LogLine(text='hello from the worker'))

    app._pump_batch_events()

    assert 'hello from the worker' in app.log_window.get('1.0', 'end')


def test_scan_dialog_uses_a_queue_not_direct_callbacks(app, monkeypatch):
    """scan_media_files_async must be handed an emit, never widget callbacks."""
    captured = {}

    def fake_async(source, formats=None, emit=None):
        captured['emit'] = emit
        captured['source'] = source

    monkeypatch.setattr(app.controller, 'scan_media_files_async', fake_async)
    # scan_files_dialog imports Toplevel locally, so there is no module-level
    # name to patch. Patch the real tkinter class instead: wait_window() runs
    # its own nested Tcl event loop and blocks until the window is destroyed
    # regardless of whether mainloop() was ever called, so leaving it
    # unpatched would hang this test forever.
    monkeypatch.setattr(tk.Toplevel, 'wait_window', lambda self: None)
    app.source_var.set('C:/photos')

    app.scan_files_dialog()

    assert callable(captured['emit'])
    assert captured['source'] == 'C:/photos'


def _destroy_children(root):
    for child in list(root.children.values()):
        child.destroy()


def test_save_then_reload_restores_tag_order_and_filters(root, tmp_path, monkeypatch):
    """Tag order, "use earliest," and the file-type filters round-trip through
    a real config file across a simulated restart.

    include_images/include_videos are the interesting case: they don't exist
    yet when load_last_folders() runs (it runs right after self.tag_vars is
    built, long before the widget-construction block creates those two
    vars), so load_last_folders() can't call .set() on them directly -- it
    stashes the parsed config on self._loaded_settings instead, and their
    *initial value* is seeded from that dict at construction time.
    Constructing a second, independent MediaOrganizerApp against the same
    config file (simulating a real restart) is what actually exercises that
    seeding path -- a regression back to a direct .set() call inside
    load_last_folders would be silently swallowed by its broad
    `except Exception: pass` and would show up here as include_images/
    include_videos staying at their True default instead of the saved
    value.
    """
    config_home = tmp_path / "home1"
    config_home.mkdir()
    monkeypatch.setattr(os.path, 'expanduser', lambda p: str(config_home))

    app = MediaOrganizerApp(root)
    try:
        app.source_var.set('C:/from')
        app.dest_var.set('C:/to')
        reordered = list(reversed([v.get() for v in app.tag_vars]))
        for var, tag in zip(app.tag_vars, reordered):
            var.set(tag)
        app.use_earliest_date.set(True)
        app.include_images.set(False)
        app.include_videos.set(False)

        app.save_last_folders()

        config_path = app.config_path
        assert os.path.exists(config_path)
        with open(config_path) as f:
            saved = json.load(f)
        assert saved['tag_order'] == reordered
        assert saved['use_earliest'] is True
        assert saved['include_images'] is False
        assert saved['include_videos'] is False
        assert saved['source'] == 'C:/from'
        assert saved['dest'] == 'C:/to'
    finally:
        _destroy_children(root)

    # Construct a fresh app against the same config file, simulating a real
    # restart.
    app2 = MediaOrganizerApp(root)
    try:
        assert app2.source_var.get() == 'C:/from'
        assert app2.dest_var.get() == 'C:/to'
        assert [v.get() for v in app2.tag_vars] == reordered
        assert app2.use_earliest_date.get() is True
        assert app2.include_images.get() is False
        assert app2.include_videos.get() is False
    finally:
        _destroy_children(root)


def test_missing_config_file_leaves_defaults_and_loaded_settings_a_dict(root, tmp_path, monkeypatch):
    config_home = tmp_path / "home2"
    config_home.mkdir()
    monkeypatch.setattr(os.path, 'expanduser', lambda p: str(config_home))

    app = MediaOrganizerApp(root)
    try:
        # No config file exists yet in this fresh temp home directory.
        assert app._loaded_settings == {}
        assert app.include_images.get() is True
        assert app.include_videos.get() is True
        assert app.use_earliest_date.get() is False
    finally:
        _destroy_children(root)
