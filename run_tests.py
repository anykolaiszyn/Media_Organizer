# Test runner for Media Organizer
# Ensures the project root is on sys.path so 'media_organizer' is importable
import sys
import os
import pytest

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

pytest.main()
