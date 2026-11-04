"""Jobs: status and progress, and retry of a failed job."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.schemas import JobOut
from app.db.models import Job
from app.db.session import get_db
from app.worker import queue

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(current_user)])


def _get(db: Session, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobOut:
    """Status, attempts and progress (pages done out of the total)."""
    return JobOut.model_validate(_get(db, job_id))


@router.post(
    "/{job_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobOut,
    responses={409: {"description": "Only a failed job can be retried"}},
)
def retry_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobOut:
    job = _get(db, job_id)
    try:
        queue.retry_failed(db, job)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    db.refresh(job)
    return JobOut.model_validate(job)
