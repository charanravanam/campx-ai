"""Cryptography and request-security helpers (no I/O)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken


def _derive(secret: str, label: bytes) -> bytes:
    return hmac.new(secret.encode("utf-8"), b"campx-ai:" + label, hashlib.sha256).digest()


class Crypto:
    """Encrypts the upstream CampX session blob and signs CSRF tokens."""

    def __init__(self, secret: str):
        self._secret = secret
        self._fernet = Fernet(base64.urlsafe_b64encode(_derive(secret, b"fernet")))
        self._csrf_key = _derive(secret, b"csrf")
        self._user_key = _derive(secret, b"user-key")

    # --- encryption at rest
    def encrypt_json(self, data: dict[str, Any]) -> str:
        return self._fernet.encrypt(json.dumps(data).encode("utf-8")).decode("ascii")

    def decrypt_json(self, blob: str) -> dict[str, Any] | None:
        try:
            return json.loads(self._fernet.decrypt(blob.encode("ascii")).decode("utf-8"))
        except (InvalidToken, ValueError):
            return None

    # --- identity key (no email stored in the database)
    def user_key(self, tenant: str, login_id: str) -> str:
        msg = f"{tenant.strip().lower()}|{login_id.strip().lower()}".encode("utf-8")
        return hmac.new(self._user_key, msg, hashlib.sha256).hexdigest()

    # --- CSRF tokens: "<nonce>.<signature>"
    def new_csrf_token(self) -> str:
        nonce = secrets.token_urlsafe(24)
        return f"{nonce}.{self._sign(nonce)}"

    def csrf_token_valid(self, token: str | None) -> bool:
        if not token or "." not in token or len(token) > 200:
            return False
        nonce, _, sig = token.partition(".")
        return hmac.compare_digest(sig, self._sign(nonce))

    def _sign(self, nonce: str) -> str:
        return hmac.new(self._csrf_key, nonce.encode("ascii", "ignore"), hashlib.sha256).hexdigest()[:40]


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def hash_session_id(session_id: str) -> str:
    """Only the hash is stored, so a stolen database cannot be replayed as cookies."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def mask_login(login_id: str) -> str:
    login_id = login_id.strip()
    if "@" in login_id:
        local, _, domain = login_id.partition("@")
        return f"{local[:2]}{'*' * max(2, len(local) - 2)}@{domain}"
    return f"{login_id[:2]}{'*' * max(2, len(login_id) - 2)}"


def origin_of(url: str) -> str | None:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def request_origin_allowed(origin: str | None, referer: str | None, allowed: list[str]) -> bool:
    """State-changing requests must come from the configured frontend origin(s).

    Origin header is checked first; Referer is a fallback; neither -> rejected.
    """
    allowed_l = {a.lower() for a in allowed}
    if origin:
        return origin.rstrip("/").lower() in allowed_l
    if referer:
        ref = origin_of(referer)
        return ref in allowed_l if ref else False
    return False
