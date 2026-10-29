"""Regression tests for repeated timetable sessions (synthetic data)."""
import json
import sqlite3

from conftest import csrf_headers
from app.normalizers import normalize_timetable
from app.services import SESSIONS_KIND


def rec(i, date, day, frm, to, name, code="S1", faculty="Dr F", sem=3, **kw):
    r = {"id": i, "sessionDate": date, "orderNumber": 1, "fromTime": frm, "toTime": to, "semNo": sem,
         "subject": {"name": name, "subjectCode": code}, "faculties": [{"fullName": faculty}],
         "timetableSlot": {"day": day, "fromTime": frm, "toTime": to}}
    r.update(kw)
    return r


def test_dated_sessions_collapse_to_one_weekly_slot():
    rows = [rec(i, f"2026-07-{6 + 7 * i:02d}", "MONDAY", "09:00:00", "10:00:00", "Mechanics") for i in range(3)]
    out = normalize_timetable(rows)
    assert len(out) == 1 and out[0]["day"] == "Monday" and out[0]["start"] == "09:00"


def test_parallel_lab_batches_stay_distinct():
    rows = [rec(1, "2026-07-06", "MONDAY", "14:00:00", "16:00:00", "Lab", "L1", faculty="Dr A"),
            rec(2, "2026-07-06", "MONDAY", "14:00:00", "16:00:00", "Lab", "L1", faculty="Dr B"),
            rec(3, "2026-07-13", "MONDAY", "14:00:00", "16:00:00", "Lab", "L1", faculty="Dr A")]
    assert len(normalize_timetable(rows)) == 2


def test_overlapping_different_subjects_preserved():
    rows = [rec(1, "2026-07-06", "MONDAY", "09:00:00", "10:00:00", "A", "A1"), rec(2, "2026-07-06", "MONDAY", "09:30:00", "10:30:00", "B", "B1")]
    assert len(normalize_timetable(rows)) == 2


def test_dedupe_is_idempotent():
    rows = [rec(i, f"2026-07-{6 + 7 * i:02d}", "TUESDAY", "09:00:00", "10:00:00", "X") for i in range(4)]
    once = normalize_timetable(rows)
    from app.normalizers import dedupe_entries
    assert dedupe_entries(once + once) == once


def test_stale_stored_import_is_cleaned_on_read(logged_in, settings):
    """A timetable import stored before dedup existed must not keep showing repeats."""
    c = logged_in
    c.post("/api/import/timetable", content=json.dumps({"entries": [{"day": "Monday", "startTime": "09:00", "endTime": "10:00", "subjectName": "Old"}]}),
           headers={**csrf_headers(c), "Content-Type": "application/json"})
    conn = sqlite3.connect(settings.database_file)
    dup = {"day": "Monday", "start": "09:00", "end": "10:00", "subject_code": None, "subject_name": "Old", "faculty": None, "room": None, "kind": "class"}
    conn.execute("UPDATE imports SET payload=? WHERE kind='timetable'", (json.dumps([dup] * 5),))
    conn.commit(); conn.close()
    # live timetable is configured in the test settings, so force the imported path
    settings.data_source = "imported"
    assert len(c.get("/api/timetable").json()["entries"]) == 1


def test_semester_filter_keeps_only_student_semester(logged_in, settings):
    c = logged_in
    settings.data_source = "imported"
    rows = [rec(1, "2026-07-06", "MONDAY", "09:00:00", "10:00:00", "Mine", sem=3), rec(2, "2026-07-06", "TUESDAY", "09:00:00", "10:00:00", "Other", "O1", sem=5)]
    c.post("/api/import/profile", content=json.dumps({"student": {"fullName": "T", "semester": "3"}}), headers={**csrf_headers(c), "Content-Type": "application/json"})
    c.post("/api/import/timetable", content=json.dumps(rows), headers={**csrf_headers(c), "Content-Type": "application/json"})
    names = {e["subject_name"] for e in c.get("/api/timetable").json()["entries"]}
    assert names == {"Mine"}
