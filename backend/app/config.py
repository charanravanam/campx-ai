"""Application settings, loaded from environment variables / the root .env file.

Every setting has a safe default. Missing *required* values (for example
APP_SECRET_KEY) do not crash the app in development; the features that need
them answer with HTTP 503 and a clear message instead.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIN_SECRET_LENGTH = 32
VALID_DATA_SOURCES = ("campx", "imported", "auto")
VALID_AUTH_MODES = ("cookie", "bearer", "header")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application
    app_env: str = "development"
    app_secret_key: str = ""
    frontend_origin: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_path: str = "backend/data/campx_ai.db"
    session_ttl_hours: float = 8
    max_sessions_per_user: int = 5
    cookie_secure: bool | None = None
    app_timezone: str = "Asia/Kolkata"

    # --- data source
    data_source: str = "auto"

    # --- CampX upstream
    campx_api_base: str = "https://api.campx.in"
    campx_web_origin: str = "https://gnitc.campx.in"
    campx_login_path: str = "/auth-server/auth-v2/login"
    campx_platform_id: str = "campx"
    campx_tenant_id: str = "gnitc"
    campx_client_header_value: str = ""
    campx_auth_mode: str = "cookie"
    campx_token_header: str = ""
    campx_cookie_names: str = "campx_session_key,campx_tenant,campx_institution"
    campx_profile_path: str = ""
    campx_timetable_path: str = "/student-api/classroom-timetables"
    campx_attendance_path: str = ""
    campx_subjects_path: str = ""

    # --- limits
    request_timeout_seconds: float = 15
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 300
    max_import_bytes: int = 262144

    # --- admin
    admin_token: str = ""

    @field_validator("cookie_secure", mode="before")
    @classmethod
    def _empty_bool_is_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # ------------------------------------------------------------------ helpers
    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.frontend_origin.split(",") if o.strip()]

    @property
    def secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure

    @property
    def session_cookie_name(self) -> str:
        # "__Host-" prefix: browser enforces Secure + Path=/ + no Domain.
        return "__Host-campxai_session" if self.secure_cookies else "campxai_session"

    @property
    def csrf_cookie_name(self) -> str:
        return "__Host-campxai_csrf" if self.secure_cookies else "campxai_csrf"

    @property
    def secret_ok(self) -> bool:
        return len(self.app_secret_key) >= MIN_SECRET_LENGTH

    @property
    def auth_modes(self) -> list[str]:
        return [m.strip().lower() for m in self.campx_auth_mode.split(",") if m.strip()]

    @property
    def cookie_name_allowlist(self) -> set[str]:
        return {n.strip() for n in self.campx_cookie_names.split(",") if n.strip()}

    @property
    def database_file(self) -> Path:
        p = Path(self.database_path)
        return p if p.is_absolute() else PROJECT_ROOT / p

    def live_endpoints(self) -> dict[str, bool]:
        return {
            "login": bool(self.campx_client_header_value.strip()),
            "profile": bool(self.campx_profile_path.strip()),
            "timetable": bool(self.campx_timetable_path.strip()),
            "attendance": bool(self.campx_attendance_path.strip()),
            "subjects": bool(self.campx_subjects_path.strip()),
        }

    def startup_problems(self) -> list[str]:
        """Problems that must stop a PRODUCTION start (development only warns)."""
        problems: list[str] = []
        if not self.secret_ok:
            problems.append(f"APP_SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters.")
        if self.data_source not in VALID_DATA_SOURCES:
            problems.append(f"DATA_SOURCE must be one of {VALID_DATA_SOURCES}.")
        bad_modes = [m for m in self.auth_modes if m not in VALID_AUTH_MODES]
        if bad_modes or not self.auth_modes:
            problems.append(f"CAMPX_AUTH_MODE must be a comma list of {VALID_AUTH_MODES}.")
        if "header" in self.auth_modes and not self.campx_token_header.strip():
            problems.append("CAMPX_AUTH_MODE includes 'header' but CAMPX_TOKEN_HEADER is empty.")
        if self.is_production:
            if not self.allowed_origins or any(not o.startswith("https://") for o in self.allowed_origins):
                problems.append("In production FRONTEND_ORIGIN must list only https:// origins.")
            if not self.secure_cookies:
                problems.append("In production COOKIE_SECURE must not be false.")
            if self.admin_token and len(self.admin_token) < MIN_SECRET_LENGTH:
                problems.append("ADMIN_TOKEN must be at least 32 characters (or empty to disable).")
        return problems
