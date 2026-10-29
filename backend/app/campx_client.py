"""The ONLY place that talks to CampX.

Facts used here come from the observed login request (see README). Everything
else - how follow-up requests are authenticated, and which data paths exist -
is configuration (CAMPX_AUTH_MODE, CAMPX_*_PATH) and is UNVERIFIED until you
confirm it with Chrome DevTools.

Security rules enforced here:
* credentials and tokens are never logged;
* each call uses ONLY the calling student's own upstream session state;
* redirects are not followed; request paths come from server config only;
* upstream error bodies are never copied into our responses.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import CookieError, SimpleCookie
from typing import Any

import httpx

from .config import Settings
from .errors import AppError

log = logging.getLogger("campx_ai.upstream")

MAX_UPSTREAM_BYTES = 5 * 1024 * 1024

# Test hook: tests install an httpx.MockTransport so nothing touches the network.
_TRANSPORT: httpx.BaseTransport | None = None


def set_transport(transport: httpx.BaseTransport | None) -> None:
    global _TRANSPORT
    _TRANSPORT = transport


@dataclass
class LoginResult:
    token: str
    token_expiry: float | None  # epoch seconds, if CampX reported a parsable value
    cookies: dict[str, str]


def _parse_iso(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _extract_cookies(resp: httpx.Response, allow: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for header in resp.headers.get_list("set-cookie"):
        jar: SimpleCookie = SimpleCookie()
        try:
            jar.load(header)
        except CookieError:
            continue
        for name, morsel in jar.items():
            if name in allow and morsel.value:
                found[name] = morsel.value
    return found


class CampXClient:
    def __init__(self, settings: Settings):
        self.s = settings

    # ---------------------------------------------------------------- plumbing
    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.s.campx_api_base,
            timeout=httpx.Timeout(self.s.request_timeout_seconds),
            follow_redirects=False,
            transport=_TRANSPORT,
        )

    def _base_headers(self) -> dict[str, str]:
        origin = self.s.campx_web_origin.rstrip("/")
        return {
            "Accept": "application/json",
            "X-Campx-Client": self.s.campx_client_header_value.strip(),
            "X-Platform-Id": self.s.campx_platform_id,
            "X-Tenant-Id": self.s.campx_tenant_id,
            "Origin": origin,
            "Referer": origin + "/",
        }

    def _auth_headers(self, state: dict[str, Any]) -> dict[str, str]:
        headers: dict[str, str] = {}
        modes = self.s.auth_modes
        token = state.get("token") or ""
        cookies: dict[str, str] = state.get("cookies") or {}
        if "cookie" in modes and cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        if "bearer" in modes and token:
            headers["Authorization"] = f"Bearer {token}"
        if "header" in modes and token and self.s.campx_token_header.strip():
            headers[self.s.campx_token_header.strip()] = token
        return headers

    @staticmethod
    def _raise_for_transport(exc: Exception) -> None:
        if isinstance(exc, httpx.TimeoutException):
            raise AppError(504, "upstream_timeout", "CampX did not respond in time. Try again shortly.") from None
        raise AppError(502, "upstream_unreachable", "Could not reach CampX. Check your network and try again.") from None

    # ------------------------------------------------------------------- login
    def login(self, login_id: str, password: str) -> LoginResult:
        if not self.s.campx_client_header_value.strip():
            raise AppError(
                503,
                "campx_not_configured",
                "CAMPX_CLIENT_HEADER_VALUE is not set. See README: 'Finding X-Campx-Client'.",
            )
        # Exactly the body shape observed from the official web app.
        body = {
            "loginId": login_id,
            "password": password,
            "deviceType": "browser",
            "clientName": "unknown",
            "os": "unknown",
            "osVersion": "unknown",
            "latitude": None,
            "longitude": None,
            "tokenType": "WEB",
            "loginType": "USER",
        }
        headers = {**self._base_headers(), "Content-Type": "application/json"}
        try:
            with self._client() as c:
                resp = c.post(self.s.campx_login_path, json=body, headers=headers)
        except httpx.HTTPError as exc:
            self._raise_for_transport(exc)

        status = resp.status_code
        if status in (400, 401):
            raise AppError(401, "invalid_credentials", "Incorrect login ID or password.")
        if status == 403:
            raise AppError(
                403,
                "upstream_forbidden",
                "CampX refused the login request (HTTP 403). This can mean the account is blocked or the "
                "X-Campx-Client value is wrong. Not a password problem we can detect.",
            )
        if status == 429:
            wait = resp.headers.get("retry-after", "")
            hdr = {"Retry-After": wait} if wait.isdigit() else {}
            raise AppError(429, "upstream_rate_limited", "CampX is rate limiting logins. Wait a few minutes.", hdr)
        if status >= 500:
            raise AppError(502, "upstream_unavailable", f"CampX is having problems (HTTP {status}). Try later.")
        if status not in (200, 201):
            raise AppError(502, "upstream_unexpected_status", f"CampX answered login with unexpected HTTP {status}.")

        try:
            data = resp.json()
        except ValueError:
            raise AppError(502, "upstream_malformed", "CampX returned a login response we could not parse.") from None
        if not isinstance(data, dict):
            raise AppError(502, "upstream_malformed", "CampX returned an unexpected login response shape.")

        # MFA: we do NOT implement CampX MFA, and we never pretend login worked.
        if data.get("isMfaRequired") is True:
            raise AppError(
                403,
                "mfa_unsupported",
                "This CampX account requires multi-factor verification, which CampX AI does not support yet. "
                "No session was created.",
            )
        session = data.get("session")
        token = session.get("token") if isinstance(session, dict) else None
        if not isinstance(token, str) or not token:
            raise AppError(502, "upstream_malformed", "CampX login succeeded but returned no session token.")
        return LoginResult(
            token=token,
            token_expiry=_parse_iso(session.get("tokenExpiry")),
            cookies=_extract_cookies(resp, self.s.cookie_name_allowlist),
        )

    # ----------------------------------------------------------- authenticated
    def get_json(self, path: str, state: dict[str, Any]) -> Any:
        """GET a configured CampX path with THIS student's session state."""
        path = (path or "").strip()
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise AppError(503, "not_configured", "The configured CampX path is invalid (must start with '/').")
        if not self.s.campx_client_header_value.strip():
            raise AppError(503, "campx_not_configured", "CAMPX_CLIENT_HEADER_VALUE is not set.")

        auth = self._auth_headers(state)
        if not auth:
            raise AppError(
                502,
                "campx_auth_not_established",
                "CampX did not give us anything usable for CAMPX_AUTH_MODE. Verify the mode in DevTools "
                "(try CAMPX_AUTH_MODE=bearer or header) - see steps_for_chatgpt.md section 11.",
            )
        try:
            with self._client() as c:
                resp = c.get(path, headers={**self._base_headers(), **auth})
        except httpx.HTTPError as exc:
            self._raise_for_transport(exc)

        status = resp.status_code
        if status == 401:
            raise AppError(401, "campx_session_expired", "Your CampX session expired. Please sign in again.")
        if status == 403:
            raise AppError(
                403,
                "upstream_forbidden",
                "CampX refused this request (HTTP 403). Your account may not be allowed to use this data, "
                "or CAMPX_AUTH_MODE is wrong.",
            )
        if status == 404:
            raise AppError(404, "upstream_not_found", "CampX has no resource at the configured path (HTTP 404).")
        if status == 429:
            wait = resp.headers.get("retry-after", "")
            hdr = {"Retry-After": wait} if wait.isdigit() else {}
            raise AppError(429, "upstream_rate_limited", "CampX is rate limiting requests. Slow down and retry.", hdr)
        if status >= 500:
            raise AppError(502, "upstream_unavailable", f"CampX is having problems (HTTP {status}).")
        if status < 200 or status >= 300:
            raise AppError(502, "upstream_unexpected_status", f"CampX answered with unexpected HTTP {status}.")
        if len(resp.content) > MAX_UPSTREAM_BYTES:
            raise AppError(502, "upstream_too_large", "CampX response was unexpectedly large.")
        try:
            return resp.json()
        except ValueError:
            raise AppError(502, "upstream_malformed", "CampX returned data that is not valid JSON.") from None
