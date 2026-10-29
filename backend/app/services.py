"""Data resolution: live CampX vs imported JSON, per DATA_SOURCE."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from .campx_client import CampXClient
from .db import connect
from .deps import Auth
from .errors import AppError
from . import normalizers as N
from .sessions import now

KINDS = ("timetable", "attendance", "profile", "subjects")
NORMALIZERS: dict[str, Callable[[Any], Any]] = {
    "timetable": N.normalize_timetable,
    "attendance": N.normalize_attendance,
    "profile": N.normalize_profile,
    "subjects": N.normalize_subjects,
}
PATH_SETTING = {
    "timetable": "campx_timetable_path",
    "attendance": "campx_attendance_path",
    "profile": "campx_profile_path",
    "subjects": "campx_subjects_path",
}
# Live problems that are about *configuration/route/shape*, not about the user's session.
FALLBACK_CODES = {"not_configured", "upstream_not_found", "unsupported_structure"}


@dataclass
class Resolved:
    source: str  # "campx" | "imported" | "none"
    data: Any
    notice: str | None = None


# ------------------------------------------------------------ imported storage
def save_import(auth: Auth, kind: str, normalized: Any) -> float:
    t = now()
    with connect(auth.settings.database_file) as c:
        c.execute(
            "INSERT INTO imports (user_key, kind, payload, imported_at) VALUES (?,?,?,?) "
            "ON CONFLICT(user_key, kind) DO UPDATE SET payload=excluded.payload, imported_at=excluded.imported_at",
            (auth.session.user_key, kind, json.dumps(normalized), t),
        )
    return t


def load_import(auth: Auth, kind: str) -> Any | None:
    with connect(auth.settings.database_file) as c:
        row = c.execute(
            "SELECT payload FROM imports WHERE user_key = ? AND kind = ?", (auth.session.user_key, kind)
        ).fetchone()
    if not row:
        return None
    data = json.loads(row["payload"])
    if kind == "timetable" and isinstance(data, list):
        data = N.dedupe_entries(data)  # imports saved before dedup existed may still hold repeats
    return data


def list_imports(auth: Auth) -> dict[str, float]:
    with connect(auth.settings.database_file) as c:
        rows = c.execute("SELECT kind, imported_at FROM imports WHERE user_key = ?", (auth.session.user_key,)).fetchall()
    return {r["kind"]: r["imported_at"] for r in rows}


def delete_import(auth: Auth, kind: str) -> bool:
    with connect(auth.settings.database_file) as c:
        return c.execute("DELETE FROM imports WHERE user_key = ? AND kind = ?", (auth.session.user_key, kind)).rowcount > 0


# ------------------------------------------------------------------- live data
def fetch_live(auth: Auth, kind: str) -> Any:
    path = getattr(auth.settings, PATH_SETTING[kind]).strip()
    if not path:
        raise AppError(
            503,
            "not_configured",
            f"Live CampX {kind} is not configured. Set {PATH_SETTING[kind].upper()} in .env "
            "(see steps_for_chatgpt.md section 11) or import JSON in Settings.",
        )
    try:
        raw = CampXClient(auth.settings).get_json(path, auth.session.campx)
    except AppError as exc:
        if exc.code == "campx_session_expired":
            auth.store.delete(auth.sid)  # our session is useless without a valid CampX session
        raise
    return NORMALIZERS[kind](raw)


def resolve(auth: Auth, kind: str) -> Resolved:
    mode = auth.settings.data_source
    if mode == "campx":
        return Resolved("campx", fetch_live(auth, kind))
    if mode == "imported":
        data = load_import(auth, kind)
        if data is None:
            return Resolved("none", None, f"No imported {kind} yet. Import a JSON file in Settings.")
        return Resolved("imported", data)
    # auto
    try:
        return Resolved("campx", fetch_live(auth, kind))
    except AppError as exc:
        if exc.code not in FALLBACK_CODES:
            raise
        data = load_import(auth, kind)
        if data is not None:
            return Resolved("imported", data, f"Showing imported data because live CampX {kind} is unavailable ({exc.code}).")
        if exc.code == "not_configured":
            return Resolved("none", None, f"Live {kind} is not configured and nothing has been imported. See Settings.")
        raise


# --------------------------------------------------------------------- derived
def derive_subjects(auth: Auth) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    def add(code, name, faculty=None):
        key = (code or name or "").strip().lower()
        if not key:
            return
        cur = merged.setdefault(key, {"subject_code": code, "subject_name": name, "faculty": faculty, "credits": None, "category": None, "semester": None})
        cur["subject_code"] = cur["subject_code"] or code
        cur["subject_name"] = cur["subject_name"] or name
        cur["faculty"] = cur["faculty"] or faculty

    for kind in ("timetable", "attendance"):
        try:
            r = resolve(auth, kind)
        except AppError as exc:
            if exc.status == 401:
                raise
            continue
        if r.data is None:
            continue
        for item in r.data:
            if kind == "timetable" and item["kind"] != "class":
                continue
            add(item.get("subject_code"), item.get("subject_name"), item.get("faculty"))
    return list(merged.values())


# ----------------------------------------------------------- dated sessions
# Internal kind (no public import route): the dated session list behind the weekly timetable.
SESSIONS_KIND = "timetable_sessions"
from . import session_model as _SM  # noqa: E402

NORMALIZERS[SESSIONS_KIND] = _SM.normalize_sessions
PATH_SETTING[SESSIONS_KIND] = "campx_timetable_path"
