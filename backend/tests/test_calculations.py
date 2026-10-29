import itertools
from fractions import Fraction

import pytest

from app.calculations import build_attendance, classes_can_miss, classes_needed, percentage, subject_row


def test_known_values():
    assert classes_needed(25, 40, 75) == 20   # (25+20)/(40+20)=0.75
    assert classes_needed(30, 40, 75) == 0    # already at 75%
    assert classes_needed(0, 0, 75) == 0
    assert classes_needed(9, 10, 100) is None
    assert classes_needed(10, 10, 100) == 0
    assert classes_can_miss(30, 40, 75) == 0
    assert classes_can_miss(40, 40, 75) == 13  # 40/53 = 75.47%, 40/54 = 74.07%
    assert percentage(0, 0) is None and percentage(1, 3) == 33.33


def test_bruteforce_matches_definition():
    for t, a, target in itertools.product(range(0, 31), range(0, 31), (1, 33, 50, 60, 75, 80, 85, 90, 99)):
        if a > t:
            continue
        n = classes_needed(a, t, target)
        meets = lambda x: Fraction(a + x, t + x) * 100 >= target if (t + x) else True
        assert meets(n)
        if n > 0:
            assert not meets(n - 1), (a, t, target)
        s = classes_can_miss(a, t, target)
        ok = lambda m: t + m == 0 or Fraction(a, t + m) * 100 >= target
        if Fraction(a, t) * 100 >= target if t else False:
            assert ok(s) and not ok(s + 1), (a, t, target)
        else:
            assert s == 0


def test_build_attendance_mixed_sources():
    recs = [
        {"subject_code": "A", "subject_name": "A", "attended": 30, "total": 40, "reported_percentage": None},
        {"subject_code": "B", "subject_name": "B", "attended": None, "total": None, "reported_percentage": 60.0},
    ]
    r = build_attendance(recs, 75)
    assert r["overall"]["subjects_counted"] == 1 and r["overall"]["subjects_total"] == 2 and r["overall"]["percentage"] == 75.0
    b = r["subjects"][1]
    assert b["percentage_basis"] == "reported" and b["classes_needed"] is None and b["status"] == "low"


def test_zero_total_has_no_percentage():
    row = subject_row({"subject_name": "Z", "attended": 0, "total": 0}, 75)
    assert row["percentage"] is None and row["status"] == "unknown"
    assert build_attendance([{"subject_name": "Z", "attended": 0, "total": 0}])["overall"] is None
