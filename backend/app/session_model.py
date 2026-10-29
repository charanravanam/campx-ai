"""Dated attendance sessions, as opposed to the weekly recurring view in normalize_timetable().

Evidence (redacted structural analysis of a real CampX response): the timetable endpoint returns
one record per dated session with a unique ``id``, ``sessionDate``, ``orderNumber``, times, a nested
subject (with ``subjectType.type`` Theory/Lab), ``groups`` (lab batches) and ``periods``.
Some lab records span two periods (``periods: [5, 6]``) but appear as ONE record.

Nothing here guesses what the institution counts as one "class". Each session carries
``period_count`` so the caller can choose a documented counting model.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from .errors import AppError
from .normalizers import MAX_ENTRIES, _TT_CONTAINERS, parse_time, pick, text, unsupported

_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def subject_key(code: str | None, name: str | None) -> str:
    return (code or name or "").strip().lower()


def _iso_date(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    m = _DATE.match(v.strip())
    if not m:
        return None
    try:
        dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None
    return m.group(1)


def _records(payload: Any, depth: int = 0) -> list[dict]:
    if depth > 4:
        raise unsupported("sessions", "Nesting is too deep.")
    if isinstance(payload, list):
        if not all(isinstance(x, dict) for x in payload):
            raise unsupported("sessions", "Expected a list of objects.")
        return payload
    if isinstance(payload, dict):
        for k in _TT_CONTAINERS:
            v = pick(payload, k)
            if isinstance(v, (list, dict)):
                return _records(v, depth + 1)
    raise unsupported("sessions", "Expected a list of dated session records.")


def normalize_sessions(payload: Any) -> list[dict[str, Any]]:
    """-> dated sessions, de-duplicated by upstream id (or by a documented semantic key if no id).

    Raises unsupported_structure when the payload has no ``sessionDate`` (a plain weekly timetable).
    """
    recs = _records(payload)
    if len(recs) > MAX_ENTRIES * 4:
        raise AppError(422, "too_many_entries", "Too many session records.")
    out: dict[str, dict[str, Any]] = {}
    for i, r in enumerate(recs, start=1):
        date = _iso_date(pick(r, "sessionDate", "date"))
        if date is None:
            raise unsupported("sessions", f"Record {i} has no valid sessionDate (YYYY-MM-DD).")
        subj = pick(r, "subject")
        sdict = subj if isinstance(subj, dict) else {}
        name = text(pick(sdict, "name", "subjectName")) or text(pick(r, "subjectName", "subject_name"))
        code = text(pick(sdict, "subjectCode", "code")) or text(pick(r, "subjectCode", "subject_code"))
        if not (name or code):
            raise unsupported("sessions", f"Record {i} has no subject.")
        stype = pick(sdict, "subjectType")
        type_name = (text(pick(stype, "type")) if isinstance(stype, dict) else None) or ""
        has_att = stype.get("hasAttendance") if isinstance(stype, dict) else None
        kind = "lab" if type_name.lower().startswith("lab") else "theory" if type_name else "other"
        periods = pick(r, "periods")
        period_count = len(periods) if isinstance(periods, list) and periods else 1
        groups = [g for g in (text(pick(g, "name")) if isinstance(g, dict) else None for g in (pick(r, "groups") or [])) if g]
        order = pick(r, "orderNumber")
        start, end = parse_time(pick(r, "fromTime", "startTime")), parse_time(pick(r, "toTime", "endTime"))
        sa = pick(r, "studentAttendance")
        flag = sa.get("status") if isinstance(sa, dict) and isinstance(sa.get("status"), bool) else None
        up_id = pick(r, "id")
        skey = subject_key(code, name)
        if isinstance(up_id, (int, str)) and not isinstance(up_id, bool):
            session_key = f"id:{up_id}"
        else:  # documented fallback when no stable id exists
            session_key = f"k:{date}|{order}|{start}|{end}|{skey}|{','.join(sorted(groups))}"
        if session_key in out:
            continue  # same upstream session repeated -> keep one
        out[session_key] = {
            "session_key": session_key,
            "date": date,
            "order": order if isinstance(order, int) and not isinstance(order, bool) else None,
            "start": start,
            "end": end,
            "subject_key": skey,
            "subject_code": code,
            "subject_name": name,
            "kind": kind,
            "counts_for_attendance": has_att if isinstance(has_att, bool) else None,
            "period_count": period_count,
            "groups": groups,
            "completed": bool(pick(r, "completed")) if pick(r, "completed") is not None else None,
            "suspended": bool(r.get("isSuspended")),
            # RAW upstream flag from studentAttendance.status. Its meaning (present vs absent) is UNVERIFIED.
            "recorded_flag": flag,
        }
    return sorted(out.values(), key=lambda s: (s["date"], s["start"] or "", s["session_key"]))
