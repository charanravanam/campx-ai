import pytest

from conftest import ORIGIN, csrf_headers, login, make_client


def test_login_without_csrf_rejected(client):
    r = client.post("/api/auth/login", json={"loginId": "alice@example.invalid", "password": "alice-pass"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"


def test_login_with_forged_csrf_rejected(client):
    client.get("/api/auth/csrf")
    r = client.post("/api/auth/login", json={"loginId": "a@b.c", "password": "x"}, headers={"X-CSRF-Token": "forged.token"})
    assert r.status_code == 403


def test_csrf_header_must_match_cookie(client, settings):
    good = client.get("/api/auth/csrf").json()["csrf_token"]
    other = make_client(settings).get("/api/auth/csrf").json()["csrf_token"]  # validly signed, but not our cookie
    r = client.post("/api/auth/login", json={"loginId": "alice@example.invalid", "password": "alice-pass"}, headers={"X-CSRF-Token": other})
    assert r.status_code == 403 and good != other


def test_csrf_token_reused_while_cookie_valid(client):
    assert client.get("/api/auth/csrf").json() == client.get("/api/auth/csrf").json()


def test_foreign_origin_rejected(client):
    h = csrf_headers(client)
    r = client.post("/api/auth/logout", headers={**h, "Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "origin_not_allowed"


def test_missing_origin_and_referer_rejected(settings, fake):
    from fastapi.testclient import TestClient
    from app.main import create_app
    c = TestClient(create_app(settings), base_url="http://localhost")
    tok = c.get("/api/auth/csrf").json()["csrf_token"]
    assert c.post("/api/auth/logout", headers={"X-CSRF-Token": tok}).status_code == 403
    assert c.post("/api/auth/logout", headers={"X-CSRF-Token": tok, "Referer": ORIGIN + "/page"}).status_code == 200


def test_logout_requires_csrf(logged_in):
    assert logged_in.post("/api/auth/logout").status_code == 403
    assert logged_in.get("/api/auth/me").status_code == 200  # still logged in


def test_cors_only_for_configured_origin(client):
    ok = client.options("/api/auth/csrf", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == ORIGIN
    bad = client.options("/api/auth/csrf", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_login_rate_limited_after_repeated_failures(client, fake):
    for _ in range(3):
        assert login(client, password="wrong").status_code == 401
    r = login(client, password="wrong")
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_attempts"
    assert int(r.headers["retry-after"]) > 0
    n = len(fake.requests)
    assert login(client).status_code == 429  # even the right password is blocked
    assert len(fake.requests) == n  # and CampX is not contacted


def test_rate_limit_is_per_account(client, fake):
    for _ in range(3):
        login(client, password="wrong")
    assert login(client, "bob@example.invalid").status_code == 200


def test_rate_limit_counter_resets_after_success(client):
    for _ in range(2):
        login(client, password="wrong")
    assert login(client).status_code == 200
    for _ in range(2):
        login(client, password="wrong")
    assert login(client).status_code == 200


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert client.get("/api/auth/csrf").headers["cache-control"] == "no-store"


def test_oversized_body_rejected(client):
    r = client.post("/api/auth/login", content=b"x" * 40000, headers={"Content-Type": "application/json", "X-CSRF-Token": "a"})
    assert r.status_code == 413


def test_production_refuses_weak_config(settings):
    from app.main import create_app
    with pytest.raises(RuntimeError):
        create_app(settings.model_copy(update={"app_env": "production"}))  # http origin
    ok = settings.model_copy(update={"app_env": "production", "frontend_origin": "https://app.example.edu"})
    app = create_app(ok)
    assert app.state.settings.session_cookie_name.startswith("__Host-")
    assert app.docs_url is None


def test_admin_disabled_without_token(client):
    assert client.get("/api/admin/stats").status_code == 404


def test_admin_requires_separate_credential(settings, fake):
    c = make_client(settings.model_copy(update={"admin_token": "a" * 40}))
    assert c.get("/api/admin/stats").status_code == 401
    assert c.get("/api/admin/stats", headers={"X-Admin-Token": "wrong"}).status_code == 401
    login(c)
    assert c.get("/api/admin/stats").status_code == 401  # a student session is NOT admin
    r = c.get("/api/admin/stats", headers={"X-Admin-Token": "a" * 40})
    assert r.status_code == 200 and r.json()["active_sessions"] == 1
    assert c.post("/api/admin/revoke-all", headers={"X-Admin-Token": "a" * 40}).json()["revoked"] == 1
    assert c.get("/api/auth/me").status_code == 401
