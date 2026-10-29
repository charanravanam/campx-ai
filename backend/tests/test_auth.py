import json
import sqlite3

import pytest

from app import sessions as sessions_mod
from conftest import ORIGIN, csrf_headers, login, make_client


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert "secret" not in json.dumps(r.json()).lower().replace("secret_key_ok", "")


def test_login_success_sets_httponly_cookie_and_hides_tokens(client, fake):
    r = login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is True
    text = r.text
    for secret in ("token-secret", "cookie-secret", "alice-pass"):
        assert secret not in text
    set_cookie = r.headers.get_list("set-cookie")
    sess = [c for c in set_cookie if c.startswith("campxai_session=")][0]
    assert "HttpOnly" in sess and "samesite=lax" in sess.lower()
    assert all("cookie-secret" not in c and "token-secret" not in c for c in set_cookie)


def test_login_sends_observed_request_shape(client, fake):
    login(client)
    req = fake.requests[0]
    assert req.method == "POST" and req.url.path == "/auth-server/auth-v2/login"
    h = req.headers
    assert h["content-type"] == "application/json"
    assert h["x-campx-client"] == "test-client-header-value"
    assert h["x-platform-id"] == "campx" and h["x-tenant-id"] == "gnitc"
    assert h["origin"] == "https://gnitc.campx.in" and h["referer"] == "https://gnitc.campx.in/"
    body = json.loads(req.content)
    assert body["loginType"] == "USER" and body["tokenType"] == "WEB" and body["deviceType"] == "browser"
    assert body["latitude"] is None and body["longitude"] is None


def test_login_wrong_password(client, fake):
    r = login(client, password="wrong")
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    assert "campxai_session" not in r.headers.get("set-cookie", "")


def test_mfa_required_is_not_reported_as_success(client, fake):
    fake.mfa = True
    r = login(client)
    assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_unsupported"
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("upstream,status,code", [
    (403, 403, "upstream_forbidden"), (429, 429, "upstream_rate_limited"),
    (500, 502, "upstream_unavailable"), (503, 502, "upstream_unavailable"), (418, 502, "upstream_unexpected_status"),
])
def test_login_upstream_errors(client, fake, upstream, status, code):
    fake.login_status = upstream
    r = login(client)
    assert r.status_code == status and r.json()["error"]["code"] == code


def test_login_timeout(client, fake):
    fake.raise_timeout = True
    r = login(client)
    assert r.status_code == 504 and r.json()["error"]["code"] == "upstream_timeout"


def test_login_missing_client_header_is_503(settings, fake):
    s = settings.model_copy(update={"campx_client_header_value": ""})
    c = make_client(s)
    r = login(c)
    assert r.status_code == 503 and r.json()["error"]["code"] == "campx_not_configured"
    assert fake.requests == []


def test_missing_secret_is_503(settings, fake):
    s = settings.model_copy(update={"app_secret_key": ""})
    c = make_client(s)
    assert c.get("/api/auth/csrf").status_code == 503
    assert c.get("/api/auth/me").status_code == 503
    assert c.get("/health").status_code == 200


def test_validation_error_never_echoes_password(client):
    tok = client.get("/api/auth/csrf").json()["csrf_token"]
    r = client.post("/api/auth/login", json={"loginId": "ab", "password": "SuperSecret123"}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 422 and "SuperSecret123" not in r.text


def test_me_requires_session(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/timetable").status_code == 401
    assert client.get("/api/attendance").status_code == 401


def test_me_after_login_masks_login(logged_in):
    r = logged_in.get("/api/auth/me").json()
    assert r["user"]["login_hint"].startswith("al") and "alice@" not in json.dumps(r)


def test_logout_invalidates_session_even_if_cookie_replayed(logged_in):
    old_cookie = logged_in.cookies.get("campxai_session")
    assert logged_in.post("/api/auth/logout", headers=csrf_headers(logged_in)).status_code == 200
    assert logged_in.get("/api/auth/me").status_code == 401
    logged_in.cookies.set("campxai_session", old_cookie)  # attacker replays stolen cookie
    assert logged_in.get("/api/auth/me").status_code == 401


def test_sessions_are_isolated_per_user(settings, fake):
    a, b = make_client(settings), make_client(settings)
    assert login(a, "alice@example.invalid").status_code == 200
    assert login(b, "bob@example.invalid").status_code == 200
    assert a.cookies.get("campxai_session") != b.cookies.get("campxai_session")
    ta, tb = a.get("/api/timetable").json(), b.get("/api/timetable").json()
    assert {e["subject_code"] for e in ta["entries"]} == {"A101", "A102"}
    assert {e["subject_code"] for e in tb["entries"]} == {"B201"}
    # each upstream call used only its own user's cookie
    data_calls = [r for r in fake.requests if "student-api/classroom" in r.url.path]
    cookies = [r.headers["cookie"] for r in data_calls]
    assert len(set(cookies)) == 2


def test_session_expires(logged_in, monkeypatch):
    real = sessions_mod.now()
    monkeypatch.setattr(sessions_mod, "now", lambda: real + 9 * 3600)
    assert logged_in.get("/api/auth/me").status_code == 401


def test_session_capped_by_campx_token_expiry(settings, fake):
    from datetime import datetime, timedelta, timezone
    fake.token_expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    c = make_client(settings)
    login(c)
    exp = c.get("/api/auth/me").json()["expires_at"]
    assert datetime.fromisoformat(exp) < datetime.now(timezone.utc) + timedelta(minutes=6)


def test_secrets_not_stored_in_plaintext_or_logged(client, fake, settings, caplog):
    caplog.set_level("DEBUG")
    login(client)
    raw = open(settings.database_file, "rb").read()
    for secret in (b"alice-pass", b"token-secret", b"cookie-secret", b"alice@example"):
        assert secret not in raw
    for f in (settings.database_file.with_suffix(".db-wal"),):
        if f.exists():
            assert b"token-secret" not in f.read_bytes()
    assert "alice-pass" not in caplog.text and "token-secret" not in caplog.text


def test_new_login_replaces_presented_session(client):
    login(client)
    first = client.cookies.get("campxai_session")
    login(client)
    assert client.cookies.get("campxai_session") != first
