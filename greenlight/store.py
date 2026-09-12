"""Caching what we fetch, so a second look at a niche is free.

A niche of three hundred games is six hundred HTTP requests at roughly a second
and a half each - about fifteen minutes. Cached, the same run is instant, which
is the difference between a tool you re-run while thinking and one you run once
and never again.
"""

import json
import os
import sqlite3
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "greenlight.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (
    url        TEXT PRIMARY KEY,
    fetched_at REAL NOT NULL,
    payload    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at   TEXT NOT NULL,
    niche    TEXT,
    apps     INTEGER
);
"""


class Cache:

    def __init__(self, path=None):
        path = path or DB_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def get(self, url, max_age):
        row = self.conn.execute(
            "SELECT fetched_at, payload FROM http_cache WHERE url = ?",
            (url,)).fetchone()
        if row is None:
            return None
        if max_age is not None and (time.time() - row["fetched_at"]) > max_age:
            return None
        try:
            return json.loads(row["payload"])
        except ValueError:
            return None

    def put(self, url, payload):
        self.conn.execute(
            "INSERT OR REPLACE INTO http_cache (url, fetched_at, payload)"
            " VALUES (?,?,?)", (url, time.time(), json.dumps(payload)))
        self.conn.commit()

    def forget(self, url):
        """Drop an entry - used when a response turns out to be junk."""
        self.conn.execute("DELETE FROM http_cache WHERE url = ?", (url,))
        self.conn.commit()

    def stats(self):
        row = self.conn.execute(
            "SELECT COUNT(*) n, MIN(fetched_at) oldest FROM http_cache").fetchone()
        return {"entries": row["n"], "oldest": row["oldest"]}

    def close(self):
        self.conn.close()
