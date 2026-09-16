"""Importing the GUI module must not mutate the global subprocess module.

main.py previously reassigned subprocess.Popen/run/call at import time. Because
asyncio.windows_utils does `class Popen(subprocess.Popen)`, replacing Popen with
a plain function makes `import asyncio` raise TypeError for the rest of the
process -- which aborted pytest collection for every test importing
unittest.mock.

These run in a fresh interpreter: importing main in-process would reintroduce
the very breakage under test.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_in_fresh_interpreter(code):
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_importing_main_leaves_subprocess_popen_a_class():
    result = _run_in_fresh_interpreter(
        "import subprocess\n"
        "import media_organizer.app.main\n"
        "assert isinstance(subprocess.Popen, type), (\n"
        "    'subprocess.Popen is %r, expected a class' % type(subprocess.Popen)\n"
        ")\n"
    )
    assert result.returncode == 0, result.stderr


def test_importing_main_leaves_subprocess_run_and_call_intact():
    result = _run_in_fresh_interpreter(
        "import subprocess\n"
        "import media_organizer.app.main\n"
        "for name in ('run', 'call'):\n"
        "    fn = getattr(subprocess, name)\n"
        "    assert fn.__module__ == 'subprocess', (\n"
        "        'subprocess.%s was replaced by %s.%s' % (name, fn.__module__, fn.__name__)\n"
        "    )\n"
    )
    assert result.returncode == 0, result.stderr


def test_asyncio_still_importable_after_importing_main():
    result = _run_in_fresh_interpreter(
        "import media_organizer.app.main\n"
        "import asyncio\n"
    )
    assert result.returncode == 0, result.stderr
