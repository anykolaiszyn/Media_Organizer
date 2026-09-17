import sqlite3
import tempfile
import os
import json

class BatchResultsDB:
    def __init__(self, db_path=None):
        if db_path is None:
            temp_dir = tempfile.gettempdir()
            db_path = os.path.join(temp_dir, f"media_organizer_batch_{os.getpid()}.sqlite3")
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        c.execute("DROP TABLE IF EXISTS results")
        c.execute("""
            CREATE TABLE results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                action TEXT,
                status TEXT,
                metadata TEXT,
                error TEXT
            )
        """)
        self.conn.commit()

    def insert_result(self, filename, action, status, metadata, error=None):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO results (filename, action, status, metadata, error) VALUES (?, ?, ?, ?, ?)",
            (filename, action, status, json.dumps(metadata), error)
        )
        self.conn.commit()

    def fetch_results(self, limit=100, offset=0):
        c = self.conn.cursor()
        c.execute("SELECT filename, action, status, metadata, error FROM results LIMIT ? OFFSET ?", (limit, offset))
        return c.fetchall()

    def count_results(self):
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) FROM results")
        return c.fetchone()[0]

    def clear(self):
        c = self.conn.cursor()
        c.execute("DELETE FROM results")
        self.conn.commit()

    def close(self):
        if hasattr(self, 'conn') and self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
        # Wait a moment for Windows to release the file lock
        import time
        for _ in range(10):
            try:
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)
                break
            except PermissionError:
                time.sleep(0.05)

    @staticmethod
    def cleanup_old_temp_dbs():
        temp_dir = tempfile.gettempdir()
        for fname in os.listdir(temp_dir):
            if fname.startswith("media_organizer_batch_") and fname.endswith(".sqlite3"):
                try:
                    os.remove(os.path.join(temp_dir, fname))
                except Exception:
                    pass
