import time
import types
import pytest
from media_organizer.app.main import MediaOrganizerApp

class DummyRoot:
    def after(self, ms, func):
        # Call immediately for test
        func()

class DummyLogWindow:
    def __init__(self):
        self.lines = []
        self.state = 'normal'
    def config(self, state=None):
        self.state = state or self.state
    def insert(self, where, msg):
        self.lines.append(msg)
    def see(self, where):
        pass

def test_log_throttling_flush():
    app = MediaOrganizerApp.__new__(MediaOrganizerApp)
    app.root = DummyRoot()
    app.log_window = DummyLogWindow()
    app._log_buffer = []
    app._log_flush_scheduled = False
    # Add 25 messages (should flush at 20, then at 25)
    for i in range(25):
        app._log_callback(f"msg {i}")
    # Because DummyRoot.after calls flush immediately, buffer is always empty
    assert len(app._log_buffer) == 0
    # All messages should be in log_window
    assert len(app.log_window.lines) == 25
    assert app.log_window.lines[0].startswith('msg 0')
    assert app.log_window.lines[-1].startswith('msg 24')
