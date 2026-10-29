from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from app.errors import AppError
from app.services import FALLBACK_CODES
from fastapi import APIRouter, Depends, Query

from ..calculations import DEFAULT_TARGET, build_attendance
from ..deps import Auth, require_session
from ..services import derive_subjects, fetch_live, resolve
from ..timetable_logic import today_view

router = APIRouter(prefix="/api", tags=["data"])


def _now(tz_name: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(tz_name))
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone()


def _filter_timetable_by_student_semester(auth: Auth, entries: list[dict]) -> list[dict]:
    try:
        profile = resolve(auth, "profile").data or {}
    except AppError as exc:
        if exc.code in FALLBACK_CODES:
            return entries
        raise

    student_semester = profile.get("semester")
    if student_semester is None or not str(student_semester).strip():
        return entries

    labelled = [entry for entry in entries if entry.get("semester") is not None]
    if not labelled:
        return entries

    target = str(student_semester).strip().casefold()
    return [
        entry for entry in entries
        if entry.get("semester") is None
        or str(entry["semester"]).strip().casefold() == target
    ]

# --- live-only passthroughs (normalised; the raw upstream body is never returned)
@router.get("/campx/profile")
def campx_profile(auth: Auth = Depends(require_session)):
    return {"source": "campx", "profile": fetch_live(auth, "profile")}


@router.get("/campx/timetable")
def campx_timetable(auth: Auth = Depends(require_session)):
    entries = fetch_live(auth, "timetable")
    entries = _filter_timetable_by_student_semester(auth, entries)
    return {"source": "campx", "entries": entries}


# --- source-aware endpoints (DATA_SOURCE decides)
@router.get("/profile")
def profile(auth: Auth = Depends(require_session)):
    r = resolve(auth, "profile")
    return {"source": r.source, "notice": r.notice, "profile": r.data}


@router.get("/timetable")
def timetable(auth: Auth = Depends(require_session)):
    r = resolve(auth, "timetable")
    entries = _filter_timetable_by_student_semester(auth, r.data or [])
    return {
        "source": r.source,
        "notice": r.notice,
        "entries": entries,
    }


@router.get("/timetable/today")
def timetable_today(auth: Auth = Depends(require_session)):
    r = resolve(auth, "timetable")
    entries = _filter_timetable_by_student_semester(auth, r.data or [])
    view = today_view(entries, _now(auth.settings.app_timezone))
    return {"source": r.source, "notice": r.notice, **view}



@router.get("/attendance")
def attendance(target: int = Query(DEFAULT_TARGET, ge=1, le=100), auth: Auth = Depends(require_session)):
    r = resolve(auth, "attendance")
    built = build_attendance(r.data or [], target)
    return {"source": r.source, "notice": r.notice, **built}


@router.get("/subjects")
def subjects(auth: Auth = Depends(require_session)):
    r = resolve(auth, "subjects")
    if r.data is not None:
        return {"source": r.source, "notice": r.notice, "derived": False, "subjects": r.data}
    derived = derive_subjects(auth)
    if derived:
        return {
            "source": "derived",
            "notice": "Subjects were derived from your timetable/attendance because no subject list is available.",
            "derived": True,
            "subjects": derived,
        }
    return {"source": "none", "notice": r.notice, "derived": False, "subjects": []}
