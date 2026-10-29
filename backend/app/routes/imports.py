from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request

from ..deps import Auth, require_session
from ..errors import AppError
from ..attendance_store import delete_attendance_imports, store_attendance_import
from ..services import KINDS, NORMALIZERS, SESSIONS_KIND, delete_import, list_imports, save_import

router = APIRouter(prefix="/api/import", tags=["import"])


async def read_limited_json(request: Request, limit: int):
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise AppError(413, "payload_too_large", f"Import is larger than {limit} bytes.")
    chunks, size = [], 0
    async for chunk in request.stream():  # also protects chunked uploads
        size += len(chunk)
        if size > limit:
            raise AppError(413, "payload_too_large", f"Import is larger than {limit} bytes.")
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise AppError(400, "invalid_json", "The uploaded file is not valid UTF-8 JSON.") from None


def _make(kind: str):
    async def endpoint(request: Request, auth: Auth = Depends(require_session)):
        payload = await read_limited_json(request, auth.settings.max_import_bytes)
        normalized = NORMALIZERS[kind](payload)  # raises 422 for unknown structures
        extra: dict = {}
        if kind == "attendance":  # immutable baseline + fingerprint (idempotent re-imports)
            extra = store_attendance_import(auth, payload, normalized)
        ts = save_import(auth, kind, normalized)
        if kind == "timetable":  # also keep the dated sessions (needed for forecasts); silently skipped if the file is weekly-only
            try:
                save_import(auth, SESSIONS_KIND, NORMALIZERS[SESSIONS_KIND](payload))
            except AppError:
                delete_import(auth, SESSIONS_KIND)
        count = len(normalized) if isinstance(normalized, list) else 1
        return {"kind": kind, "count": count, "source": "imported", "imported_at": ts, **extra}

    endpoint.__name__ = f"import_{kind}"
    return endpoint


for _k in KINDS:
    router.add_api_route(f"/{_k}", _make(_k), methods=["POST"], summary=f"Import {_k} JSON (your account only)")


@router.get("/status")
def status(auth: Auth = Depends(require_session)):
    return {"imports": list_imports(auth)}


@router.delete("/{kind}")
def remove(kind: str, auth: Auth = Depends(require_session)):
    if kind not in KINDS:
        raise AppError(404, "not_found", "Unknown import kind.")
    if kind == "timetable":
        delete_import(auth, SESSIONS_KIND)
    if kind == "attendance":
        delete_attendance_imports(auth)
    return {"kind": kind, "deleted": delete_import(auth, kind)}
