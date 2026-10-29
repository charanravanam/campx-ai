"""Persistence for attendance imports (immutable baselines) and student-managed adjustments."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .db import connect
from .deps import Auth
from .errors import AppError
from .session_model import subject_key
from .sessions import now


def fingerprint(payload: Any) -> str:
    """Stable id of a file's *content* (key order / whitespace independent)."""
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def validate_baseline(records: list[dict[str, Any]]) -> None:
    """Import-time checks beyond normalize_attendance(): duplicate subjects are rejected, never merged."""
    seen: dict[str, int] = {}
    for i, r in enumerate(records, start=1):
        key = subject_key(r.get("subject_code"), r.get("subject_name"))
        if key in seen:
            raise AppError(422, "duplicate_subject", f"Records {seen[key]} and {i} are the same subject. Remove the duplicate and re-import.")
        seen[key] = i


def store_attendance_import(auth: Auth, raw: Any, normalized: list[dict[str, Any]]) -> dict[str, Any]:
    """Idempotent. Same content -> 'unchanged'/'reactivated' (no new baseline). New content -> new active baseline."""
    validate_baseline(normalized)
    fp, uk, t = fingerprint(raw), auth.session.user_key, now()
    with connect(auth.settings.database_file) as c:
        row = c.execute("SELECT id, is_active FROM attendance_imports WHERE user_key=? AND fingerprint=?", (uk, fp)).fetchone()
        if row and row["is_active"]:
            return {"import_id": row["id"], "import_status": "unchanged", "fingerprint": fp}
        c.execute("UPDATE attendance_imports SET is_active=0 WHERE user_key=? AND is_active=1", (uk,))
        if row:
            c.execute("UPDATE attendance_imports SET is_active=1 WHERE id=?", (row["id"],))
            return {"import_id": row["id"], "import_status": "reactivated", "fingerprint": fp}
        cur = c.execute(
            "INSERT INTO attendance_imports (user_key, fingerprint, raw_payload, normalized, created_at, is_active) VALUES (?,?,?,?,?,1)",
            (uk, fp, json.dumps(raw, ensure_ascii=False), json.dumps(normalized), t),
        )
        return {"import_id": cur.lastrowid, "import_status": "created", "fingerprint": fp}


def active_import(auth: Auth) -> dict[str, Any] | None:
    with connect(auth.settings.database_file) as c:
        r = c.execute(
            "SELECT id, fingerprint, normalized, created_at FROM attendance_imports WHERE user_key=? AND is_active=1", (auth.session.user_key,)
        ).fetchone()
    return None if r is None else {"id": r["id"], "fingerprint": r["fingerprint"], "records": json.loads(r["normalized"]), "created_at": r["created_at"]}


def delete_attendance_imports(auth: Auth) -> bool:
    with connect(auth.settings.database_file) as c:  # adjustments go with it (ON DELETE CASCADE)
        return c.execute("DELETE FROM attendance_imports WHERE user_key=?", (auth.session.user_key,)).rowcount > 0


def list_adjustments(auth: Auth, import_id: int) -> dict[str, dict[str, Any]]:
    with connect(auth.settings.database_file) as c:
        rows = c.execute(
            "SELECT subject_key, session_key, status, updated_at FROM attendance_adjustments WHERE user_key=? AND import_id=?",
            (auth.session.user_key, import_id),
        ).fetchall()
    return {r["session_key"]: dict(r) for r in rows}


def set_adjustment(auth: Auth, import_id: int, subj: str, session_key: str, status: str) -> None:
    t = now()
    with connect(auth.settings.database_file) as c:  # upsert: repeats and Present<->Absent flips never double count
        c.execute(
            "INSERT INTO attendance_adjustments (user_key, import_id, subject_key, session_key, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(user_key, import_id, session_key) DO UPDATE SET status=excluded.status, subject_key=excluded.subject_key, updated_at=excluded.updated_at",
            (auth.session.user_key, import_id, subj, session_key, status, t, t),
        )


def clear_adjustments(auth: Auth, import_id: int, session_key: str | None = None, subj: str | None = None) -> int:
    sql, args = "DELETE FROM attendance_adjustments WHERE user_key=? AND import_id=?", [auth.session.user_key, import_id]
    if session_key:
        sql += " AND session_key=?"; args.append(session_key)
    if subj:
        sql += " AND subject_key=?"; args.append(subj)
    with connect(auth.settings.database_file) as c:
        return c.execute(sql, args).rowcount
