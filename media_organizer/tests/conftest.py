# conftest.py
# Ensures the app/ directory is on sys.path for test imports
import sys
from pathlib import Path

root = Path(__file__).parent.parent
app_dir = root / 'app'
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))
