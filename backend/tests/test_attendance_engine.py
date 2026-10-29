"""Exact-arithmetic checks for the forecasting engine (no UI, no DB)."""
from fractions import Fraction
import pytest
from app.attendance_engine import (EngineError, apply_outcomes, classes_can_miss, classes_needed,
                                   meets, parse_threshold, percentage, plan_recovery, project, validate_counts)

P75 = parse_threshold(75)


def brute_needed(a, t, p):
    n = 0
    while Fraction(a + n, t + n) < p:
        n += 1
    return n


def brute_can_miss(a, t, p):
    s = 0
    while Fraction(a, t + s + 1) >= p:
        s += 1
    return s if Fraction(a, t) >= p else 0


@pytest.mark.parametrize("pct", [50, 65, 75, 80, "82.5", 90])
def test_needed_and_can_miss_match_brute_force(pct):
    p = parse_threshold(pct)
    for t in range(1, 41):
        for a in range(0, t + 1):
            assert classes_needed(a, t, p) == brute_needed(a, t, p), (a, t, pct)
            assert classes_can_miss(a, t, p) == brute_can_miss(a, t, p), (a, t, pct)


def test_exactly_at_just_below_just_above():
    assert meets(3, 4, P75) is True and classes_needed(3, 4, P75) == 0
    assert meets(299, 400, P75) is False and classes_needed(299, 400, P75) == 4  # 74.75% -> rounds to 74.75, not 75
    assert meets(301, 400, P75) is True
    assert classes_can_miss(3, 4, P75) == 0 and classes_can_miss(6, 8, P75) == 0 and classes_can_miss(7, 8, P75) == 1


def test_rounding_boundary_uses_counts_not_rounded_percentage():
    # 74.996...% displays as 75.0 but must NOT count as meeting 75%
    a, t = 149_999, 200_000 - 1  # 75.0000...% check below with exact numbers
    a, t = 74_999, 100_000
    assert percentage(a, t) == 75.0
    assert meets(a, t, P75) is False
    assert classes_needed(a, t, P75) == 4  # (74999+4)/(100004) = 0.75 exactly


def test_zero_attended_and_very_low():
    assert classes_needed(0, 10, P75) == 30
    assert classes_needed(0, 1, P75) == 3
    assert classes_needed(1, 100, P75) == 296


def test_zero_total_is_undefined_not_zero_or_hundred():
    assert percentage(0, 0) is None
    assert meets(0, 0, P75) is None and classes_needed(0, 0, P75) is None and classes_can_miss(0, 0, P75) is None
    assert plan_recovery(0, 0, P75, [])["state"] == "no_baseline"


def test_large_counts_exact():
    t = 10**15
    a = (3 * t) // 4
    assert classes_needed(a, t, P75) == 0
    assert classes_needed(a - 1, t, P75) == 4


def test_different_thresholds():
    assert classes_needed(60, 100, parse_threshold(65)) == 15  # (60+n)/(100+n) >= .65 -> n >= 14.28.. -> 15
    assert classes_needed(60, 100, parse_threshold(90)) == 300


@pytest.mark.parametrize("bad", [0, 100, -5, 101, "abc", None, True, float("nan"), float("inf")])
def test_bad_thresholds(bad):
    with pytest.raises(EngineError):
        parse_threshold(bad)


@pytest.mark.parametrize("a,t", [(-1, 5), (6, 5), (1.5, 5), ("3", 5), (True, 5), (1, -2)])
def test_bad_counts(a, t):
    with pytest.raises(EngineError):
        validate_counts(a, t)


def test_project_and_apply_outcomes():
    r = project(30, 40, 3, 2)
    assert (r["attended"], r["total"], r["missed"]) == (33, 45, 12) and r["percentage"] == 73.33
    assert apply_outcomes(30, 40, [("present", 1), ("absent", 2)]) == (31, 43)
    with pytest.raises(EngineError):
        project(30, 40, -1, 0)


def S(d, key, units=1, start="09:00"):
    return {"date": d, "session_key": key, "units": units, "start": start}


def test_recovery_date_first_session_that_reaches_threshold():
    # 2/4 -> needs 4 in a row
    up = [S("2026-11-05", "e"), S("2026-11-02", "a"), S("2026-11-03", "b"), S("2026-11-04", "c"), S("2026-11-04", "d", start="10:00")]
    r = plan_recovery(2, 4, P75, up)
    assert r["state"] == "date" and r["needed"] == 4 and r["date"] == "2026-11-04" and r["sessions_used"] == 4


def test_multiple_sessions_same_date_and_grouped_units():
    r = plan_recovery(2, 4, P75, [S("2026-11-02", "lab", units=4)])
    assert r["state"] == "date" and r["date"] == "2026-11-02" and r["units_used"] == 4


def test_insufficient_sessions_does_not_extrapolate():
    r = plan_recovery(2, 4, P75, [S("2026-11-02", "a"), S("2026-11-03", "b"), S("2026-11-04", "c")])
    assert r == {"state": "insufficient_sessions", "needed": 4, "available_sessions": 3, "available_units": 3}


def test_no_timetable_vs_empty_and_already_met():
    assert plan_recovery(2, 4, P75, None)["state"] == "no_timetable"
    assert plan_recovery(2, 4, P75, [])["state"] == "insufficient_sessions"
    assert plan_recovery(3, 4, P75, None) == {"state": "already_met", "needed": 0}
