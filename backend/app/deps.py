"""FastAPI dependencies shared by routes."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from .config import Settings
from .errors import AppError
from .security import Crypto
from .sessions import SessionData, SessionStore, now


@dataclass
class Auth:
    settings: Settings
    store: SessionStore
    crypto: Crypto
    sid: str
    session: SessionData


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def crypto_of(request: Request) -> Crypto:
    crypto = request.app.state.crypto
    if crypto is None:
        raise AppError(503, "config_missing", "APP_SECRET_KEY is missing or shorter than 32 characters. See README step 'Configure .env'.")
    return crypto


def require_session(request: Request) -> Auth:
    s = settings_of(request)
    crypto = crypto_of(request)
    store: SessionStore = request.app.state.store
    sid = request.cookies.get(s.session_cookie_name)
    session = store.get(sid)
    if session is None or sid is None:
        raise AppError(401, "not_authenticated", "Please sign in.")
    upstream_expiry = session.campx.get("token_expiry")
    if isinstance(upstream_expiry, (int, float)) and upstream_expiry <= now():
        store.delete(sid)
        raise AppError(401, "campx_session_expired", "Your CampX session expired. Please sign in again.")
    return Auth(settings=s, store=store, crypto=crypto, sid=sid, session=session)
