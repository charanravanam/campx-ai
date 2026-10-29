"""SQLite helpers. All queries elsewhere use parameter binding (never f-strings)."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id_hash     TEXT PRIMARY KEY,
    user_key    TEXT NOT NULL,
    login_hint  TEXT,
    tenant      TEXT,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    campx_blob  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_key);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS imports (
    user_key     TEXT NOT NULL,
    kind         TEXT NOT NULL,
    payload      TEXT NOT NULL,
    imported_at  REAL NOT NULL,
    PRIMARY KEY (user_key, kind)
);

-- Attendance forecasting (additive; created with IF NOT EXISTS so old local databases upgrade in place).
-- One row per distinct imported file (identified by fingerprint). raw_payload is the untouched original;
-- normalized is the validated baseline. Rows are never mutated by simulations.
CREATE TABLE IF NOT EXISTS attendance_imports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key     TEXT NOT NULL,
    fingerprint  TEXT NOT NULL,
    raw_payload  TEXT NOT NULL,
    normalized   TEXT NOT NULL,
    created_at   REAL NOT NULL,
    is_active    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_key, fingerprint)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_att_imports_one_active ON attendance_imports(user_key) WHERE is_active = 1;

-- Student-managed Present/Absent outcomes for upcoming sessions, bound to one import version.
CREATE TABLE IF NOT EXISTS attendance_adjustments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key     TEXT NOT NULL,
    import_id    INTEGER NOT NULL REFERENCES attendance_imports(id) ON DELETE CASCADE,
    subject_key  TEXT NOT NULL,
    session_key  TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('present','absent')),
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    UNIQUE (user_key, import_id, session_key)
);
CREATE INDEX IF NOT EXISTS idx_att_adj_user ON attendance_adjustments(user_key, import_id);
"""


def init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
    try:
        os.chmod(path, 0o600)  # best effort; ignored on Windows
    except OSError:
        pass


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
