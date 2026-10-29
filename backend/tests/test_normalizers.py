import json
from datetime import datetime

import pytest

from app import normalizers as N
from app.errors import AppError
from app.timetable_logic import today_view
from conftest import SAMPLE


def load(name):
    return json.load(open(SAMPLE / name))


def test_timetable_flat_entries_with_break_and_free():
    e = N.normalize_timetable(load("sample_timetable.json"))
    kinds = {x["kind"] for x in e}
    assert kinds == {"class", "break", "free"}
    mon = [x for x in e if x["day"] == "Monday"]
    assert [x["start"] for x in mon] == sorted(x["start"] for x in mon)
    assert next(x for x in e if x["kind"] == "break")["subject_name"] is None

def test_timetable_removes_exact_duplicate_entries():
    payload = {
        "entries": [
            {
                "day": "Monday",
                "startTime": "09:10",
                "endTime": "10:10",
                "subjectCode": "25PC0ME04",
                "subjectName": "Material Science and Metallurgy",
                "faculty": "D Prasuna Lilly Florence",
            },
            {
                "day": "Monday",
                "startTime": "09:10",
                "endTime": "10:10",
                "subjectCode": "25PC0ME04",
                "subjectName": "Material Science and Metallurgy",
                "faculty": "D Prasuna Lilly Florence",
            },
        ]
    }

    entries = N.normalize_timetable(payload)

    assert len(entries) == 1
    assert entries[0]["subject_code"] == "25PC0ME04"

def test_timetable_weekday_keyed_nested_subject_and_12h_time():
    e = N.normalize_timetable(load("sample_timetable_weekday_keyed.json"))
    assert [x["day"] for x in e] == ["Monday", "Tuesday", "Wednesday"]
    first = e[0]
    assert (first["start"], first["end"]) == ("09:00", "09:50")
    assert first["subject_code"] == "SMP101" and first["subject_name"] == "Sample Algorithms"
    assert first["faculty"] == "Dr. A. Faculty" and first["room"] == "R-101"


def test_timetable_day_blocks_and_wrapped_containers():
    payload = {"data": {"timetables": [{"day": "Tue", "periods": [{"startTime": "2024-01-02T14:30:00Z", "subject": "Maths", "teacher": {"name": "Mr X"}}]}]}}
    e = N.normalize_timetable(payload)
    assert e == [{"day": "Tuesday", "start": "14:30", "end": None, "subject_code": None, "subject_name": "Maths", "faculty": "Mr X", "room": None, "kind": "class"}]


def test_timetable_numeric_days():
    e = N.normalize_timetable([{"dayOfWeek": 1, "startTime": "9:00", "subjectName": "A"}, {"dayOfWeek": "7", "startTime": "9:00", "subjectName": "B"}])
    assert [x["day"] for x in e] == ["Monday", "Sunday"]


@pytest.mark.parametrize("bad", [None, 5, "text", {}, [], {"x": 1}, [1], {"entries": "str"}, [{"startTime": "9:00"}]])
def test_timetable_rejects_unknown(bad):
    if bad == []:
        assert N.normalize_timetable(bad) == []  # an empty list is a valid empty timetable
        return
    with pytest.raises(AppError) as ei:
        N.normalize_timetable(bad)
    assert ei.value.status == 422


@pytest.mark.parametrize("raw,out", [("9:00", "09:00"), ("09:05:30", "09:05"), ("1:30 PM", "13:30"), ("12:00 AM", "00:00"), ("12:15 pm", "12:15"), ("25:00", None), ("9:75", None), ("noon", None), (900, None)])
def test_parse_time(raw, out):
    assert N.parse_time(raw) == out


def test_profile_normalization():
    p = N.normalize_profile(load("sample_profile.json"))
    assert p["full_name"] == "Aarav Sample" and p["roll_number"] == "SAMPLE-0001" and p["section"] == "A"
    assert p["photo_url"] is None


def test_profile_wrapped_and_name_parts_and_photo_sanitised():
    p = N.normalize_profile({"data": {"firstName": "Zed", "lastName": "Fake", "photoUrl": "javascript:alert(1)", "branchName": "ECE"}})
    assert p["full_name"] == "Zed Fake" and p["branch"] == "ECE" and p["photo_url"] is None
    assert N.normalize_profile({"name": "A", "photo": "https://x.example/p.png"})["photo_url"] == "https://x.example/p.png"
    assert N.normalize_profile([{"name": "Solo"}])["full_name"] == "Solo"


@pytest.mark.parametrize("bad", [{"foo": 1}, "x", [], [1, 2], None, {"data": {}}])
def test_profile_rejects_unknown(bad):
    with pytest.raises(AppError):
        N.normalize_profile(bad)


def test_attendance_variants():
    recs = N.normalize_attendance({"data": [
        {"subject": {"code": "C1", "name": "One"}, "present": 8, "conducted": "10"},
        {"subjectName": "Two", "total": 20, "absent": 5},
        {"subjectName": "Three", "attendancePercentage": "82.5%"},
    ]})
    assert (recs[0]["attended"], recs[0]["total"], recs[0]["subject_code"]) == (8, 10, "C1")
    assert (recs[1]["attended"], recs[1]["total"]) == (15, 20)
    assert recs[2]["reported_percentage"] == 82.5 and recs[2]["attended"] is None


@pytest.mark.parametrize("bad", [
    {"subjects": [{"attended": 1, "total": 2}]}, {"subjects": [{"subjectName": "X"}]},
    {"subjects": [{"subjectName": "X", "attended": -1, "total": 2}]}, {"subjects": [{"subjectName": "X", "attended": 3, "total": 2}]},
    {"subjects": [{"subjectName": "X", "percentage": "abc"}]}, {"subjects": "no"}, 42, {"subjects": [1]}, {"subjects": [{"subjectName": "X", "attended": 1.5, "total": 3}]},
])
def test_attendance_rejects_bad(bad):
    with pytest.raises(AppError):
        N.normalize_attendance(bad)


def test_subjects():
    s = N.normalize_subjects(load("sample_subjects.json"))
    assert len(s) == 5 and s[0]["subject_code"] == "SMP101" and s[0]["credits"] == "4"
    with pytest.raises(AppError):
        N.normalize_subjects({"subjects": [{"credits": 3}]})


def test_today_view_current_and_next():
    e = N.normalize_timetable([
        {"day": "Monday", "startTime": "09:00", "endTime": "09:50", "subjectName": "A"},
        {"day": "Monday", "startTime": "09:50", "endTime": "10:00", "type": "Break"},
        {"day": "Monday", "startTime": "10:00", "endTime": "10:50", "subjectName": "B"},
        {"day": "Tuesday", "startTime": "09:00", "endTime": "09:50", "subjectName": "C"},
    ])
    mon_930 = datetime(2024, 1, 1, 9, 30)  # a Monday
    v = today_view(e, mon_930)
    assert v["day"] == "Monday" and v["class_count"] == 2
    assert v["current_class"]["subject_name"] == "A" and v["next_class"]["subject_name"] == "B"
    late = today_view(e, datetime(2024, 1, 1, 18, 0))
    assert late["next_class"] is None and late["current_class"] is None and late["upcoming"] == []
    assert today_view(e, datetime(2024, 1, 3, 9, 0))["entries"] == []  # Wednesday

def test_timetable_campx_nested_slot_and_faculties():
    payload = [
        {
            "fromTime": "14:00:00",
            "toTime": "16:00:00",
            "subject": {
                "subjectCode": "SAMPLE101",
                "name": "Sample Workshop",
            },
            "faculties": [{"fullName": "Sample Faculty"}],
            "timetableSlot": {"day": "WEDNESDAY"},
        }
    ]

    entries = N.normalize_timetable(payload)

    assert len(entries) == 1
    entry = entries[0]
    assert entry["day"] == "Wednesday"
    assert entry["start"] == "14:00"
    assert entry["end"] == "16:00"
    assert entry["subject_code"] == "SAMPLE101"
    assert entry["subject_name"] == "Sample Workshop"
    assert entry["faculty"] == "Sample Faculty"

def test_profile_normalizes_current_semester():
    profile = N.normalize_profile({"currentSemester": 3})
    assert profile["semester"] == "3"