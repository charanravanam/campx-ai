"""Turn unknown-ish JSON (live CampX or imported) into our fixed shapes.

Rules:
* Only KNOWN structures are accepted. Anything else raises
  AppError(422, "unsupported_structure") - we never guess or fabricate.
* Field aliases (e.g. startTime / start_time / from) are an *assumption* about
  what CampX may call things. They are UNVERIFIED against real CampX payloads.
  Use `docs/` + steps_for_chatgpt.md section 11 to confirm with a redacted sample.
"""
from __future__ import annotations

import re
from typing import Any

from .errors import AppError

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_DAY_LOOKUP = {d.lower(): d for d in DAYS} | {d[:3].lower(): d for d in DAYS} | {"tues": "Tuesday", "thur": "Thursday", "thurs": "Thursday", "weds": "Wednesday"}
MAX_ENTRIES = 2000


def unsupported(what: str, detail: str = "") -> AppError:
    msg = f"Unrecognised {what} structure."
    if detail:
        msg += f" {detail}"
    return AppError(422, "unsupported_structure", msg)


# --------------------------------------------------------------------- helpers
def pick(d: dict, *names: str) -> Any:
    for n in names:
        v = d.get(n)
        if v not in (None, "", [], {}):
            return v
    lower = {k.lower(): v for k, v in d.items() if isinstance(k, str)}
    for n in names:
        v = lower.get(n.lower())
        if v not in (None, "", [], {}):
            return v
    return None


def text(v: Any, *name_keys: str) -> str | None:
    """Best-effort short string from a str / number / {name:..} / [..] value."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        s = " ".join(v.split())
        return s[:200] or None
    if isinstance(v, dict):
        inner = pick(v, *(name_keys or ("name", "title", "label", "fullName", "displayName")))
        return text(inner) if inner is not None and not isinstance(inner, dict) else None
    if isinstance(v, list):
        parts = [p for p in (text(x, *name_keys) for x in v) if p]
        return ", ".join(parts)[:200] or None
    return None


def day_from(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 1 <= value <= 7:  # 1=Monday ... 7=Sunday
        return DAYS[value - 1]
    if isinstance(value, str):
        key = value.strip().lower().rstrip(".")
        if key.isdigit() and 1 <= int(key) <= 7:
            return DAYS[int(key) - 1]
        return _DAY_LOOKUP.get(key)
    return None


_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})(?::\d{2}(?:\.\d+)?)?\s*([AaPp][Mm])?\s*$")


def parse_time(value: Any) -> str | None:
    """-> 'HH:MM' (24h) or None. Accepts 9:00, 09:00:00, 9:00 AM, ISO datetimes."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    if "T" in s and len(s) >= 16:  # 2024-01-01T09:30:00(Z)
        s = s.split("T", 1)[1]
        s = re.split(r"[Zz+\-]", s, maxsplit=1)[0]
    m = _TIME_RE.match(s)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap:
        ap = ap.lower()
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if ap == "pm" else 0)
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def unwrap(payload: Any, keys: tuple[str, ...], depth: int = 0) -> Any:
    """Descend through known container keys: {"data": {"items": [...]}} -> [...]."""
    if depth > 4 or not isinstance(payload, dict):
        return payload
    for k in keys:
        v = pick(payload, k)
        if isinstance(v, (list, dict)):
            return unwrap(v, keys, depth + 1)
    return payload


def _int_or_none(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and re.fullmatch(r"\s*\d+\s*", v):
        return int(v)
    return None


# ------------------------------------------------------------------- timetable
_START = ("startTime", "start_time", "start", "from", "fromTime", "beginTime", "periodStart")
_END = ("endTime", "end_time", "end", "to", "toTime", "finishTime", "periodEnd")
_SUBJECT = ("subject", "subjectName", "subject_name", "course", "courseName", "title", "subjectTitle")
_CODE = ("subjectCode", "subject_code", "courseCode", "course_code", "code")
_FACULTY = ("faculty", "faculties", "facultyName", "faculty_name", "teacher", "teacherName", "instructor", "employeeName", "staff")
_ROOM = ("room", "roomNo", "room_no", "roomNumber", "classRoom", "classroom", "venue", "location")
_DAY = ("day", "dayOfWeek", "day_of_week", "weekday", "dayName", "weekDay")
_TT_CONTAINERS = ("entries", "timetable", "timetables", "classroomTimetables", "classroomTimetable", "data", "items", "results", "result", "content", "rows", "schedule")
_NESTED = ("periods", "slots", "classes", "sessions", "entries", "lectures", "schedule", "items")
_BREAK_WORDS = re.compile(r"\b(break|lunch|recess|interval)\b", re.I)


def _is_period(d: dict) -> bool:
    return pick(d, *_START) is not None or pick(d, *_SUBJECT) is not None



def _walk(
    node: Any,
    day: str | None,
    depth: int,
    out: list[tuple[str | None, dict, str | None]],
    semester: str | None = None,
) -> None:
    if depth > 6:
        raise unsupported("timetable", "Nesting is too deep.")

    if isinstance(node, list):
        for item in node:
            if not isinstance(item, dict):
                raise unsupported("timetable", "Expected a list of objects.")
            _walk(item, day, depth + 1, out, semester)
        return

    if not isinstance(node, dict):
        raise unsupported("timetable")

    own_semester = (
        text(pick(node, "semNo", "semester", "semesterNo",
                  "semesterNumber", "currentSemester"))
        or semester
    )

    slot = pick(node, "timetableSlot")
    own_day = (
        day_from(pick(node, *_DAY))
        or (day_from(pick(slot, *_DAY)) if isinstance(slot, dict) else None)
        or day
    )

    nested = next(
        (pick(node, k) for k in _NESTED
         if isinstance(pick(node, k), (list, dict))),
        None,
    )

    if _is_period(node) and not (
        nested is not None and pick(node, *_START) is None
    ):
        out.append((own_day, node, own_semester))
        return

    if nested is not None and own_day:
        _walk(nested, own_day, depth + 1, out, own_semester)
        return

    weekday_keys = [
        k for k in node
        if isinstance(k, str) and day_from(k)
        and isinstance(node[k], (list, dict))
    ]
    if weekday_keys:
        for k in weekday_keys:
            _walk(node[k], day_from(k), depth + 1, out, own_semester)
        return

    for k in _TT_CONTAINERS:
        value = pick(node, k)
        if isinstance(value, (list, dict)):
            _walk(value, own_day, depth + 1, out, own_semester)
            return

    raise unsupported(
        "timetable",
        "Expected periods, weekday keys or a known container such as 'entries'.",
    )




def normalize_timetable(payload: Any) -> list[dict[str, Any]]:
    raw: list[tuple[str | None, dict, str | None]] = []
    _walk(payload, None, 0, raw)

    if len(raw) > MAX_ENTRIES:
        raise AppError(
            422,
            "too_many_entries",
            f"Timetable has more than {MAX_ENTRIES} entries.",
        )

    entries: list[dict[str, Any]] = []

    for i, (day, d, inherited_semester) in enumerate(raw, start=1):
        if day is None:
            raise unsupported(
                "timetable",
                f"Entry {i} has no recognisable day (use Monday..Sunday).",
            )

        name = text(pick(d, *_SUBJECT), "subjectName", "name", "title")

        subject = pick(d, "subject")
        code = text(pick(d, *_CODE)) or (
            text(pick(subject, "code", "subjectCode"))
            if isinstance(subject, dict)
            else None
        )

        kind_hint = text(
            pick(d, "type", "kind", "category", "periodType")
        ) or ""

        is_break = bool(
            _BREAK_WORDS.search(kind_hint)
            or (name and _BREAK_WORDS.fullmatch(name.strip()))
        )

        kind = "break" if is_break else (
            "class" if (name or code) else "free"
        )

        entries.append(
            {
                "day": day,
                "start": parse_time(pick(d, *_START)),
                "end": parse_time(pick(d, *_END)),
                "subject_code": code,
                "subject_name": name,
                "faculty": text(
                    pick(d, *_FACULTY),
                    "name",
                    "fullName",
                    "employeeName",
                ),
                "room": text(
                    pick(d, *_ROOM),
                    "name",
                    "roomNo",
                    "number",
                ),
                "kind": kind,
            }
        )

        semester = text(
            pick(
                d,
                "semNo",
                "semester",
                "semesterNo",
                "semesterNumber",
                "currentSemester",
            )
        ) or inherited_semester

        if semester is not None:
            entries[-1]["semester"] = semester

    return dedupe_entries(entries)


def dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse identical weekly slots and sort. Idempotent, so it is safe to re-apply to stored data.

    Dated upstream sessions (one record per calendar date) collapse into ONE weekly slot; entries that
    differ in faculty/room/semester (e.g. parallel lab batches) stay distinct.
    """
    unique: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for entry in entries:
        signature = (
            entry.get("day"), entry.get("start"), entry.get("end"), entry.get("subject_code"),
            entry.get("subject_name"), entry.get("faculty"), entry.get("room"), entry.get("kind"), entry.get("semester"),
        )
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(entry)
    unique.sort(key=lambda e: (DAYS.index(e["day"]), e.get("start") or "99:99", e.get("end") or "99:99"))
    return unique


# --------------------------------------------------------------------- profile
_PROFILE_CONTAINERS = ("data", "profile", "student", "user", "result", "studentProfile", "basicDetails")


def _safe_photo(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    u = url.strip()
    if u.lower().startswith("https://") or (u.lower().startswith("data:image/") and len(u) < 200_000):
        return u
    return None  # drops javascript:, http:, relative paths


def normalize_profile(payload: Any) -> dict[str, Any]:
    node = payload
    if isinstance(node, list) and len(node) == 1:
        node = node[0]

    if not isinstance(node, dict):
        raise unsupported("profile", "Expected a JSON object.")

    # Unwrap legacy response containers, but preserve CampX's
    # root-level student and admission objects together.
    if "student" not in node and "admission" not in node:
        node = unwrap(
            node,
            ("data", "profile", "user", "result", "studentProfile", "basicDetails"),
        )
        if not isinstance(node, dict):
            raise unsupported("profile", "Expected a JSON object.")

    # Keep the full response so student and admission data are both available.
    student = pick(node, "student")
    admission = pick(node, "admission")

    if not isinstance(student, dict):
        student = {}
    if not isinstance(admission, dict):
        admission = {}

    course = pick(admission, "course")
    program = pick(admission, "program")
    if not isinstance(course, dict):
        course = {}
    if not isinstance(program, dict):
        program = {}

    classroom = pick(student, "classroom")
    if not isinstance(classroom, dict):
        classroom = {}

    def get(*names: str) -> Any:
        for source in (student, admission, node, course, program, classroom):
            value = pick(source, *names)
            if value not in (None, "", [], {}):
                return value
        return None

    first = text(get("firstName", "first_name"))
    last = text(get("lastName", "last_name"))
    full = text(get("fullName", "full_name", "name", "studentName", "displayName")) or (
        " ".join(part for part in (first, last) if part) or None
    )

    branch = text(
        pick(student, "branchName", "branch", "branchCode")
    ) or text(
        pick(node, "branchName", "branch", "branchCode")
    ) or text(
        pick(program, "branchName", "branchDisplay", "branchCode")
    ) or text(
        pick(admission, "branchName", "branchCode")
    )

    course_name = text(
        pick(course, "courseName", "displayName", "name")
    ) or text(
        pick(admission, "courseName", "course")
    ) or text(
        pick(program, "program", "programName", "displayName")
    )

    profile = {
        "full_name": full,
        "roll_number": text(get("rollNumber", "rollNo", "roll_number", "roll_no", "registrationNumber", "regNo", "admissionNumber")),
        "email": text(get("email", "emailId", "emailAddress", "mail")),
        "photo_url": _safe_photo(get("photoUrl", "photo_url", "photo", "profilePhoto", "profileImage", "profilePicture", "avatar", "imageUrl")),
        "branch": branch,
        "course": course_name,
        "batch": text(get("batch", "batchName", "admissionYear", "academicYear")),
        "semester": text(get("semester", "currentSemester", "sem", "semesterName", "semNo")),
        "classroom": text(pick(classroom, "name")) or text(
            get("classroomName", "className", "class")
        ),
        "section": text(get("section", "sectionName")),
    }

    if not any(profile.values()):
        raise unsupported("profile", "None of the known profile fields (name, roll number, email, branch...) were found.")

    return profile


def _flatten_records(node: Any, keys: tuple[str, ...], what: str, depth: int = 0) -> list[dict]:
    if depth > 5:
        raise unsupported(what, "Nesting is too deep.")
    if isinstance(node, list):
        if not all(isinstance(x, dict) for x in node):
            raise unsupported(what, "Expected a list of objects.")
        return node
    if isinstance(node, dict):
        for k in keys:
            v = pick(node, k)
            if isinstance(v, (list, dict)):
                return _flatten_records(v, keys, what, depth + 1)
    raise unsupported(what, f"Expected a list or one of the keys: {', '.join(keys[:5])}...")


_ATTENDED = ("attended", "present", "presentCount", "classesAttended", "attendedClasses", "classes_attended", "attendedCount")
_TOTAL = ("total", "conducted", "held", "totalClasses", "numberOfClasses", "classesHeld", "total_classes", "classesConducted", "totalCount")
_ABSENT = ("absent", "absentCount", "classesMissed")
_PCT = ("percentage", "percent", "attendancePercentage", "attendance_percentage", "attendancePercent")
_ATT_CONTAINERS = ("subjects", "attendance", "subjectWise", "subject_wise", "records", "data", "items", "results", "result", "content")

def normalize_attendance(payload: Any) -> list[dict[str, Any]]:
    records = _flatten_records(payload, _ATT_CONTAINERS, "attendance")
    if len(records) > MAX_ENTRIES:
        raise AppError(422, "too_many_entries", f"More than {MAX_ENTRIES} attendance records.")
    out: list[dict[str, Any]] = []
    for i, r in enumerate(records, start=1):
        sub = pick(r, "subject", "subjectName", "subject_name", "course", "courseName", "name", "title")
        name = text(sub, "subjectName", "name", "title")
        code = text(pick(r, "subjectCode", "subject_code", "courseCode", "code")) or (
            text(sub, "code", "subjectCode") if isinstance(sub, dict) else None
        )
        if not (name or code):
            raise unsupported("attendance", f"Record {i} has no subject name or code.")
        attended, total = _int_or_none(pick(r, *_ATTENDED)), _int_or_none(pick(r, *_TOTAL))
        absent = _int_or_none(pick(r, *_ABSENT))
        if attended is None and total is not None and absent is not None:
            attended = total - absent
        pct_raw = pick(r, *_PCT)
        pct = None
        if pct_raw is not None:
            try:
                pct = float(str(pct_raw).strip().rstrip("%"))
            except ValueError:
                raise unsupported("attendance", f"Record {i} has a non-numeric percentage.") from None
            if not 0 <= pct <= 100:
                raise unsupported("attendance", f"Record {i} percentage must be between 0 and 100.")
        if (attended is None) != (total is None):
            raise unsupported("attendance", f"Record {i} needs BOTH attended and total counts (or only a percentage).")
        if attended is not None and total is not None:
            if attended < 0 or total < 0 or attended > total:
                raise unsupported("attendance", f"Record {i} has impossible counts (attended must be 0..total).")
        elif pct is None:
            raise unsupported("attendance", f"Record {i} has neither counts nor a percentage.")
        out.append({"subject_code": code, "subject_name": name, "attended": attended, "total": total, "reported_percentage": pct})
    return out


# -------------------------------------------------------------------- subjects
_SUBJ_CONTAINERS = ("subjects", "courses", "data", "items", "results", "result", "content")


def normalize_subjects(payload: Any) -> list[dict[str, Any]]:
    records = _flatten_records(payload, _SUBJ_CONTAINERS, "subjects")
    if len(records) > MAX_ENTRIES:
        raise AppError(422, "too_many_entries", f"More than {MAX_ENTRIES} subjects.")
    out = []
    for i, r in enumerate(records, start=1):
        name = text(pick(r, "subjectName", "subject_name", "name", "title", "courseName", "subject"), "name", "subjectName")
        code = text(pick(r, "subjectCode", "subject_code", "courseCode", "code"))
        if not (name or code):
            raise unsupported("subjects", f"Subject {i} has no name or code.")
        out.append(
            {
                "subject_code": code,
                "subject_name": name,
                "faculty": text(pick(r, *_FACULTY), "name", "fullName", "employeeName"),
                "credits": text(pick(r, "credits", "credit", "creditPoints")),
                "category": text(pick(r, "type", "category", "subjectType", "kind")),
                "semester": text(pick(r, "semester", "sem", "semesterName")),
            }
        )
    return out
