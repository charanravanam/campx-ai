"""Server-side website sessions (one per logged-in student).

The browser only ever holds a random session id in an HttpOnly cookie. The
upstream CampX token/cookies live encrypted in SQLite, keyed by the SHA-256
hash of that id.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .db import connect
from .security import Crypto, hash_session_id, new_session_id


def now() -> float:
    """Indirection so tests can fake the clock."""
    return time.time()


@dataclass
class SessionData:
    user_key: str
    login_hint: str
    tenant: str
    created_at: float
    expires_at: float
    campx: dict[str, Any] = field(repr=False, default_factory=dict)  # never serialise to clients


class SessionStore:
    def __init__(self, db_path: Path, crypto: Crypto, max_per_user: int = 5):
        self.db_path = db_path
        self.crypto = crypto
        self.max_per_user = max_per_user

    def create(
        self,
        *,
        user_key: str,
        login_hint: str,
        tenant: str,
        campx_state: dict[str, Any],
        ttl_seconds: float,
        hard_expiry: float | None = None,
    ) -> tuple[str, float]:
        sid = new_session_id()
        t = now()
        expires = t + ttl_seconds
        if hard_expiry is not None:
            expires = min(expires, hard_expiry)
        with connect(self.db_path) as c:
            c.execute(
                "INSERT INTO sessions (id_hash, user_key, login_hint, tenant, created_at, expires_at, last_seen, campx_blob)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (hash_session_id(sid), user_key, login_hint, tenant, t, expires, t, self.crypto.encrypt_json(campx_state)),
            )
            # keep only the newest N sessions per user
            c.execute(
                "DELETE FROM sessions WHERE user_key = ? AND id_hash NOT IN ("
                " SELECT id_hash FROM sessions WHERE user_key = ? ORDER BY created_at DESC LIMIT ?)",
                (user_key, user_key, self.max_per_user),
            )
        return sid, expires

    def get(self, session_id: str | None) -> SessionData | None:
        if not session_id or len(session_id) > 200:
            return None
        h = hash_session_id(session_id)
        with connect(self.db_path) as c:
            row = c.execute("SELECT * FROM sessions WHERE id_hash = ?", (h,)).fetchone()
            if row is None:
                return None
            t = now()
            if row["expires_at"] <= t:
                c.execute("DELETE FROM sessions WHERE id_hash = ?", (h,))
                return None
            blob = self.crypto.decrypt_json(row["campx_blob"])
            if blob is None:  # secret changed or data corrupted -> treat as logged out
                c.execute("DELETE FROM sessions WHERE id_hash = ?", (h,))
                return None
            c.execute("UPDATE sessions SET last_seen = ? WHERE id_hash = ?", (t, h))
            return _to_data(row, blob)

    def delete(self, session_id: str | None) -> None:
        if not session_id:
            return
        with connect(self.db_path) as c:
            c.execute("DELETE FROM sessions WHERE id_hash = ?", (hash_session_id(session_id),))

    def delete_user(self, user_key: str) -> int:
        with connect(self.db_path) as c:
            return c.execute("DELETE FROM sessions WHERE user_key = ?", (user_key,)).rowcount

    def purge_expired(self) -> int:
        with connect(self.db_path) as c:
            return c.execute("DELETE FROM sessions WHERE expires_at <= ?", (now(),)).rowcount

    def count_active(self) -> int:
        with connect(self.db_path) as c:
            return c.execute("SELECT COUNT(*) FROM sessions WHERE expires_at > ?", (now(),)).fetchone()[0]


def _to_data(row: sqlite3.Row, blob: dict[str, Any]) -> SessionData:
    return SessionData(
        user_key=row["user_key"],
        login_hint=row["login_hint"] or "",
        tenant=row["tenant"] or "",
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        campx=blob,
    )
