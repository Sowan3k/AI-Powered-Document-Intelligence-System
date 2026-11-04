"""The job queue: a PostgreSQL table claimed with FOR UPDATE SKIP LOCKED (D02).

A job moves queued -> running -> succeeded, or back to queued with a delay
for a retry, or to failed once its attempts run out or the failure is final.
Every move writes a `processing_events` row, which is the document's history.
A running job sends a heartbeat; a job whose heartbeat goes stale (its worker
died) is put back in the queue by the next worker.
"""

import logging
import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import DocumentStatus, JobStatus
from app.db.models import Document, Job, ProcessingEvent

logger = logging.getLogger(__name__)

JOB_PROCESS = "process"  # ingest, extract, validate, index
JOB_INDEX = "index"  # refresh search after a correction
ACTIVE = (JobStatus.QUEUED, JobStatus.RUNNING)


def event(session: Session, job: Job, name: str, **detail: object) -> None:
    session.add(
        ProcessingEvent(
            document_id=job.document_id, job_id=job.id, event=name, detail=detail or None
        )
    )


def enqueue(session: Session, document_id: uuid.UUID, job_type: str, settings: Settings) -> Job:
    """Add a job. Does not commit."""
    job = Job(
        id=uuid.uuid4(),
        document_id=document_id,
        job_type=job_type,
        status=JobStatus.QUEUED,
        max_attempts=settings.job_max_attempts,
    )
    session.add(job)
    session.flush()
    event(session, job, "job_queued", job_type=job_type)
    return job


def active_job(session: Session, document_id: uuid.UUID, job_type: str) -> Job | None:
    return session.scalars(
        select(Job).where(
            Job.document_id == document_id, Job.job_type == job_type, Job.status.in_(ACTIVE)
        )
    ).first()


def claim(session: Session, worker_id: str) -> Job | None:
    """Take the oldest runnable job. Two workers never get the same one."""
    job = session.scalars(
        select(Job)
        .where(Job.status == JobStatus.QUEUED, Job.run_after <= func.now())
        .order_by(Job.run_after, Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        session.rollback()
        return None
    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.locked_by = worker_id
    job.locked_at = job.heartbeat_at = func.now()
    event(session, job, "job_started", attempt=job.attempts, worker=worker_id)
    session.commit()
    session.refresh(job)
    return job


def heartbeat(session: Session, job_id: uuid.UUID, worker_id: str) -> bool:
    result = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.locked_by == worker_id, Job.status == JobStatus.RUNNING)
        .values(heartbeat_at=func.now())
    )
    session.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def succeed(session: Session, job: Job) -> None:
    job.status = JobStatus.SUCCEEDED
    job.finished_at = func.now()
    job.locked_by = None
    event(session, job, "job_succeeded", attempts=job.attempts)
    session.commit()


def fail(session: Session, job: Job, error: str, *, retryable: bool, settings: Settings) -> None:
    """Schedule a retry with exponential backoff, or fail for good."""
    job.last_error = error[:500]
    job.locked_by = None
    if retryable and job.attempts < job.max_attempts:
        delay = settings.job_backoff_s * 2 ** (job.attempts - 1)
        job.status = JobStatus.QUEUED
        job.run_after = func.now() + timedelta(seconds=delay)
        event(
            session,
            job,
            "job_retry_scheduled",
            attempt=job.attempts,
            delay_s=delay,
            error=job.last_error,
        )
        logger.info("job %s attempt %d failed, retry in %ss", job.id, job.attempts, delay)
    else:
        job.status = JobStatus.FAILED
        job.finished_at = func.now()
        event(session, job, "job_failed", attempts=job.attempts, error=job.last_error)
        document = session.get(Document, job.document_id)
        if job.job_type == JOB_PROCESS and document and document.status != DocumentStatus.FAILED:
            document.status = DocumentStatus.FAILED
            document.error_code = "JOB_FAILED"
            document.error_message = job.last_error
        logger.info("job %s failed after %d attempts", job.id, job.attempts)
    session.commit()


def recover_stale(session: Session, settings: Settings) -> int:
    """Re-queue running jobs whose worker stopped sending heartbeats."""
    cutoff = func.now() - timedelta(seconds=settings.stale_job_s)
    stale = session.scalars(
        select(Job)
        .where(Job.status == JobStatus.RUNNING, Job.heartbeat_at < cutoff)
        .with_for_update(skip_locked=True)
    ).all()
    for job in stale:
        if job.attempts < job.max_attempts:
            job.status = JobStatus.QUEUED
            job.run_after = func.now()
            outcome = "requeued"
        else:
            job.status = JobStatus.FAILED
            job.finished_at = func.now()
            outcome = "failed"
        job.last_error = "the worker stopped while running this job"
        job.locked_by = None
        event(session, job, "job_recovered", outcome=outcome, attempts=job.attempts)
    session.commit()
    if stale:
        logger.info("recovered %d stale jobs", len(stale))
    return len(stale)


def retry_failed(session: Session, job: Job) -> None:
    """A person asked to run a failed job again: fresh attempts. Commits."""
    if job.status != JobStatus.FAILED:
        raise ValueError("only a failed job can be retried")
    job.status = JobStatus.QUEUED
    job.attempts = 0
    job.run_after = func.now()
    job.finished_at = None
    event(session, job, "job_retry_requested")
    document = session.get(Document, job.document_id)
    if job.job_type == JOB_PROCESS and document is not None:
        document.status = DocumentStatus.QUEUED
        document.error_code = document.error_message = None
    session.commit()
