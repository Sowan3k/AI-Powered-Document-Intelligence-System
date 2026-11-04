"""A small in-memory sliding-window rate limiter, per client IP (security rule 7).

One Render instance runs one API process, so memory is the right place. With
several instances the counts would need a shared store (D46).
"""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, window_s: float = 60) -> None:
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int) -> float | None:
        """Record a request. Returns None if allowed, else seconds until the next slot."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window_s:
                hits.popleft()
            if len(hits) >= limit:
                return max(0.0, hits[0] + self.window_s - now)
            hits.append(now)
            if len(self._hits) > 10_000:  # forget idle clients so memory stays bounded
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_limiter = RateLimiter()
upload_limiter = RateLimiter()
