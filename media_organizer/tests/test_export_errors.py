import pytest
from media_organizer.app.batch_results_db import BatchResultsDB
import csv
import io
import time

def test_export_errors_csv():
    db = BatchResultsDB()
    try:
        db.insert_result('file1.jpg', 'copy', 'done', {}, error=None)
        db.insert_result('file2.jpg', 'copy', 'error', {}, error='Failed')
        db.insert_result('file3.jpg', 'move', 'done', {}, error=None)
        db.insert_result('file4.jpg', 'move', 'error', {}, error='Oops')
        # Simulate export logic
        all_rows = []
        offset = 0
        page_size = 2
        while True:
            rows = db.fetch_results(limit=page_size, offset=offset)
            if not rows:
                break
            all_rows.extend(rows)
            offset += page_size
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['filename','action','status','error'])
        for row in all_rows:
            filename, action, status, metadata, error = row
            if error or status == 'error':
                writer.writerow([filename, action, status, error or ''])
        csv_content = output.getvalue()
        assert 'file2.jpg' in csv_content
        assert 'Failed' in csv_content
        assert 'file4.jpg' in csv_content
        assert 'Oops' in csv_content
        assert 'file1.jpg' not in csv_content  # not an error
    finally:
        # Ensure all connections are closed before removing file
        db.conn.close()
        time.sleep(0.1)  # Give Windows a moment to release the file lock
        db.close()
