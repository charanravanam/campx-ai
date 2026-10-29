"""Import -> forecast -> simulate -> reset, with synthetic data only."""
from __future__ import annotations

import datetime as dt
import json

from conftest import csrf_headers, login, make_client

TODAY = dt.date.today()


def sess(i, days, subj="Alpha", code="A101", order=1, kind="Theory", periods=(1,), groups=(), **kw):
    d = (TODAY + dt.timedelta(days=days)).isoformat()
    r = {"id": i, "sessionDate": d, "orderNumber": order, "fromTime": f"{8 + order}:00:00", "toTime": f"{9 + order}:00:00",
         "completed": days < 0, "isSuspended": False, "subject": {"name": subj, "subjectCode": code, "subjectType": {"type": kind, "hasAttendance": True}},
         "periods": list(periods), "groups": [{"name": g} for g in groups], "timetableSlot": {"day": "MONDAY"}}
    r.update(kw)
    return r


def timetable():
    rows = [sess(1, -3), sess(2, -2)]                        # past: ignored for forecasting
    rows += [sess(10 + n, n) for n in range(1, 7)]           # 6 upcoming Alpha lectures
    rows += [sess(11, 1)]                                    # same upstream id repeated -> one session
    rows += [sess(50, 2, subj="Lab X", code="L1", order=5, kind="Lab", periods=(5, 6), groups=("Batch 1",)),
             sess(51, 2, subj="Lab X", code="L1", order=5, kind="Lab", periods=(5, 6), groups=("Batch 2",))]
    return rows


ATT = {"subjects": [{"subjectCode": "A101", "subjectName": "Alpha", "attended": 2, "total": 4},
                    {"subjectCode": "L1", "subjectName": "Lab X", "attended": 8, "total": 10}]}


def post(c, path, body, raw=False):
    data = body if raw else json.dumps(body)
    return c.post(path, content=data, headers={**csrf_headers(c), "Content-Type": "application/json"})


def setup(c):
    assert post(c, "/api/import/timetable", timetable()).status_code == 200
    r = post(c, "/api/import/attendance", ATT)
    assert r.status_code == 200, r.text
    return r.json()


def alpha(c, **q):
    j = c.get("/api/attendance/forecast", params=q).json()
    return j, next(s for s in j["subjects"] if s["subject_key"] == "a101")


def test_import_idempotent_and_updates(logged_in):
    c = logged_in
    first = setup(c)
    assert first["import_status"] == "created"
    again = post(c, "/api/import/attendance", {"subjects": ATT["subjects"][::-1]}).json()   # same content, different order -> different file
    assert again["import_status"] == "created"
    same = post(c, "/api/import/attendance", {"subjects": ATT["subjects"][::-1]}).json()
    assert same["import_status"] == "unchanged" and same["import_id"] == again["import_id"]
    back = post(c, "/api/import/attendance", ATT).json()
    assert back["import_status"] == "reactivated" and back["import_id"] == first["import_id"]


def test_forecast_uses_real_sessions_and_dedupes(logged_in):
    c = logged_in; setup(c)
    j, a = alpha(c)
    assert j["subjects"][0]["source_label"] == "Imported JSON"
    assert a["baseline"]["attended"] == 2 and a["classes_needed"] == 4
    assert len(a["upcoming"]) == 6                      # repeated id 10 collapsed
    assert a["recovery"]["state"] == "date" and a["recovery"]["sessions_used"] == 4
    assert a["recovery"]["date"] == (TODAY + dt.timedelta(days=4)).isoformat()


def test_simulation_updates_not_double_counts_and_keeps_baseline(logged_in):
    c = logged_in; setup(c)
    _, a = alpha(c); sk = a["upcoming"][0]["session_key"]
    body = {"subject_key": "a101", "session_key": sk, "status": "present"}
    assert post(c, "/api/attendance/adjustments", body).status_code == 200
    assert post(c, "/api/attendance/adjustments", body).status_code == 200      # retry
    _, a = alpha(c)
    assert (a["simulated"]["attended"], a["simulated"]["total"]) == (3, 5) and a["simulated"]["source_label"] == "Student Simulation"
    assert (a["baseline"]["attended"], a["baseline"]["total"]) == (2, 4) and a["baseline"]["source_label"] == "Imported JSON"
    post(c, "/api/attendance/adjustments", {**body, "status": "absent"})        # flip
    _, a = alpha(c)
    assert (a["simulated"]["attended"], a["simulated"]["total"]) == (2, 5)
    r = c.delete("/api/attendance/adjustments", headers=csrf_headers(c))
    assert r.json()["cleared"] == 1
    _, a = alpha(c)
    assert (a["simulated"]["attended"], a["simulated"]["total"]) == (2, 4) and not a["has_simulation"]


def test_scenario_never_persists(logged_in):
    c = logged_in; setup(c)
    r = post(c, "/api/attendance/scenario", {"subject_key": "a101", "attend": 3, "miss": 1})
    j = r.json()
    assert j["persisted"] is False and j["projected"]["attended"] == 5 and j["projected"]["total"] == 8
    r2 = post(c, "/api/attendance/scenario", {"subject_key": "a101", "sequence": ["present", "absent", "absent"], "target": 40})
    assert r2.json()["projected"]["total"] == 7 and r2.json()["meets_target"] is True
    _, a = alpha(c)
    assert (a["simulated"]["attended"], a["simulated"]["total"]) == (2, 4)


def test_adjustment_validation(logged_in):
    c = logged_in; setup(c)
    ok = lambda b: post(c, "/api/attendance/adjustments", b)
    assert ok({"subject_key": "a101", "session_key": "id:999", "status": "present"}).status_code == 404
    assert ok({"subject_key": "a101", "session_key": "id:1", "status": "present"}).status_code == 422       # past
    assert ok({"subject_key": "l1", "session_key": "id:11", "status": "present"}).status_code == 422        # wrong subject
    assert ok({"subject_key": "a101", "session_key": "id:11", "status": "maybe"}).status_code == 422
    assert ok({"subject_key": "a101", "session_key": "id:11", "status": "present", "extra": 1}).status_code == 422


def test_lab_batches_not_counted_until_marked(logged_in):
    c = logged_in; setup(c)
    j = c.get("/api/attendance/forecast").json()
    lab = next(s for s in j["subjects"] if s["subject_key"] == "l1")
    assert lab["recovery"]["state"] == "already_met"   # 8/10 meets 75%
    assert all(u["needs_confirmation"] for u in lab["upcoming"]) and any("lab-batch" in n for n in lab["notes"]) and any("span several periods" in n for n in lab["notes"])
    post(c, "/api/attendance/adjustments", {"subject_key": "l1", "session_key": "id:50", "status": "present"})
    lab = next(s for s in c.get("/api/attendance/forecast").json()["subjects"] if s["subject_key"] == "l1")
    assert lab["simulated"]["total"] == 11
    lab = next(s for s in c.get("/api/attendance/forecast", params={"lab_units": "period"}).json()["subjects"] if s["subject_key"] == "l1")
    assert lab["simulated"]["total"] == 12


def test_no_timetable_and_insufficient(logged_in):
    c = logged_in
    post(c, "/api/import/attendance", ATT)
    j, a = alpha(c)
    assert a["recovery"]["state"] == "no_timetable" and "cannot be estimated" in j["notice"]
    post(c, "/api/import/timetable", [sess(i, i) for i in range(1, 3)])
    _, a = alpha(c)
    assert a["recovery"]["state"] == "insufficient_sessions" and a["recovery"]["available_sessions"] == 2


def test_rejects_bad_imports(logged_in):
    c = logged_in
    dup = {"subjects": [ATT["subjects"][0], ATT["subjects"][0]]}
    assert post(c, "/api/import/attendance", dup).json()["error"]["code"] == "duplicate_subject"
    bad = {"subjects": [{"subjectCode": "X", "attended": 9, "total": 4}]}
    assert post(c, "/api/import/attendance", bad).status_code == 422
    assert post(c, "/api/import/attendance", "{not json", raw=True).json()["error"]["code"] == "invalid_json"
    assert post(c, "/api/import/attendance", "x" * 30000, raw=True).status_code == 413
    assert c.get("/api/attendance/forecast").json()["subjects"] == []


def test_csrf_and_auth_required(settings, fake):
    c = make_client(settings)
    try:
        assert c.get("/api/attendance/forecast").status_code == 401
        login(c)
        assert c.post("/api/attendance/scenario", json={"subject_key": "a"}).json()["error"]["code"] == "csrf_failed"
        assert c.delete("/api/attendance/adjustments").json()["error"]["code"] == "csrf_failed"
        assert c.get("/api/attendance/forecast", params={"target": 100}).status_code == 422
    finally:
        c.__exit__(None, None, None)


def test_two_users_isolated(settings, fake):
    a = make_client(settings); b = make_client(settings)
    try:
        login(a); login(b, "bob@example.invalid")
        setup(a)
        sk = alpha(a)[1]["upcoming"][0]["session_key"]
        post(a, "/api/attendance/adjustments", {"subject_key": "a101", "session_key": sk, "status": "present"})
        assert b.get("/api/attendance/forecast").json()["subjects"] == []
        assert post(b, "/api/attendance/adjustments", {"subject_key": "a101", "session_key": sk, "status": "absent"}).status_code == 409
        assert b.delete("/api/attendance/adjustments", headers=csrf_headers(b)).json()["cleared"] == 0
        assert alpha(a)[1]["simulated"]["attended"] == 3
    finally:
        a.__exit__(None, None, None); b.__exit__(None, None, None)


def test_persists_across_restart(settings, fake):
    c = make_client(settings)
    login(c); setup(c)
    sk = alpha(c)[1]["upcoming"][0]["session_key"]
    post(c, "/api/attendance/adjustments", {"subject_key": "a101", "session_key": sk, "status": "present"})
    c.__exit__(None, None, None)
    c2 = make_client(settings)                  # new app instance, same database file
    try:
        login(c2)
        assert alpha(c2)[1]["simulated"]["attended"] == 3
    finally:
        c2.__exit__(None, None, None)


def test_updated_import_starts_with_clean_ledger(logged_in):
    c = logged_in; setup(c)
    sk = alpha(c)[1]["upcoming"][0]["session_key"]
    post(c, "/api/attendance/adjustments", {"subject_key": "a101", "session_key": sk, "status": "present"})
    newer = {"subjects": [{"subjectCode": "A101", "subjectName": "Alpha", "attended": 3, "total": 5}]}
    assert post(c, "/api/import/attendance", newer).json()["import_status"] == "created"
    _, a = alpha(c)
    assert (a["simulated"]["attended"], a["simulated"]["total"]) == (3, 5) and not a["has_simulation"]
    post(c, "/api/import/attendance", ATT)       # back to the first file: its saved simulation returns, applied once
    assert alpha(c)[1]["simulated"]["attended"] == 3
