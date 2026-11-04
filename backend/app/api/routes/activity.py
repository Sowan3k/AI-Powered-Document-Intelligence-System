"""GET /api/activity: what is processing now, for the live progress dock.

Each document's stage comes from its latest processing event, so the web app
can show it moving through Upload, Read, AI extract, Check and Done. One call
returns everything the dock needs, so polling it every few seconds is cheap.
"""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.enums import DocumentStatus, ReviewStatus
from app.db.models import Document, Invoice, Job, ProcessingEvent
from app.db.session import get_db

router = APIRouter(tags=["activity"], dependencies=[Depends(current_user)])

# The step each event belongs to. Model calls are not steps.
STAGE_OF_EVENT = {
    "uploaded": "queued",
    "job_queued": "queued",
    "job_retry_scheduled": "queued",
    "job_retry_requested": "queued",
    "job_recovered": "queued",
    "job_started": "reading",
    "ingest_started": "reading",
    "ingested": "extracting",
    "extract_started": "extracting",
    "extract_windows": "extracting",
    "vision_page": "extracting",
    "vision_failed": "extracting",
    "extracted": "checking",
    "validated": "indexing",
    "completed": "done",
    "job_succeeded": "done",
    "rejected": "failed",
    "ingest_failed": "failed",
    "extract_failed": "failed",
    "job_failed": "failed",
}
STAGE_LABELS = {
    "queued": "Waiting in line",
    "reading": "Reading pages",
    "extracting": "AI is extracting the fields",
    "checking": "Checking the numbers",
    "indexing": "Making it searchable",
    "done": "Done",
    "failed": "Failed",
}


class ActivityItem(BaseModel):
    document_id: uuid.UUID
    filename: str
    status: DocumentStatus
    stage: str
    stage_label: str
    progress_done: int
    progress_total: int | None
    progress_unit: str | None  # "pages" while reading, "windows" while extracting
    attempts: int
    invoice_count: int
    needs_review: int
    error_code: str | None
    updated_at: datetime


class ActivityResponse(BaseModel):
    active: list[ActivityItem]
    recent: list[ActivityItem]
    review_count: int


def _stage(doc: Document, event: str | None) -> str:
    if doc.status is DocumentStatus.FAILED:
        return "failed"
    if doc.status is DocumentStatus.COMPLETED:
        return "done"
    return STAGE_OF_EVENT.get(event or "", "queued")


@router.get("/activity", response_model=ActivityResponse)
def activity(
    recent_minutes: int = Query(15, ge=1, le=1440),
    db: Session = Depends(get_db),
) -> ActivityResponse:
    since = func.now() - timedelta(minutes=recent_minutes)
    docs = db.scalars(
        select(Document)
        .where(
            or_(
                Document.status.in_((DocumentStatus.QUEUED, DocumentStatus.PROCESSING)),
                Document.updated_at >= since,
            )
        )
        .order_by(Document.created_at.desc())
        .limit(50)
    ).all()
    ids = [d.id for d in docs]
    events: dict[uuid.UUID, str] = {}
    jobs: dict[uuid.UUID, Job] = {}
    counts: dict[uuid.UUID, tuple[int, int]] = {}
    if ids:
        latest = (
            select(ProcessingEvent.document_id, ProcessingEvent.event)
            .where(ProcessingEvent.document_id.in_(ids), ProcessingEvent.event != "llm_call")
            .distinct(ProcessingEvent.document_id)
            .order_by(ProcessingEvent.document_id, ProcessingEvent.id.desc())
        )
        events = dict(db.execute(latest).all())
        for job in db.scalars(
            select(Job)
            .where(Job.document_id.in_(ids), Job.job_type == "process")
            .order_by(Job.created_at)
        ):
            jobs[job.document_id] = job
        for doc_id, total, review in db.execute(
            select(
                Invoice.document_id,
                func.count(),
                func.count().filter(Invoice.review_status == ReviewStatus.NEEDS_REVIEW),
            )
            .where(Invoice.document_id.in_(ids))
            .group_by(Invoice.document_id)
        ):
            counts[doc_id] = (total, review)

    active, recent = [], []
    for doc in docs:
        event = events.get(doc.id)
        stage = _stage(doc, event)
        job = jobs.get(doc.id)
        unit = None
        if stage == "reading":
            unit = "pages"
        elif stage == "extracting" and event == "extract_windows":
            unit = "windows"
        total, review = counts.get(doc.id, (0, 0))
        item = ActivityItem(
            document_id=doc.id,
            filename=doc.filename,
            status=doc.status,
            stage=stage,
            stage_label=STAGE_LABELS[stage],
            progress_done=job.progress_done if job and unit else 0,
            progress_total=job.progress_total if job and unit else None,
            progress_unit=unit,
            attempts=job.attempts if job else 0,
            invoice_count=total,
            needs_review=review,
            error_code=doc.error_code,
            updated_at=doc.updated_at,
        )
        (active if stage not in ("done", "failed") else recent).append(item)

    review_count = (
        db.scalar(select(func.count()).where(Invoice.review_status == ReviewStatus.NEEDS_REVIEW))
        or 0
    )
    return ActivityResponse(active=active, recent=recent, review_count=review_count)
