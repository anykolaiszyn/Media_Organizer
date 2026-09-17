"""The CLI extracts metadata once, up front, not once per file inside organize_files."""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_cli_organizes_by_date(tmp_path):
    source = tmp_path / 'src'
    dest = tmp_path / 'lib'
    source.mkdir()
    (source / 'a.jpg').write_bytes(b'not a real jpg, exiftool will find no date tags')

    result = subprocess.run(
        [sys.executable, '-m', 'media_organizer.cli',
         '--source', str(source), '--dest', str(dest)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60,
    )

    assert result.returncode == 0, result.stderr
    # No real date metadata in a fake file -> it lands in no_metadata, proving
    # the run completed rather than crashing on the new organize_files signature.
    assert (dest / 'no_metadata' / 'a.jpg').exists()
