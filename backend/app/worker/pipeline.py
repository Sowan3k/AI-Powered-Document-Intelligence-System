"""What a job does. `process` runs every stage; `index` only refreshes search.

Stages: ingest (Phase 1), extract (Phase 2), validate (Phase 3), index.
A file that cannot be read, or a model reply that broke the schema twice,
is a final failure with its code: retrying would fail the same way. Network,
storage and quota errors propagate, and the queue retries the job.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import DocumentStatus
from app.db.models import Document, Job, ProcessingEvent
from app.extract.llm import LlmClient
from app.extract.service import extract_document
from app.ingest.service import ingest_document
from app.search.index import index_document
from app.storage import FileStorage
from app.validate.service import validate_document
from app.worker.queue import JobCancelledError, is_cancelled

logger = logging.getLogger(__name__)


@dataclass
class Outcome:
    ok: bool
    error_code: str | None = None


def process_document(
    session: Session,
    storage: FileStorage,
    llm: LlmClient | None,
    document_id: uuid.UUID,
    settings: Settings,
    job: Job | None = None,
) -> Outcome:
    if not ingest_document(session, storage, document_id, settings, job):
        return Outcome(False, _code(session, document_id))
    _stop_if_cancelled(session, job)
    if extract_document(session, storage, llm, document_id, settings, job) is None:
        return Outcome(False, _code(session, document_id))
    _stop_if_cancelled(session, job)
    validate_document(session, document_id, settings, job)
    _record(session, document_id, job, index_document(session, llm, document_id, settings))
    _stop_if_cancelled(session, job)
    document = session.get(Document, document_id)
    assert document is not None  # noqa: S101 (ingest found it)
    document.status = DocumentStatus.COMPLETED
    session.add(
        ProcessingEvent(document_id=document_id, job_id=job.id if job else None, event="completed")
    )
    session.commit()
    return Outcome(True)


def reindex(
    session: Session,
    llm: LlmClient | None,
    document_id: uuid.UUID,
    settings: Settings,
    job: Job | None = None,
) -> Outcome:
    _record(session, document_id, job, index_document(session, llm, document_id, settings))
    return Outcome(True)


def _record(session: Session, document_id: uuid.UUID, job: Job | None, usages) -> None:  # type: ignore[no-untyped-def]
    """Embedding calls count like every other model call (tokens per document)."""
    for usage in usages:
        session.add(
            ProcessingEvent(
                document_id=document_id,
                job_id=job.id if job else None,
                event="llm_call",
                detail=usage.as_detail(),
            )
        )
    if usages:
        session.commit()


def _stop_if_cancelled(session: Session, job: Job | None) -> None:
    """Between steps: a person may have cancelled the job from the web app (D86)."""
    if job is not None and is_cancelled(session, job.id):
        raise JobCancelledError


def _code(session: Session, document_id: uuid.UUID) -> str | None:
    document = session.get(Document, document_id)
    return document.error_code if document else None
