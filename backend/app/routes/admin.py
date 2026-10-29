"""Admin endpoints: separate credential (X-Admin-Token), never cookie based, disabled unless ADMIN_TOKEN is set."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Request

from ..db import connect
from ..deps import settings_of
from ..errors import AppError


def require_admin(request: Request) -> None:
    s = settings_of(request)
    if not s.admin_token:
        raise AppError(404, "not_found", "Not found.")  # pretend it does not exist
    given = request.headers.get("x-admin-token", "")
    if not hmac.compare_digest(given.encode(), s.admin_token.encode()):
        raise AppError(401, "admin_unauthorized", "Invalid admin credential.")


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/stats")
def stats(request: Request):
    store = request.app.state.store
    with connect(settings_of(request).database_file) as c:
        imports = c.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
    return {"active_sessions": store.count_active(), "import_rows": imports}


@router.post("/purge-expired")
def purge(request: Request):
    return {"purged": request.app.state.store.purge_expired()}


@router.post("/revoke-all")
def revoke_all(request: Request):
    """Emergency: log every student out (e.g. after a suspected leak or secret rotation)."""
    with connect(settings_of(request).database_file) as c:
        n = c.execute("DELETE FROM sessions").rowcount
    return {"revoked": n}
