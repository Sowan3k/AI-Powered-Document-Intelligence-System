"""The job queue on Postgres: SKIP LOCKED, heartbeats, stale recovery, backoff."""

import contextlib
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import JobStatus
from app.db.models import Document, Job, ProcessingEvent
from app.extract.llm import LlmError, LlmOutputError
from app.storage import StorageError
from app.worker import queue
from app.worker.main import Worker, describe, is_retryable


def make_document(session: Session) -> Document:
    doc = Document(id=uuid.uuid4(), filename="q.pdf", sha256="0" * 64, size_bytes=1)
    session.add(doc)
    session.flush()
    return doc


def test_skip_locked_gives_two_workers_different_jobs(engine: Engine) -> None:
    settings = Settings()
    with Session(engine) as setup:
        doc = make_document(setup)
        first = queue.enqueue(setup, doc.id, queue.JOB_PROCESS, settings)
        second = queue.enqueue(setup, doc.id, queue.JOB_PROCESS, settings)
        setup.execute(
            text("UPDATE jobs SET run_after = now() - interval '1 minute' WHERE id = :id"),
            {"id": first.id},
        )
        setup.commit()
        doc_id, first_id, second_id = doc.id, first.id, second.id
    try:
        with engine.connect() as holder:
            # Worker A has locked the oldest job and not committed yet.
            holder.begin()
            locked = holder.execute(
                text(
                    "SELECT id FROM jobs WHERE status = 'queued' ORDER BY run_after "
                    "LIMIT 1 FOR UPDATE SKIP LOCKED"
                )
            ).scalar()
            assert locked == first_id
            # Worker B does not wait for A; it takes the next job.
            with Session(engine) as b:
                claimed = queue.claim(b, "worker-b")
                assert claimed is not None and claimed.id == second_id
                assert claimed.status is JobStatus.RUNNING and claimed.attempts == 1
            holder.rollback()
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(Document).where(Document.id == doc_id))
            cleanup.commit()


def test_empty_queue(db: Session) -> None:
    assert queue.claim(db, "w") is None


def test_stale_running_job_is_requeued(db: Session) -> None:
    settings = Settings(stale_job_s=60)
    doc = make_document(db)
    job = queue.enqueue(db, doc.id, queue.JOB_PROCESS, settings)
    db.flush()
    job.status, job.attempts, job.locked_by = JobStatus.RUNNING, 1, "dead-worker"
    job.heartbeat_at = func.now() - timedelta(minutes=5)
    fresh = queue.enqueue(db, doc.id, queue.JOB_INDEX, settings)
    fresh.status, fresh.attempts, fresh.heartbeat_at = JobStatus.RUNNING, 1, func.now()
    db.flush()
    assert queue.recover_stale(db, settings) == 1
    db.refresh(job)
    db.refresh(fresh)
    assert job.status is JobStatus.QUEUED and job.locked_by is None
    assert job.last_error == "the worker stopped while running this job"
    assert fresh.status is JobStatus.RUNNING  # its worker is alive


def test_stale_job_out_of_attempts_fails(db: Session) -> None:
    settings = Settings(stale_job_s=60)
    job = queue.enqueue(db, make_document(db).id, queue.JOB_PROCESS, settings)
    job.status, job.attempts = JobStatus.RUNNING, job.max_attempts
    job.heartbeat_at = func.now() - timedelta(minutes=5)
    db.flush()
    queue.recover_stale(db, settings)
    db.refresh(job)
    assert job.status is JobStatus.FAILED


def test_heartbeat_only_for_the_owner(db: Session) -> None:
    job = queue.enqueue(db, make_document(db).id, queue.JOB_PROCESS, Settings())
    db.flush()
    claimed = queue.claim(db, "me")
    assert claimed is not None
    assert queue.heartbeat(db, job.id, "me") is True
    assert queue.heartbeat(db, job.id, "someone-else") is False


def test_backoff_doubles(db: Session) -> None:
    settings = Settings(job_backoff_s=30)
    job = queue.enqueue(db, make_document(db).id, queue.JOB_PROCESS, settings)
    db.flush()
    delays = []
    for attempt in (1, 2):
        job.attempts = attempt
        queue.fail(db, job, "LlmError: busy", retryable=True, settings=settings)
        delays.append(
            db.scalars(
                select(ProcessingEvent.detail)
                .where(
                    ProcessingEvent.job_id == job.id, ProcessingEvent.event == "job_retry_scheduled"
                )
                .order_by(ProcessingEvent.id.desc())
            ).first()["delay_s"]
        )
    assert delays == [30, 60]
    job.attempts = 3
    queue.fail(db, job, "LlmError: busy", retryable=True, settings=settings)
    assert job.status is JobStatus.FAILED


def test_unknown_job_type_fails_for_good(db: Session) -> None:
    doc = make_document(db)
    db.add(Job(document_id=doc.id, job_type="mystery", max_attempts=3))
    db.flush()
    worker = Worker(0.01, sessions=lambda: contextlib.nullcontext(db), heartbeats=False)
    assert worker.run_once() is True
    job = db.scalars(select(Job).where(Job.document_id == doc.id)).one()
    assert job.status is JobStatus.FAILED and job.attempts == 1
    assert "unknown job type" in job.last_error


@pytest.mark.parametrize(
    ("exc", "retryable"),
    [
        (LlmError("Gemini call failed with HTTP 503"), True),
        (LlmOutputError("embedding reply had the wrong shape"), False),
        (StorageError("storage download failed with HTTP 500"), True),
        (OperationalError("SELECT", {}, Exception("gone")), True),
        (RuntimeError("GEMINI_API_KEY must be set"), False),
        (ValueError("unknown job type"), False),
        (KeyError("surprise"), True),
    ],
)
def test_retry_classification(exc: Exception, retryable: bool) -> None:
    assert is_retryable(exc) is retryable


def test_error_messages_from_unknown_errors_are_not_stored() -> None:
    assert describe(KeyError("Acme Traders total 130.20")) == "KeyError"
    assert describe(LlmError("Gemini call failed with HTTP 503")).endswith("HTTP 503")
