"""In-memory sliding-window limiter for login attempts.

Single-process only. For multiple workers/servers use a shared store such as
Redis (see SECURITY.md).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int, clock=time.monotonic):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, key: str) -> deque[float]:
        q = self._hits[key]
        cutoff = self._clock() - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def retry_after(self, key: str) -> int:
        """0 if allowed, else seconds until another attempt is allowed."""
        with self._lock:
            q = self._trim(key)
            if len(q) < self.max_attempts:
                return 0
            return max(1, int(q[0] + self.window - self._clock()) + 1)

    def hit(self, key: str) -> None:
        with self._lock:
            self._trim(key).append(self._clock())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
