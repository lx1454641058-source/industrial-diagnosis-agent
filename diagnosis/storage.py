"""Original SQLite evidence store; all query values use parameter binding."""
import json
from pathlib import Path
import sqlite3
import threading
import time


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS samples (
                    id INTEGER PRIMARY KEY, ts REAL NOT NULL, source TEXT NOT NULL,
                    ok INTEGER NOT NULL, temperature REAL, humidity REAL,
                    code TEXT NOT NULL, detail TEXT NOT NULL, raw TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS samples_time ON samples(ts);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, started REAL NOT NULL, provider TEXT NOT NULL,
                    source TEXT NOT NULL, question TEXT NOT NULL, result TEXT NOT NULL);
            ''')

    def sample(self, source, ok, data=None, code='ok', detail='', raw='', ts=None):
        data = data or {}
        with self.lock, self.db:
            cur = self.db.execute('INSERT INTO samples(ts,source,ok,temperature,humidity,code,detail,raw) VALUES(?,?,?,?,?,?,?,?)',
                (time.time() if ts is None else ts, source, int(ok), data.get('temperature'),
                 data.get('humidity'), code, detail[:500], raw[:256]))
            return cur.lastrowid

    def event(self, kind, detail):
        with self.lock, self.db:
            self.db.execute('INSERT INTO events(ts,kind,detail) VALUES(?,?,?)', (time.time(), kind, detail[:500]))

    def samples(self, limit=80, since=0):
        with self.lock:
            return [dict(r) for r in self.db.execute(
                'SELECT * FROM samples WHERE ts>=? ORDER BY id DESC LIMIT ?', (since, min(limit, 500)))]

    def latest_success(self):
        with self.lock:
            row = self.db.execute('SELECT * FROM samples WHERE ok=1 ORDER BY id DESC LIMIT 1').fetchone()
            return dict(row) if row else None

    def events(self, limit=20):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (min(limit, 100),))]

    def save_session(self, result):
        with self.lock, self.db:
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)',
                (result['id'], result['started'], result['provider'], result['source'],
                 result['question'], json.dumps(result, ensure_ascii=False)))

    def sessions(self, limit=20):
        with self.lock:
            return [json.loads(r['result']) for r in self.db.execute(
                'SELECT result FROM sessions ORDER BY started DESC LIMIT ?', (min(limit, 100),))]

    def close(self):
        with self.lock:
            self.db.close()
