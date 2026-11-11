"""Jarvis's records: one SQLite file on the server (data/jarvis.db). Backed up nightly (phase 1 backups)."""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

DB_FILE = config.ROOT / "data" / "jarvis.db"
_lock = threading.RLock()  # re-entrant: a tool may read a setting while it holds a connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
  id INTEGER PRIMARY KEY, text TEXT NOT NULL, due_utc TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',            -- pending | fired | done | cancelled
  created_utc TEXT NOT NULL, fired_utc TEXT
);
CREATE TABLE IF NOT EXISTS routines (
  name TEXT PRIMARY KEY, every_days REAL, last_done_utc TEXT, created_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS routine_log (id INTEGER PRIMARY KEY, name TEXT NOT NULL, done_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS water (id INTEGER PRIMARY KEY, ml INTEGER NOT NULL, local_day TEXT NOT NULL, logged_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY, fact TEXT NOT NULL, category TEXT, created_utc TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, text TEXT NOT NULL, tag TEXT, created_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS push_subs (endpoint TEXT PRIMARY KEY, sub_json TEXT NOT NULL, created_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY, ts_utc TEXT NOT NULL, action TEXT NOT NULL, detail TEXT);
"""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    with _lock:
        DB_FILE.parent.mkdir(exist_ok=True)
        c = sqlite3.connect(DB_FILE)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def log(action: str, detail: str = "") -> None:
    with conn() as c:
        c.execute("INSERT INTO activity (ts_utc, action, detail) VALUES (?,?,?)", (now_utc(), action, detail))


def get_setting(key: str, default: str = "") -> str:
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(key: str, value: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, value))
