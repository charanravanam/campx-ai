from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response

from ..campx_client import CampXClient
from ..deps import Auth, crypto_of, require_session, settings_of
from ..errors import AppError
from ..schemas import LoginRequest
from ..security import mask_login
from ..services import list_imports
from ..sessions import now

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _cookie_kwargs(s):
    return {
        "httponly": True,
        "secure": s.secure_cookies,
        "samesite": "none" if s.secure_cookies else "lax",
        "path": "/",
    }


def _set_csrf_cookie(response: Response, s, token: str) -> None:
    response.set_cookie(s.csrf_cookie_name, token, max_age=int(s.session_ttl_hours * 3600), **_cookie_kwargs(s))


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


@router.get("/csrf")
def csrf(request: Request, response: Response):
    s, crypto = settings_of(request), crypto_of(request)
    existing = request.cookies.get(s.csrf_cookie_name)
    token = existing if crypto.csrf_token_valid(existing) else crypto.new_csrf_token()
    _set_csrf_cookie(response, s, token)
    return {"csrf_token": token}


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    s, crypto = settings_of(request), crypto_of(request)
    if not s.campx_client_header_value.strip():
        raise AppError(503, "campx_not_configured", "CAMPX_CLIENT_HEADER_VALUE is not set. See README: 'Finding X-Campx-Client'.")

    limiter = request.app.state.limiter
    ip_limiter = request.app.state.ip_limiter
    ukey = crypto.user_key(s.campx_tenant_id, body.login_id)
    ip = request.client.host if request.client else "unknown"
    for lim, key in ((limiter, f"user:{ukey}"), (ip_limiter, f"ip:{ip}")):
        wait = lim.retry_after(key)
        if wait:
            raise AppError(429, "too_many_attempts", "Too many sign-in attempts. Wait and try again.", {"Retry-After": str(wait)})

    try:
        result = CampXClient(s).login(body.login_id, body.password)
    except AppError:
        limiter.hit(f"user:{ukey}")
        ip_limiter.hit(f"ip:{ip}")
        raise
    limiter.reset(f"user:{ukey}")

    store = request.app.state.store
    store.delete(request.cookies.get(s.session_cookie_name))  # no session fixation
    sid, expires = store.create(
        user_key=ukey,
        login_hint=mask_login(body.login_id),
        tenant=s.campx_tenant_id,
        campx_state={"token": result.token, "token_expiry": result.token_expiry, "cookies": result.cookies},
        ttl_seconds=s.session_ttl_hours * 3600,
        hard_expiry=result.token_expiry,
    )
    response.set_cookie(s.session_cookie_name, sid, max_age=max(1, int(expires - now())), **_cookie_kwargs(s))
    token = crypto.new_csrf_token()  # rotate CSRF token on privilege change
    _set_csrf_cookie(response, s, token)
    return {
        "authenticated": True,
        "user": {"login_hint": mask_login(body.login_id), "tenant": s.campx_tenant_id},
        "expires_at": _iso(expires),
        "csrf_token": token,
    }


@router.get("/me")
def me(auth: Auth = Depends(require_session)):
    s = auth.settings
    return {
        "authenticated": True,
        "user": {"login_hint": auth.session.login_hint, "tenant": auth.session.tenant},
        "expires_at": _iso(auth.session.expires_at),
        "data_source": s.data_source,
        "live_endpoints": s.live_endpoints(),
        "imports": {k: _iso(v) for k, v in list_imports(auth).items()},
    }


@router.post("/logout")
def logout(request: Request, response: Response):
    s = settings_of(request)
    request.app.state.store.delete(request.cookies.get(s.session_cookie_name))
    response.delete_cookie(s.session_cookie_name, path="/")
    response.delete_cookie(s.csrf_cookie_name, path="/")
    return {"authenticated": False}
