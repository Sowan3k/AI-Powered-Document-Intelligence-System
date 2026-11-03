"""Worker process entry point: python -m app.worker.main

The worker runs beside the API in the same container (DECISIONS.md D03).
Phase 0 provides the loop and clean shutdown. Phase 4 adds job claiming with
FOR UPDATE SKIP LOCKED, heartbeats and stale-job recovery in `run_once`.
"""

import logging
import os
import signal
import socket
import threading
from collections.abc import Callable
from types import FrameType

from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger("app.worker")


class Worker:
    def __init__(self, poll_interval_s: float, worker_id: str | None = None) -> None:
        self.poll_interval_s = poll_interval_s
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self._stop = threading.Event()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def stop(self, signum: int | None = None, _frame: FrameType | None = None) -> None:
        if signum is not None:
            logger.info("worker %s received signal %s, stopping", self.worker_id, signum)
        self._stop.set()

    def run_once(self) -> bool:
        """Claim and run one job. Return True if a job ran.

        No job types exist yet, so there is never work to do.
        """
        return False

    def run(self) -> None:
        logger.info("worker %s started, polling every %.1fs", self.worker_id, self.poll_interval_s)
        while not self._stop.is_set():
            try:
                did_work = self.run_once()
            except Exception:
                # One bad job must not kill the loop. Phase 4 records the error on the job.
                logger.exception("worker %s: unexpected error in run_once", self.worker_id)
                did_work = False
            if not did_work:
                self._stop.wait(self.poll_interval_s)
        logger.info("worker %s stopped", self.worker_id)


def install_signal_handlers(handler: Callable[[int, FrameType | None], None]) -> None:
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker = Worker(poll_interval_s=settings.worker_poll_interval_s)
    install_signal_handlers(worker.stop)
    worker.run()


if __name__ == "__main__":
    main()
