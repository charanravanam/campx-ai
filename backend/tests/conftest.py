"""Shared fixtures. NOTHING here contacts the real CampX service."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import campx_client  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

ORIGIN = "http://localhost:5173"
SAMPLE = Path(__file__).resolve().parents[1] / "sample_data"

TIMETABLE_A = {"entries": [
    {"day": "Monday", "startTime": "09:00", "endTime": "09:50", "subjectCode": "A101", "subjectName": "Alpha Subject", "faculty": "Dr A", "room": "R1"},
    {"day": "Monday", "startTime": "10:00", "endTime": "10:50", "subjectCode": "A102", "subjectName": "Beta Subject", "faculty": "Dr B", "room": "R2"},
]}
TIMETABLE_B = {"entries": [
    {"day": "Tuesday", "startTime": "11:00", "endTime": "11:50", "subjectCode": "B201", "subjectName": "Zeta Subject", "faculty": "Dr Z", "room": "R9"},
]}


class FakeCampX:
    """In-memory stand-in for api.campx.in. Records every request it receives."""

    def __init__(self):
        self.users = {"alice@example.invalid": ("alice-pass", "A"), "bob@example.invalid": ("bob-pass", "B")}
        self.data = {"A": {"/student-api/classroom-timetables": TIMETABLE_A, "/student-api/profile": {"data": {"fullName": "Alice Fake", "rollNumber": "FA-1"}}},
                     "B": {"/student-api/classroom-timetables": TIMETABLE_B, "/student-api/profile": {"data": {"fullName": "Bob Fake", "rollNumber": "FB-1"}}}}
        self.requests: list[httpx.Request] = []
        self.mfa = False
        self.login_status: int | None = None   # force a status for login
        self.data_status: int | None = None    # force a status for data calls
        self.data_body: object | None = None   # force a body for data calls
        self.raise_timeout = False
        self.token_expiry = "2099-01-01T00:00:00.000Z"
        self.cookie_to_user: dict[str, str] = {}
        self.n = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_timeout:
            raise httpx.ReadTimeout("boom", request=request)
        if request.url.path == "/auth-server/auth-v2/login":
            if self.login_status:
                return httpx.Response(self.login_status, json={"message": "forced"})
            body = json.loads(request.content)
            rec = self.users.get(body.get("loginId"))
            if not rec or rec[0] != body.get("password"):
                return httpx.Response(401, json={"message": "bad credentials"})
            self.n += 1
            cookie = f"cookie-secret-{self.n}"
            self.cookie_to_user[cookie] = rec[1]
            return httpx.Response(
                201,
                json={"session": {"token": f"token-secret-{self.n}", "tokenExpiry": self.token_expiry, "subDomain": "gnitc", "institutionCode": "gnitc"},
                      "isMfaEnabled": self.mfa, "isMfaRequired": self.mfa, "skipMfaSetup": True},
                headers=[("set-cookie", f"campx_session_key={cookie}; Path=/; HttpOnly; Secure"),
                         ("set-cookie", "campx_tenant=gnitc; Path=/"), ("set-cookie", "campx_institution=gnitc; Path=/"),
                         ("set-cookie", "unrelated=zzz; Path=/")],
            )
        if self.data_status:
            return httpx.Response(self.data_status, json={"message": "forced"})
        cookie_hdr = request.headers.get("cookie", "")
        key = next((p.split("=", 1)[1] for p in cookie_hdr.split("; ") if p.startswith("campx_session_key=")), None)
        user = self.cookie_to_user.get(key or "")
        if not user:
            return httpx.Response(401, json={"message": "no session"})
        if self.data_body is not None:
            if isinstance(self.data_body, bytes):
                return httpx.Response(200, content=self.data_body)
            return httpx.Response(200, json=self.data_body)
        payload = self.data[user].get(request.url.path)
        if payload is None:
            return httpx.Response(404, json={"message": "nope"})
        return httpx.Response(200, json=payload)


@pytest.fixture
def fake():
    f = FakeCampX()
    campx_client.set_transport(httpx.MockTransport(f.handler))
    yield f
    campx_client.set_transport(None)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        app_env="development",
        app_secret_key="unit-test-secret-" + "x" * 40,
        frontend_origin=ORIGIN,
        database_path=str(tmp_path / "test.db"),
        campx_client_header_value="test-client-header-value",
        campx_timetable_path="/student-api/classroom-timetables",
        campx_profile_path="/student-api/profile",
        campx_attendance_path="",
        data_source="auto",
        login_rate_limit_attempts=3,
        login_rate_limit_window_seconds=300,
        max_import_bytes=20000,
    )


def make_client(settings) -> TestClient:
    c = TestClient(create_app(settings), base_url="http://localhost", headers={"Origin": ORIGIN})
    c.__enter__()  # run lifespan (DB init)
    return c


@pytest.fixture
def client(settings, fake):
    c = make_client(settings)
    yield c
    c.__exit__(None, None, None)


def login(c: TestClient, user="alice@example.invalid", password=None):
    password = password or {"alice@example.invalid": "alice-pass", "bob@example.invalid": "bob-pass"}.get(user, "x")
    tok = c.get("/api/auth/csrf").json()["csrf_token"]
    return c.post("/api/auth/login", json={"loginId": user, "password": password}, headers={"X-CSRF-Token": tok})


def csrf_headers(c: TestClient) -> dict:
    return {"X-CSRF-Token": c.get("/api/auth/csrf").json()["csrf_token"]}


@pytest.fixture
def logged_in(client, fake):
    r = login(client)
    assert r.status_code == 200, r.text
    return client
