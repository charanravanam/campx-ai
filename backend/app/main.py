"""CampX AI backend entry point:  uvicorn app.main:app --reload   (run inside backend/)."""
from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from .config import Settings
from .db import connect, init_db
from .errors import error_response, install_error_handlers
from .ratelimit import RateLimiter
from .routes import admin, attendance_plan, auth, data, imports
from .security import Crypto, request_origin_allowed
from .sessions import SessionStore

log = logging.getLogger("campx_ai")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class _Redact(logging.Filter):
    """Belt and braces: scrub anything that looks like a secret from log lines."""
    _pat = re.compile(r"(password|token|cookie|authorization|secret)(\S*\s*[=:]\s*)\S+", re.I)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._pat.sub(r"\1\2[redacted]", str(record.msg))
        return True


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings()
    problems = s.startup_problems()
    if s.is_production and problems:
        raise RuntimeError("Refusing to start in production: " + " | ".join(problems))
    for p in problems:
        logging.getLogger("campx_ai").warning("Config problem: %s", p)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(s.database_file)
        if app.state.crypto is not None:
            app.state.store.purge_expired()
        yield

    app = FastAPI(
        title="CampX AI API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if s.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if s.is_production else "/openapi.json",
    )
    crypto = Crypto(s.app_secret_key) if s.secret_ok else None
    app.state.settings = s
    app.state.crypto = crypto
    app.state.store = SessionStore(s.database_file, crypto, s.max_sessions_per_user) if crypto else None
    app.state.limiter = RateLimiter(s.login_rate_limit_attempts, s.login_rate_limit_window_seconds)
    app.state.ip_limiter = RateLimiter(s.login_rate_limit_attempts * 4, s.login_rate_limit_window_seconds)
    if crypto is None:  # let /health and error paths work; store-dependent routes answer 503
        app.state.store = _NoStore()
    install_error_handlers(app)
    logging.getLogger("campx_ai").addFilter(_Redact())

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # 1) body size
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > s.max_import_bytes + 4096:
            return error_response(413, "payload_too_large", "Request body is too large.")
        # 2) CSRF + origin for cookie-authenticated, state-changing requests
        if request.method in UNSAFE and not request.url.path.startswith("/api/admin"):
            if not request_origin_allowed(request.headers.get("origin"), request.headers.get("referer"), s.allowed_origins):
                return error_response(403, "origin_not_allowed", "Request origin is not allowed.")
            if crypto is None:
                return error_response(503, "config_missing", "APP_SECRET_KEY is missing or too short. See README.")
            header = request.headers.get("x-csrf-token")
            cookie = request.cookies.get(s.csrf_cookie_name)
            import hmac as _h
            if not (header and cookie and _h.compare_digest(header, cookie) and crypto.csrf_token_valid(header)):
                return error_response(403, "csrf_failed", "Missing or invalid CSRF token. Reload the page and try again.")
        response = await call_next(request)
        # 3) security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api") or request.url.path == "/health":
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if s.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # CORS is added AFTER the guard so it is the outermost layer (errors get CORS headers too).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.get("/health", tags=["meta"])
    def health():
        db_ok = True
        try:
            init_db(s.database_file)
            with connect(s.database_file) as c:
                c.execute("SELECT 1")
        except Exception:
            db_ok = False
        return {
            "status": "ok" if db_ok else "degraded",
            "env": s.app_env,
            "database": "ok" if db_ok else "error",
            "config": {
                "secret_key_ok": s.secret_ok,
                "data_source": s.data_source,
                "live_endpoints_configured": s.live_endpoints(),
                "problems": s.startup_problems(),
            },
        }

    for r in (auth.router, data.router, attendance_plan.router, imports.router, admin.router):
        app.include_router(r)
    return app


class _NoStore:
    """Placeholder when APP_SECRET_KEY is missing: every use is a clean 503, never a crash."""
    def __getattr__(self, _name):
        from .errors import AppError
        raise AppError(503, "config_missing", "APP_SECRET_KEY is missing or too short. See README.")


app = create_app()
