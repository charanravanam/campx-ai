"""Attendance maths (pure functions, integer arithmetic where it matters)."""
from __future__ import annotations

from typing import Any

DEFAULT_TARGET = 75


def classes_needed(attended: int, total: int, target: int) -> int | None:
    """Smallest n >= 0 such that (attended+n)/(total+n) >= target/100, attending all n.

    Derivation: (a+n)*100 >= T*(t+n)  =>  n*(100-T) >= T*t - 100*a.
    Returns None when impossible (target 100 and any class already missed).
    """
    need = target * total - 100 * attended
    if need <= 0:
        return 0
    if target >= 100:
        return None
    den = 100 - target
    return -(-need // den)  # ceiling division


def classes_can_miss(attended: int, total: int, target: int) -> int:
    """Largest s >= 0 such that attended/(total+s) >= target/100 (missing s more classes)."""
    if target <= 0:
        return 0
    slack = 100 * attended - target * total
    if slack < 0:
        return 0
    return slack // target


def percentage(attended: int, total: int) -> float | None:
    return round(attended * 100 / total, 2) if total > 0 else None


def subject_row(rec: dict[str, Any], target: int) -> dict[str, Any]:
    a, t = rec.get("attended"), rec.get("total")
    row = {
        "subject_code": rec.get("subject_code"),
        "subject_name": rec.get("subject_name"),
        "attended": a,
        "total": t,
        "percentage": None,
        "percentage_basis": None,  # "counts" (we calculated) | "reported" (source gave a number only)
        "status": "unknown",
        "classes_needed": None,
        "classes_can_miss": None,
    }
    if a is not None and t is not None:
        row["percentage"] = percentage(a, t)
        row["percentage_basis"] = "counts"
        if t > 0:
            row["status"] = "ok" if a * 100 >= target * t else "low"
            row["classes_needed"] = classes_needed(a, t, target)
            row["classes_can_miss"] = classes_can_miss(a, t, target)
    elif rec.get("reported_percentage") is not None:
        row["percentage"] = rec["reported_percentage"]
        row["percentage_basis"] = "reported"
        row["status"] = "ok" if rec["reported_percentage"] >= target else "low"
    return row


def build_attendance(records: list[dict[str, Any]], target: int = DEFAULT_TARGET) -> dict[str, Any]:
    rows = [subject_row(r, target) for r in records]
    counted = [r for r in rows if r["percentage_basis"] == "counts" and r["total"]]
    overall = None
    if counted:
        a = sum(r["attended"] for r in counted)
        t = sum(r["total"] for r in counted)
        overall = {
            "attended": a,
            "total": t,
            "percentage": percentage(a, t),
            "status": "ok" if a * 100 >= target * t else "low",
            "classes_needed": classes_needed(a, t, target),
            "classes_can_miss": classes_can_miss(a, t, target),
            "subjects_counted": len(counted),
            "subjects_total": len(rows),
        }
    return {"target": target, "overall": overall, "subjects": rows}
