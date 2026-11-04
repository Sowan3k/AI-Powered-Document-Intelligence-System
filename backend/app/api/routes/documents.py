"""Documents: upload a batch, list, details with history, results, reprocess, the
original file, delete."""

import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from starlette.background import BackgroundTask

from app.api.deps import current_user, get_storage, limit_upload
from app.api.schemas import (
    DocumentDetail,
    DocumentOut,
    DocumentPage,
    EventOut,
    InvoiceDetail,
    IssueOut,
    JobOut,
    PageOut,
    ResultsResponse,
    UploadResponse,
    UploadResult,
)
from app.core.config import Settings, get_settings
from app.db.enums import DocumentStatus
from app.db.models import Document, Invoice, Job, Page, ProcessingEvent
from app.db.session import get_db
from app.ingest.errors import IngestError
from app.ingest.limits import check_batch
from app.ingest.upload import register_upload
from app.storage import FileStorage
from app.storage.base import StorageError
from app.worker import queue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(current_user)])

COPY_CHUNK = 1024 * 1024


def _get(db: Session, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    return document


def _latest_jobs(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, Job]:
    latest: dict[uuid.UUID, Job] = {}
    if ids:
        for job in db.scalars(select(Job).where(Job.document_id.in_(ids)).order_by(Job.created_at)):
            latest[job.document_id] = job
    return latest


def invoice_detail(inv: Invoice) -> InvoiceDetail:
    """An invoice with its lines, open issues and corrections."""
    detail = InvoiceDetail.model_validate(inv)
    detail.issues = [IssueOut.model_validate(i) for i in inv.issues if not i.resolved]
    return detail


def _out(doc: Document, job: Job | None, invoices: int | None) -> DocumentOut:
    out = DocumentOut.model_validate(doc)
    out.latest_job = JobOut.model_validate(job) if job else None
    out.invoice_count = invoices
    return out


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadResponse,
    dependencies=[Depends(limit_upload)],
    responses={400: {"description": "Too many files"}, 429: {}},
)
def upload(
    files: list[UploadFile] = File(..., description="One or more files"),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> UploadResponse:
    """Store every file and queue it. A bad file fails alone; the others go on."""
    try:
        check_batch(len(files), settings)
    except IngestError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from None
    results: list[UploadResult] = []
    with tempfile.TemporaryDirectory(prefix="docintel-upload-") as tmp:
        for n, upload_file in enumerate(files):
            path = Path(tmp) / f"file-{n}"
            with path.open("wb") as out:
                shutil.copyfileobj(upload_file.file, out, COPY_CHUNK)
            doc = register_upload(db, storage, upload_file.filename or "unnamed", path, settings)
            job = None
            if doc.status is DocumentStatus.QUEUED:
                db.flush()
                job = queue.enqueue(db, doc.id, queue.JOB_PROCESS, settings)
            results.append(
                UploadResult(
                    document_id=doc.id,
                    filename=doc.filename,
                    status=doc.status,
                    error_code=doc.error_code,
                    error_message=doc.error_message,
                    job_id=job.id if job else None,
                )
            )
    db.commit()
    accepted = sum(r.job_id is not None for r in results)
    logger.info("upload batch: %d accepted, %d rejected", accepted, len(results) - accepted)
    return UploadResponse(documents=results, accepted=accepted, rejected=len(results) - accepted)


@router.get("", response_model=DocumentPage)
def list_documents(
    status_filter: DocumentStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> DocumentPage:
    query = select(Document)
    if status_filter:
        query = query.where(Document.status == status_filter)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    docs = list(db.scalars(query.order_by(Document.created_at.desc()).limit(limit).offset(offset)))
    ids = [d.id for d in docs]
    jobs = _latest_jobs(db, ids)
    counts = dict(
        db.execute(
            select(Invoice.document_id, func.count())
            .where(Invoice.document_id.in_(ids))
            .group_by(Invoice.document_id)
        ).all()
    ) if ids else {}  # fmt: skip
    items = [_out(d, jobs.get(d.id), counts.get(d.id, 0)) for d in docs]
    return DocumentPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> DocumentDetail:
    doc = _get(db, document_id)
    jobs = list(db.scalars(select(Job).where(Job.document_id == doc.id).order_by(Job.created_at)))
    events = db.scalars(
        select(ProcessingEvent)
        .where(ProcessingEvent.document_id == doc.id)
        .order_by(ProcessingEvent.created_at, ProcessingEvent.id)
    )
    invoices = db.scalar(select(func.count()).where(Invoice.document_id == doc.id)) or 0
    base = _out(doc, jobs[-1] if jobs else None, invoices)
    return DocumentDetail(
        **base.model_dump(),
        jobs=[JobOut.model_validate(j) for j in jobs],
        history=[EventOut.model_validate(e) for e in events],
    )


@router.get("/{document_id}/results", response_model=ResultsResponse)
def get_results(
    document_id: uuid.UUID,
    include_pages: bool = Query(False, description="Also return the text of every page"),
    db: Session = Depends(get_db),
) -> ResultsResponse:
    doc = _get(db, document_id)
    invoices = db.scalars(
        select(Invoice)
        .where(Invoice.document_id == doc.id)
        .options(
            selectinload(Invoice.line_items),
            selectinload(Invoice.issues),
            selectinload(Invoice.corrections),
        )
        .order_by(Invoice.page_start, Invoice.row_start, Invoice.created_at)
    ).all()
    out = [invoice_detail(inv) for inv in invoices]
    pages = []
    if include_pages:
        pages = [
            PageOut.model_validate(p)
            for p in db.scalars(
                select(Page).where(Page.document_id == doc.id).order_by(Page.page_number)
            )
        ]
    jobs = _latest_jobs(db, [doc.id])
    return ResultsResponse(
        document=_out(doc, jobs.get(doc.id), len(out)), invoices=out, pages=pages
    )


@router.post(
    "/{document_id}/reprocess",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobOut,
    responses={404: {}, 409: {"description": "Already queued, or nothing stored to process"}},
)
def reprocess(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JobOut:
    doc = _get(db, document_id)
    if doc.storage_path is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this file was rejected at upload; upload it again"
        )
    if queue.active_job(db, doc.id, queue.JOB_PROCESS):
        raise HTTPException(status.HTTP_409_CONFLICT, "this document is already queued or running")
    doc.status = DocumentStatus.QUEUED
    doc.error_code = doc.error_message = None
    job = queue.enqueue(db, doc.id, queue.JOB_PROCESS, settings)
    db.commit()
    return JobOut.model_validate(job)


# Types a browser can show safely inside the page; anything else downloads (D65).
INLINE_TYPES = {"application/pdf", "image/png", "image/jpeg"}


@router.get(
    "/{document_id}/file",
    response_class=FileResponse,
    responses={200: {"description": "The original file"}, 404: {}, 502: {}},
)
def original_file(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
) -> FileResponse:
    """The uploaded file itself, so a reviewer can compare it with the extracted values."""
    doc = _get(db, document_id)
    if doc.storage_path is None or doc.mime_type is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "this file was rejected at upload")
    tmp = tempfile.mkdtemp(prefix="docintel-file-")
    local = Path(tmp) / "original"
    try:
        storage.download(doc.storage_path, local)
    except StorageError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "the file store did not answer") from None
    inline = doc.mime_type in INLINE_TYPES
    # The stored name is user input: keep plain characters only in the header.
    safe_name = "".join(c for c in doc.filename if c.isascii() and (c.isalnum() or c in "._- "))
    return FileResponse(
        local,
        media_type=doc.mime_type,
        filename=safe_name.strip() or f"{doc.id}",
        content_disposition_type="inline" if inline else "attachment",
        background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True),
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {}, 409: {"description": "Still being processed"}, 502: {}},
)
def delete_document(
    document_id: uuid.UUID,
    user: str = Depends(current_user),
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
) -> Response:
    """Remove a document everywhere: the stored file, its pages, invoices, issues,
    corrections, jobs and history (the database cascades from the document row)."""
    doc = _get(db, document_id)
    if any(queue.active_job(db, doc.id, t) for t in (queue.JOB_PROCESS, queue.JOB_INDEX)):
        raise HTTPException(status.HTTP_409_CONFLICT, "wait until processing finishes")
    if doc.storage_path is not None:
        try:
            storage.delete(doc.storage_path)
        except StorageError:
            # Keep the row, so the delete can be tried again; nothing is half removed.
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "the file store did not answer"
            ) from None
    db.execute(sql_delete(Document).where(Document.id == doc.id))
    db.commit()
    logger.info("document %s deleted by %s", doc.id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
