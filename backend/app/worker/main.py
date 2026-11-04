"""Worker process entry point: python -m app.worker.main

The worker runs beside the API in the same container (D03). Each turn of the
loop claims one job with FOR UPDATE SKIP LOCKED, runs it while a background
thread sends heartbeats, and records the outcome. On start, and every minute
after, it re-queues jobs whose worker died (stale heartbeat).
"""

import contextlib
import logging
import os
import signal
import socket
import threading
import time
from collections.abc import Callable
from types import FrameType

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.extract.llm import LlmClient, LlmError
from app.storage import FileStorage, StorageError
from app.worker import queue
from app.worker.pipeline import process_document, reindex

logger = logging.getLogger("app.worker")

SessionFactory = Callable[[], contextlib.AbstractContextManager[Session]]
RECOVERY_INTERVAL_S = 60
# Errors raised by DocIntel's own code carry safe messages. For anything
# else, only the type name is stored, since a message could hold document data.
SAFE_MESSAGES = (LlmError, StorageError, RuntimeError, ValueError)


def describe(exc: Exception) -> str:
    if isinstance(exc, SAFE_MESSAGES):
        return f"{type(exc).__name__}: {exc}"
    return type(exc).__name__


def is_retryable(exc: Exception) -> bool:
    """Network, storage, quota and database errors pass; missing settings never do."""
    if isinstance(exc, LlmError | StorageError | OperationalError):
        return True
    return not isinstance(exc, RuntimeError | ValueError)


class Heartbeat:
    """Touches the job's heartbeat on its own session while the job runs."""

    def __init__(self, sessions: SessionFactory, job_id, worker_id: str, interval_s: float) -> None:  # type: ignore[no-untyped-def]
        self._sessions, self._job_id, self._worker_id = sessions, job_id, worker_id
        self._interval_s = interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self._interval_s):
            try:
                with self._sessions() as session:
                    queue.heartbeat(session, self._job_id, self._worker_id)
            except Exception as exc:
                logger.warning("heartbeat for job %s failed: %s", self._job_id, type(exc).__name__)

    def __enter__(self) -> "Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


class Worker:
    def __init__(
        self,
        poll_interval_s: float,
        worker_id: str | None = None,
        *,
        sessions: SessionFactory | None = None,
        storage: FileStorage | None = None,
        llm: LlmClient | None = None,
        settings: Settings | None = None,
        heartbeats: bool = True,
    ) -> None:
        self.poll_interval_s = poll_interval_s
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self._stop = threading.Event()
        self.sessions = sessions
        self.storage = storage
        self.llm = llm
        self.settings = settings or get_settings()
        self.heartbeats = heartbeats
        self._last_recovery = 0.0

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def stop(self, signum: int | None = None, _frame: FrameType | None = None) -> None:
        if signum is not None:
            logger.info("worker %s received signal %s, stopping", self.worker_id, signum)
        self._stop.set()

    def recover(self) -> int:
        if self.sessions is None:
            return 0
        self._last_recovery = time.monotonic()
        with self.sessions() as session:
            return queue.recover_stale(session, self.settings)

    def run_once(self) -> bool:
        """Claim and run one job. Return True if a job ran."""
        if self.sessions is None:
            return False
        if time.monotonic() - self._last_recovery > RECOVERY_INTERVAL_S:
            self.recover()
        with self.sessions() as session:
            job = queue.claim(session, self.worker_id)
            if job is None:
                return False
            logger.info("job %s (%s) started, attempt %d", job.id, job.job_type, job.attempts)
            beat = (
                Heartbeat(self.sessions, job.id, self.worker_id, self.settings.heartbeat_interval_s)
                if self.heartbeats
                else contextlib.nullcontext()
            )
            try:
                with beat:
                    outcome = self._run(session, job)
            except Exception as exc:
                session.rollback()
                logger.warning("job %s failed: %s", job.id, type(exc).__name__)
                queue.fail(
                    session, job, describe(exc), retryable=is_retryable(exc), settings=self.settings
                )
                return True
            if outcome.ok:
                queue.succeed(session, job)
            else:
                # The file or the model's output failed in a way a retry cannot fix.
                queue.fail(
                    session,
                    job,
                    outcome.error_code or "FAILED",
                    retryable=False,
                    settings=self.settings,
                )
            return True

    def _run(self, session: Session, job):  # type: ignore[no-untyped-def]
        if job.job_type == queue.JOB_PROCESS:
            if self.storage is None:
                raise RuntimeError("no file storage is configured")
            return process_document(
                session, self.storage, self.llm, job.document_id, self.settings, job
            )
        if job.job_type == queue.JOB_INDEX:
            return reindex(session, self.llm, job.document_id, self.settings, job)
        raise ValueError(f"unknown job type {job.job_type!r}")

    def run(self) -> None:
        logger.info("worker %s started, polling every %.1fs", self.worker_id, self.poll_interval_s)
        while not self._stop.is_set():
            try:
                did_work = self.run_once()
            except Exception:
                # One bad turn must not kill the loop (for example, the database is briefly away).
                logger.exception("worker %s: unexpected error in run_once", self.worker_id)
                did_work = False
            if not did_work:
                self._stop.wait(self.poll_interval_s)
        logger.info("worker %s stopped", self.worker_id)


def install_signal_handlers(handler: Callable[[int, FrameType | None], None]) -> None:
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def build_worker(settings: Settings) -> Worker:
    from app.db.session import get_sessionmaker
    from app.extract.llm import get_llm_client
    from app.storage import get_storage

    llm = get_llm_client(settings) if settings.gemini_api_key else None
    if llm is None:
        logger.warning("GEMINI_API_KEY is not set: documents will fail at extraction")
    return Worker(
        poll_interval_s=settings.worker_poll_interval_s,
        sessions=get_sessionmaker(),
        storage=get_storage(settings),
        llm=llm,
        settings=settings,
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker = build_worker(settings)
    install_signal_handlers(worker.stop)
    worker.recover()
    worker.run()


if __name__ == "__main__":
    main()
