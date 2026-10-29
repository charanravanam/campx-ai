"""'Today' / 'next class' logic (pure; the clock is passed in so it is testable)."""
from __future__ import annotations

from datetime import datetime
from typing import Any


def today_view(entries: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    day = now.strftime("%A")
    hhmm = now.strftime("%H:%M")
    todays = [e for e in entries if e["day"] == day]
    todays.sort(key=lambda e: (e["start"] or "99:99", e["end"] or "99:99"))

    def is_class(e): return e["kind"] == "class"

    current = next((e for e in todays if is_class(e) and e["start"] and e["end"] and e["start"] <= hhmm < e["end"]), None)
    upcoming = [e for e in todays if is_class(e) and e["start"] and e["start"] > hhmm]
    return {
        "day": day,
        "time": hhmm,
        "entries": todays,
        "class_count": sum(1 for e in todays if is_class(e)),
        "current_class": current,
        "next_class": upcoming[0] if upcoming else None,
        "upcoming": upcoming,
    }
