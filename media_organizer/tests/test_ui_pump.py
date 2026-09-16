"""The pump turns events into widget state, on the main thread."""
import queue
import tkinter as tk

import pytest

from media_organizer.app import batch_events as ev
from media_organizer.app.main import MediaOrganizerApp


@pytest.fixture
def app():
    root = tk.Tk()
    root.withdraw()
    instance = MediaOrganizerApp(root)
    yield instance
    root.destroy()


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
