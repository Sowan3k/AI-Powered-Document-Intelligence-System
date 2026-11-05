"""Skip a model that just failed, while a fallback exists (D67).

When a model still fails after all of its retries (an overload, a quota or a
timeout), the next page should not spend another minute retrying it. The
breaker remembers the failure for a few minutes, and the fallback chains
(vision, D44; extraction, D61) go straight to the next model. The last model
of a chain is always tried, so the breaker can only shorten a wait, never
turn a slow success into a failure. State lives in the worker process.
"""

import threading
import time

SKIP_FAILING_MODEL_S = 300.0


class ModelBreaker:
    def __init__(self, cooldown_s: float = SKIP_FAILING_MODEL_S) -> None:
        self.cooldown_s = cooldown_s
        self._open_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_open(self, model: str) -> bool:
        with self._lock:
            until = self._open_until.get(model)
            if until is None:
                return False
            if time.monotonic() >= until:
                del self._open_until[model]  # cooled down: try it again
                return False
            return True

    def failed(self, model: str) -> None:
        with self._lock:
            self._open_until[model] = time.monotonic() + self.cooldown_s

    def succeeded(self, model: str) -> None:
        with self._lock:
            self._open_until.pop(model, None)

    def usable(self, models: list[str]) -> list[str]:
        """The chain without models that just failed; the last one always stays."""
        if not models:
            return []
        kept = [m for m in models[:-1] if not self.is_open(m)]
        return [*kept, models[-1]]

    def reset(self) -> None:
        with self._lock:
            self._open_until.clear()


BREAKER = ModelBreaker()
