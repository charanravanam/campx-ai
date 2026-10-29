"""Attendance forecasting maths. Pure functions, exact arithmetic, no I/O.

Conventions
-----------
* A = classes attended, T = classes conducted, p = required fraction (0 < p < 1).
* p is held as a ``fractions.Fraction`` so threshold comparisons never suffer
  floating-point error. Percentages shown to people are for display only; every
  decision uses the integer counts.
* T == 0 means "undefined": functions return None instead of a misleading 0%/100%.

Formulas (p = pn/pd):
    meets threshold      A*pd >= pn*T
    attend n in a row    (A+n)/(T+n) >= p   =>   n = max(0, ceil((pn*T - pd*A) / (pd - pn)))
    can miss s classes   A/(T+s) >= p       =>   s = max(0, floor((pd*A - pn*T) / pn))
"""
from __future__ import annotations

from datetime import date as Date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Iterable, Sequence


class EngineError(ValueError):
    """Invalid input to the engine (bad counts, bad threshold...)."""


# ------------------------------------------------------------------ validation
def parse_threshold(percent: Any) -> Fraction:
    """'75' / 75 / 82.5 -> Fraction(3, 4) etc. Rejects bools, NaN and anything outside (0, 100)."""
    if isinstance(percent, bool):
        raise EngineError("Threshold must be a number.")
    try:
        d = Decimal(str(percent).strip())
    except (InvalidOperation, ValueError):
        raise EngineError("Threshold must be a number.") from None
    if not d.is_finite() or not (Decimal(0) < d < Decimal(100)):
        raise EngineError("Threshold must be greater than 0 and less than 100 percent.")
    return Fraction(d) / 100


def validate_counts(attended: Any, total: Any) -> tuple[int, int]:
    for name, v in (("attended", attended), ("total", total)):
        if isinstance(v, bool) or not isinstance(v, int):
            raise EngineError(f"{name} must be a whole number.")
        if v < 0:
            raise EngineError(f"{name} cannot be negative.")
    if attended > total:
        raise EngineError("attended cannot exceed total.")
    return attended, total


# ------------------------------------------------------------------ core maths
def percentage(attended: int, total: int) -> float | None:
    """Display-only percentage rounded half-up to 2 places; None when total == 0."""
    validate_counts(attended, total)
    if total == 0:
        return None
    q = (Decimal(attended) * 100 / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(q)


def meets(attended: int, total: int, p: Fraction) -> bool | None:
    validate_counts(attended, total)
    if total == 0:
        return None
    return attended * p.denominator >= p.numerator * total


def classes_needed(attended: int, total: int, p: Fraction) -> int | None:
    """Fewest consecutive classes to attend so that attendance >= p. 0 if already met; None if T == 0."""
    validate_counts(attended, total)
    if total == 0:
        return None
    num = p.numerator * total - p.denominator * attended
    if num <= 0:
        return 0
    den = p.denominator - p.numerator  # > 0 because p < 1
    return -(-num // den)


def classes_can_miss(attended: int, total: int, p: Fraction) -> int | None:
    """Most future classes that can be missed while staying >= p (0 if already below); None if T == 0."""
    validate_counts(attended, total)
    if total == 0:
        return None
    slack = attended * p.denominator - p.numerator * total
    return 0 if slack < 0 else slack // p.numerator


def project(attended: int, total: int, attend: int, miss: int) -> dict[str, Any]:
    """Counts after attending `attend` and missing `miss` further classes."""
    validate_counts(attended, total)
    for name, v in (("attend", attend), ("miss", miss)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise EngineError(f"{name} must be a non-negative whole number.")
    a, t = attended + attend, total + attend + miss
    return {"attended": a, "total": t, "missed": t - a, "percentage": percentage(a, t)}


# ------------------------------------------------------------ recovery planning
def plan_recovery(
    attended: int,
    total: int,
    p: Fraction,
    upcoming: Sequence[dict[str, Any]] | None,
) -> dict[str, Any]:
    """When does the student first reach p, attending every listed upcoming session?

    ``upcoming`` items: {"date": "YYYY-MM-DD", "units": int>=1, ...} in any order.
    ``None`` means no timetable is available at all (different from an empty list).
    Never extrapolates past the supplied sessions.
    """
    validate_counts(attended, total)
    if total == 0:
        return {"state": "no_baseline", "needed": None}
    needed = classes_needed(attended, total, p)
    if needed == 0:
        return {"state": "already_met", "needed": 0}
    if upcoming is None:
        return {"state": "no_timetable", "needed": needed}
    ordered = sorted(upcoming, key=lambda s: (s["date"], s.get("start") or "", str(s.get("session_key", ""))))
    a, t = attended, total
    for i, s in enumerate(ordered, start=1):
        u = int(s.get("units", 1))
        if u < 1:
            raise EngineError("A session must count for at least one class.")
        a, t = a + u, t + u
        if a * p.denominator >= p.numerator * t:
            return {"state": "date", "needed": needed, "date": s["date"], "sessions_used": i, "units_used": a - attended}
    return {
        "state": "insufficient_sessions",
        "needed": needed,
        "available_sessions": len(ordered),
        "available_units": sum(int(s.get("units", 1)) for s in ordered),
    }


def apply_outcomes(
    attended: int,
    total: int,
    outcomes: Iterable[tuple[str, int]],
) -> tuple[int, int]:
    """Fold simulated outcomes (status, units) into a baseline. status: 'present' | 'absent'."""
    validate_counts(attended, total)
    a, t = attended, total
    for status, units in outcomes:
        if status not in ("present", "absent"):
            raise EngineError("status must be 'present' or 'absent'.")
        a += units if status == "present" else 0
        t += units
    return a, t


def today_iso(d: Date) -> str:
    return d.isoformat()
