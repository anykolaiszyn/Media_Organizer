import pytest
import tempfile
import os
from media_organizer.app.batch_results_db import BatchResultsDB

def test_batch_results_db_temp_location():
    db = BatchResultsDB()
    try:
        # The DB path should be in the system temp dir
        temp_dir = tempfile.gettempdir()
        assert db.db_path.startswith(temp_dir), f"DB path {db.db_path} not in temp dir {temp_dir}"
        # Insert and fetch a result
        db.insert_result('file1.jpg', 'copy', 'done', {'meta': 1}, error=None)
        results = db.fetch_results()
        assert len(results) == 1
        assert results[0][0] == 'file1.jpg'
    finally:
        db.close()
        # DB file should be deleted after close
        assert not os.path.exists(db.db_path)

def test_batch_results_db_cleanup():
    # Create a temp DB file manually
    temp_dir = tempfile.gettempdir()
    test_db_path = os.path.join(temp_dir, 'media_organizer_batch_test.sqlite3')
    open(test_db_path, 'w').close()
    assert os.path.exists(test_db_path)
    # Run cleanup
    BatchResultsDB.cleanup_old_temp_dbs()
    assert not os.path.exists(test_db_path)
