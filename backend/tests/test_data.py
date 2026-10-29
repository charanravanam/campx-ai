import json

import pytest

from conftest import ORIGIN, SAMPLE, csrf_headers, login, make_client


def post_import(c, kind, payload, raw=None):
    body = raw if raw is not None else json.dumps(payload)
    return c.post(f"/api/import/{kind}", content=body, headers={**csrf_headers(c), "Content-Type": "application/json"})


def test_live_timetable_and_profile(logged_in):
    t = logged_in.get("/api/campx/timetable").json()
    assert t["source"] == "campx" and t["entries"][0]["subject_name"] == "Alpha Subject"
    p = logged_in.get("/api/campx/profile").json()
    assert p["profile"]["full_name"] == "Alice Fake"
    assert "token" not in json.dumps(p).lower()

def test_timetable_filters_by_student_semester(logged_in, fake):
    fake.data["A"]["/student-api/profile"] = {
        "data": {"fullName": "Alice Fake", "rollNumber": "FA-1", "currentSemester": 3}
    }
    fake.data["A"]["/student-api/classroom-timetables"] = {
        "entries": [
            {
                "day": "Monday",
                "startTime": "09:00",
                "endTime": "09:50",
                "subjectName": "Semester Three Subject",
                "semNo": 3,
            },
            {
                "day": "Monday",
                "startTime": "10:00",
                "endTime": "10:50",
                "subjectName": "Semester Two Subject",
                "semNo": 2,
            },
        ]
    }

    response = logged_in.get("/api/timetable")
    assert response.status_code == 200

    entries = response.json()["entries"]
    assert [entry["subject_name"] for entry in entries] == [
        "Semester Three Subject"
    ]


def test_upstream_auth_uses_cookie_mode_and_standard_headers(logged_in, fake):
    logged_in.get("/api/campx/timetable")
    req = fake.requests[-1]
    assert req.headers["cookie"].startswith("campx_session_key=cookie-secret")
    assert "unrelated" not in req.headers["cookie"]  # only allow-listed cookies replayed
    assert "authorization" not in req.headers
    assert req.headers["x-tenant-id"] == "gnitc" and req.headers["x-campx-client"]


def test_bearer_mode(settings, fake):
    c = make_client(settings.model_copy(update={"campx_auth_mode": "bearer"}))
    login(c)
    c.get("/api/campx/timetable")
    assert fake.requests[-1].headers["authorization"] == "Bearer token-secret-1"
    assert "cookie" not in fake.requests[-1].headers


@pytest.mark.parametrize("status,http,code", [
    (403, 403, "upstream_forbidden"), (404, 404, "upstream_not_found"), (429, 429, "upstream_rate_limited"),
    (500, 502, "upstream_unavailable"), (502, 502, "upstream_unavailable"),
])
def test_live_upstream_http_errors(logged_in, fake, status, http, code):
    fake.data_status = status
    r = logged_in.get("/api/campx/timetable")
    assert r.status_code == http and r.json()["error"]["code"] == code
    assert "forced" not in r.text  # upstream body never leaked


def test_live_upstream_401_invalidates_our_session(logged_in, fake):
    fake.data_status = 401
    r = logged_in.get("/api/campx/timetable")
    assert r.status_code == 401 and r.json()["error"]["code"] == "campx_session_expired"
    assert logged_in.get("/api/auth/me").status_code == 401


def test_live_timeout(logged_in, fake):
    fake.raise_timeout = True
    r = logged_in.get("/api/campx/timetable")
    assert r.status_code == 504 and r.json()["error"]["code"] == "upstream_timeout"


def test_live_malformed_json(logged_in, fake):
    fake.data_body = b"<html>not json</html>"
    r = logged_in.get("/api/campx/timetable")
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_malformed"


def test_live_unknown_structure_is_422_not_fake_data(logged_in, fake):
    fake.data_body = {"weird": {"shape": 1}}
    r = logged_in.get("/api/campx/timetable")
    assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_structure"


def test_unconfigured_attendance_is_503_in_campx_mode(settings, fake):
    c = make_client(settings.model_copy(update={"data_source": "campx"}))
    login(c)
    r = c.get("/api/attendance")
    assert r.status_code == 503 and r.json()["error"]["code"] == "not_configured"


def test_auto_mode_unconfigured_returns_empty_with_notice(logged_in):
    r = logged_in.get("/api/attendance").json()
    assert r["source"] == "none" and r["subjects"] == [] and r["overall"] is None and r["notice"]


def test_imported_mode_ignores_live(settings, fake):
    c = make_client(settings.model_copy(update={"data_source": "imported"}))
    login(c)
    assert c.get("/api/timetable").json()["source"] == "none"
    assert not [r for r in fake.requests if "student-api" in r.url.path]
    assert post_import(c, "timetable", json.load(open(SAMPLE / "sample_timetable.json"))).status_code == 200
    r = c.get("/api/timetable").json()
    assert r["source"] == "imported" and len(r["entries"]) > 10


def test_auto_falls_back_to_import_when_route_404(logged_in, fake):
    post_import(logged_in, "timetable", {"entries": [{"day": "Friday", "startTime": "10:00", "endTime": "10:50", "subjectName": "Imported One"}]})
    fake.data_status = 404
    r = logged_in.get("/api/timetable").json()
    assert r["source"] == "imported" and "unavailable" in r["notice"]


def test_auto_prefers_live_over_imported(logged_in):
    post_import(logged_in, "timetable", {"entries": [{"day": "Friday", "startTime": "10:00", "subjectName": "Imported One"}]})
    assert logged_in.get("/api/timetable").json()["source"] == "campx"


def test_attendance_import_and_math(logged_in):
    r = post_import(logged_in, "attendance", json.load(open(SAMPLE / "sample_attendance.json")))
    assert r.status_code == 200 and r.json()["count"] == 5
    a = logged_in.get("/api/attendance?target=75").json()
    assert a["source"] == "imported" and a["target"] == 75
    row = {x["subject_code"]: x for x in a["subjects"]}["SMP104"]  # 25/40 = 62.5%
    assert row["percentage"] == 62.5 and row["status"] == "low" and row["classes_needed"] == 20
    assert a["overall"]["attended"] == 167 and a["overall"]["total"] == 217
    assert logged_in.get("/api/attendance?target=0").status_code == 422
    assert logged_in.get("/api/attendance?target=101").status_code == 422


def test_import_requires_auth_and_csrf(client):
    assert client.post("/api/import/timetable", json={}).status_code == 403  # csrf first
    r = client.post("/api/import/timetable", content="{}", headers={**csrf_headers(client), "Content-Type": "application/json"})
    assert r.status_code == 401


def test_import_malformed_json(logged_in):
    r = post_import(logged_in, "timetable", None, raw="{not json")
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_json"
    r = post_import(logged_in, "timetable", None, raw=b"\xff\xfe")
    assert r.status_code == 400


def test_import_unknown_structure_and_bad_values(logged_in):
    assert post_import(logged_in, "timetable", {"hello": "world"}).status_code == 422
    assert post_import(logged_in, "timetable", [1, 2, 3]).status_code == 422
    assert post_import(logged_in, "timetable", {"entries": [{"startTime": "9:00", "subjectName": "No Day"}]}).status_code == 422
    assert post_import(logged_in, "attendance", {"subjects": [{"subjectName": "X", "attended": 9, "total": 5}]}).status_code == 422
    assert post_import(logged_in, "attendance", {"subjects": [{"subjectName": "X", "attended": 5}]}).status_code == 422
    assert post_import(logged_in, "attendance", {"subjects": [{"subjectName": "X", "percentage": 140}]}).status_code == 422
    assert post_import(logged_in, "profile", {"unknown": 1}).status_code == 422


def test_import_size_limit(logged_in):
    big = {"entries": [{"day": "Monday", "startTime": "09:00", "subjectName": "x" * 100}] * 400}
    r = post_import(logged_in, "timetable", big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"


def test_import_isolation_between_students(settings, fake):
    s = settings.model_copy(update={"data_source": "imported"})
    a, b = make_client(s), make_client(s)
    login(a, "alice@example.invalid"); login(b, "bob@example.invalid")
    post_import(a, "timetable", {"entries": [{"day": "Monday", "startTime": "09:00", "subjectName": "Alice Private"}]})
    assert "Alice Private" in a.get("/api/timetable").text
    assert "Alice Private" not in b.get("/api/timetable").text
    assert b.get("/api/import/status").json()["imports"] == {}
    # imports survive logout/login for the same student
    a.post("/api/auth/logout", headers=csrf_headers(a)); login(a, "alice@example.invalid")
    assert "Alice Private" in a.get("/api/timetable").text


def test_import_delete(logged_in):
    post_import(logged_in, "profile", json.load(open(SAMPLE / "sample_profile.json")))
    assert "profile" in logged_in.get("/api/import/status").json()["imports"]
    assert logged_in.delete("/api/import/profile", headers=csrf_headers(logged_in)).json()["deleted"] is True
    assert logged_in.delete("/api/import/bogus", headers=csrf_headers(logged_in)).status_code == 404


def test_today_endpoint(logged_in):
    r = logged_in.get("/api/timetable/today").json()
    assert {"day", "entries", "next_class", "upcoming", "class_count"} <= set(r)


def test_subjects_derived_from_timetable(logged_in):
    r = logged_in.get("/api/subjects").json()
    assert r["derived"] is True and {s["subject_code"] for s in r["subjects"]} == {"A101", "A102"}


def test_subjects_import(logged_in):
    post_import(logged_in, "subjects", json.load(open(SAMPLE / "sample_subjects.json")))
    r = logged_in.get("/api/subjects").json()
    assert r["derived"] is False and r["source"] == "imported" and len(r["subjects"]) == 5
