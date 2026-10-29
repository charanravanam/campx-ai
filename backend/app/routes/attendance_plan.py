"""Attendance forecasting API. Baseline (imported) is never modified; simulations live in a separate ledger."""
from __future__ import annotations

from datetime import date as Date
from typing import Any

from fastapi import APIRouter, Depends, Query

from ..attendance_engine import (EngineError, apply_outcomes, classes_can_miss, classes_needed, meets, parse_threshold,
                                 percentage, plan_recovery, project)
from ..attendance_store import active_import, clear_adjustments, list_adjustments, set_adjustment
from ..deps import Auth, require_session
from ..errors import AppError
from ..schemas import AdjustmentIn, ScenarioIn
from ..services import SESSIONS_KIND, FALLBACK_CODES, resolve
from ..session_model import subject_key
from .data import _now

router = APIRouter(prefix="/api/attendance", tags=["attendance-plan"])
DEFAULT_TARGET = 75


def _threshold(v: float):
    try:
        return parse_threshold(v)
    except EngineError as exc:
        raise AppError(422, "invalid_threshold", str(exc)) from None


def _today(auth: Auth) -> Date:
    return _now(auth.settings.app_timezone).date()


def _load_sessions(auth: Auth):
    """-> (sessions | None, notice). None = no dated timetable available."""
    try:
        r = resolve(auth, SESSIONS_KIND)
    except AppError as exc:
        if exc.status == 401:
            raise
        return None, f"Dated timetable unavailable ({exc.code})."
    return r.data, r.notice


def _units(s: dict, lab_units: str) -> int:
    return s["period_count"] if lab_units == "period" else 1


def _matches(rec: dict, s: dict) -> bool:
    keys = {k for k in (subject_key(rec.get("subject_code"), None), subject_key(None, rec.get("subject_name"))) if k}
    return s["subject_key"] in keys or (s.get("subject_code") or "").strip().lower() in keys or (s.get("subject_name") or "").strip().lower() in keys


def _bundle(auth: Auth, target: float, lab_units: str) -> dict[str, Any]:
    p = _threshold(target)
    if lab_units not in ("session", "period"):
        raise AppError(422, "invalid_lab_units", "lab_units must be 'session' or 'period'.")
    r = resolve(auth, "attendance")
    base: dict[str, Any] = {"target": target, "source": r.source, "notice": r.notice, "subjects": [], "overall": None,
                            "adjustments_enabled": False, "lab_units": lab_units, "import": None, "p": p}
    if r.source == "none" or not r.data:
        return base
    imp, adj = None, {}
    if r.source == "imported":
        imp = active_import(auth)
        if imp is None:
            return base
        records, adj = imp["records"], list_adjustments(auth, imp["id"])
        base["adjustments_enabled"] = True
        base["import"] = {"id": imp["id"], "fingerprint": imp["fingerprint"][:12], "imported_at": imp["created_at"]}
        label = "Imported JSON"
    else:
        records, label = r.data, "Official CampX"
    sessions, snotice = _load_sessions(auth)
    today = _today(auth).isoformat()
    by_key = {s["session_key"]: s for s in (sessions or [])}
    used_adj: set[str] = set()
    out = []
    for rec in records:
        skey = subject_key(rec.get("subject_code"), rec.get("subject_name"))
        row: dict[str, Any] = {"subject_key": skey, "subject_code": rec.get("subject_code"), "subject_name": rec.get("subject_name"),
                               "source_label": label, "notes": []}
        a, t = rec.get("attended"), rec.get("total")
        if a is None or t is None:
            row.update(status="no_counts", baseline=None, simulated=None, recovery={"state": "no_counts"}, upcoming=[])
            row["notes"].append("This record has a percentage but no class counts, so no projection is possible.")
            out.append(row); continue
        mine = [s for s in (sessions or []) if _matches(rec, s)]
        upcoming = [s for s in mine if s["date"] >= today and not s["completed"] and not s["suspended"] and s["counts_for_attendance"] is not False]
        marks = [(k, v) for k, v in adj.items() if k in by_key and _matches(rec, by_key[k])]
        used_adj.update(k for k, _ in marks)
        sa, st = apply_outcomes(a, t, [(v["status"], _units(by_key[k], lab_units)) for k, v in marks])
        marked = {k for k, _ in marks}
        confirmed = [s for s in upcoming if not s["groups"] and s["session_key"] not in marked]
        ambiguous = [s for s in upcoming if s["groups"] and s["session_key"] not in marked]
        rec_plan = plan_recovery(sa, st, p, None if sessions is None else [{"date": s["date"], "start": s["start"], "session_key": s["session_key"], "units": _units(s, lab_units)} for s in confirmed])
        if any(s["period_count"] > 1 for s in mine):
            row["notes"].append("Some sessions span several periods. How many classes the institution counts for them is unverified, so recovery dates are approximate. Use ?lab_units=period to test the alternative.")
        if ambiguous:
            row["notes"].append(f"{len(ambiguous)} upcoming lab-batch session(s) are not counted until you mark them (your batch is not identifiable from the timetable).")
        if rec_plan["state"] == "insufficient_sessions":
            row["notes"].append("The timetable does not contain enough upcoming sessions to reach the target; no date is estimated.")
        simulated = bool(marks)
        row.update(
            status="ok" if meets(sa, st, p) else "low" if st else "unknown",
            baseline={"attended": a, "total": t, "missed": t - a, "percentage": percentage(a, t), "source_label": label},
            simulated={"attended": sa, "total": st, "missed": st - sa, "percentage": percentage(sa, st), "source_label": "Student Simulation" if simulated else label},
            has_simulation=simulated,
            classes_needed=classes_needed(sa, st, p), classes_can_miss=classes_can_miss(sa, st, p),
            recovery=rec_plan,
            upcoming=[{"session_key": s["session_key"], "date": s["date"], "start": s["start"], "end": s["end"], "kind": s["kind"],
                       "period_count": s["period_count"], "groups": s["groups"], "units": _units(s, lab_units),
                       "simulated_status": adj[s["session_key"]]["status"] if s["session_key"] in adj else None,
                       "needs_confirmation": bool(s["groups"])} for s in sorted(upcoming, key=lambda s: (s["date"], s["start"] or ""))],
        )
        out.append(row)
    if sessions is None:
        base["notice"] = " ".join(x for x in (base["notice"], snotice, "No dated timetable is available, so recovery dates cannot be estimated.") if x)
    orphans = [k for k in adj if k not in used_adj]
    base.update(subjects=out, orphaned_adjustments=len(orphans))
    counted = [x for x in out if x.get("simulated")]
    if counted:
        a = sum(x["simulated"]["attended"] for x in counted); t = sum(x["simulated"]["total"] for x in counted)
        base["overall"] = {"attended": a, "total": t, "percentage": percentage(a, t), "status": "ok" if meets(a, t, p) else "low",
                           "classes_needed": classes_needed(a, t, p), "subjects_counted": len(counted), "subjects_total": len(out)}
    return base


def _public(b: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in b.items() if k != "p"}


@router.get("/forecast")
def forecast(target: float = Query(DEFAULT_TARGET, gt=0, lt=100), lab_units: str = Query("session"), auth: Auth = Depends(require_session)):
    return _public(_bundle(auth, target, lab_units))


@router.post("/adjustments")
def put_adjustment(body: AdjustmentIn, auth: Auth = Depends(require_session)):
    r = resolve(auth, "attendance")
    imp = active_import(auth) if r.source == "imported" else None
    if imp is None:
        raise AppError(409, "no_editable_baseline", "Simulations need an imported attendance baseline.")
    sessions, _ = _load_sessions(auth)
    s = next((x for x in (sessions or []) if x["session_key"] == body.session_key), None)
    if s is None:
        raise AppError(404, "session_not_found", "That session is not in your timetable.")
    if s["subject_key"] != body.subject_key and body.subject_key not in {(s.get("subject_code") or "").lower(), (s.get("subject_name") or "").lower()}:
        raise AppError(422, "subject_mismatch", "That session belongs to a different subject.")
    if s["date"] < _today(auth).isoformat() or s["completed"] or s["suspended"]:
        raise AppError(422, "session_not_upcoming", "Only upcoming, unsuspended sessions can be simulated.")
    if not any(subject_key(x.get("subject_code"), x.get("subject_name")) == body.subject_key for x in imp["records"]):
        raise AppError(404, "subject_not_found", "That subject is not in your imported attendance.")
    set_adjustment(auth, imp["id"], body.subject_key, body.session_key, body.status)
    return {"saved": True, "session_key": body.session_key, "status": body.status}


@router.delete("/adjustments")
def reset_adjustments(subject_key_: str | None = Query(None, alias="subject_key"), session_key: str | None = Query(None), auth: Auth = Depends(require_session)):
    imp = active_import(auth)
    return {"cleared": clear_adjustments(auth, imp["id"], session_key, subject_key_) if imp else 0}


@router.post("/scenario")
def scenario(body: ScenarioIn, lab_units: str = Query("session"), auth: Auth = Depends(require_session)):
    """Stateless what-if on top of baseline + saved simulations. Writes nothing."""
    b = _bundle(auth, body.target or DEFAULT_TARGET, lab_units)
    row = next((x for x in b["subjects"] if x["subject_key"] == body.subject_key), None)
    if row is None:
        raise AppError(404, "subject_not_found", "Unknown subject.")
    if row.get("simulated") is None:
        raise AppError(422, "no_counts", "This subject has no class counts.")
    attend = body.sequence.count("present") if body.sequence is not None else body.attend
    miss = body.sequence.count("absent") if body.sequence is not None else body.miss
    cur = row["simulated"]
    res = project(cur["attended"], cur["total"], attend, miss)
    p = b["p"]
    return {"subject_key": body.subject_key, "persisted": False, "target": b["target"], "from": cur,
            "scenario": {"attend": attend, "miss": miss}, "projected": res,
            "meets_target": meets(res["attended"], res["total"], p),
            "classes_needed": classes_needed(res["attended"], res["total"], p),
            "classes_can_miss": classes_can_miss(res["attended"], res["total"], p)}
