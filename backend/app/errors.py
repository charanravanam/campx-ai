"""One consistent error shape: {"error": {"code": "...", "message": "..."}}.

Messages never contain credentials, tokens, cookies or raw upstream bodies.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}


def error_response(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        headers=headers or None,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return error_response(exc.status, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        # IMPORTANT: FastAPI's default 422 body echoes the submitted input,
        # which would include passwords. We only return field locations + messages.
        problems = [
            {"field": ".".join(str(p) for p in e.get("loc", []) if p != "body"), "message": str(e.get("msg", "invalid"))}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": "Request validation failed.", "fields": problems}},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        # Log only the exception type: messages can contain upstream data.
        import logging

        logging.getLogger("campx_ai").error("Unhandled error: %s", type(exc).__name__)
        return error_response(500, "internal_error", "Unexpected server error.")
