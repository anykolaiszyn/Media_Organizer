import pytest
from media_organizer.app.batch_results_db import BatchResultsDB

def test_batch_results_db_pagination():
    db = BatchResultsDB()
    try:
        # Insert 250 results
        for i in range(250):
            db.insert_result(f'file{i}.jpg', 'copy', 'done', {'meta': i}, error=None)
        # Fetch first page (default 100)
        page1 = db.fetch_results(limit=100, offset=0)
        assert len(page1) == 100
        assert page1[0][0] == 'file0.jpg'
        assert page1[-1][0] == 'file99.jpg'
        # Fetch second page
        page2 = db.fetch_results(limit=100, offset=100)
        assert len(page2) == 100
        assert page2[0][0] == 'file100.jpg'
        # Fetch last page (should be 50)
        page3 = db.fetch_results(limit=100, offset=200)
        assert len(page3) == 50
        assert page3[0][0] == 'file200.jpg'
        # Fetch out of bounds
        page4 = db.fetch_results(limit=100, offset=300)
        assert len(page4) == 0
    finally:
        db.close()
