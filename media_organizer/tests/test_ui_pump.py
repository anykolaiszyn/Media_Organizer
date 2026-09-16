"""The pump turns events into widget state, on the main thread."""
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
