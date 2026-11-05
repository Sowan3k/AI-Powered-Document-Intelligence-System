"""Save what the readers find into the database.

`ingest_document` runs in the worker: it downloads the file, reads it, and
writes `pages` or `sheets` rows. Pages are committed batch by batch, and the
job's progress counts pages done out of the total.
"""

import logging
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import DocumentStatus
from app.db.models import Document, Job, Page, Sheet
from app.ingest import reader
from app.ingest.errors import IngestError
from app.ingest.schemas import FileKind
from app.ingest.upload import _event
from app.storage import FileStorage

logger = logging.getLogger(__name__)


def _fail(session: Session, document: Document, job: Job | None, exc: IngestError) -> None:
    document.status = DocumentStatus.FAILED
    document.error_code = exc.code.value
    document.error_message = exc.message
    _event(session, document, "ingest_failed", job, error_code=exc.code.value)
    session.commit()
    logger.info("ingest %s failed: %s", document.id, exc.code.value)


def ingest_document(
    session: Session,
    storage: FileStorage,
    document_id: uuid.UUID,
    settings: Settings,
    job: Job | None = None,
) -> bool:
    """Read a stored document into pages or sheets. Returns False if the file failed.

    Safe to run again: old pages and sheets of the document are replaced.
    Storage and database errors propagate, so the job queue can retry them.
    """
    document = session.get(Document, document_id)
    if document is None or document.storage_path is None:
        raise ValueError(f"document {document_id} has no stored file")

    document.status = DocumentStatus.PROCESSING
    document.error_code = document.error_message = None
    session.execute(delete(Page).where(Page.document_id == document.id))
    session.execute(delete(Sheet).where(Sheet.document_id == document.id))
    _event(session, document, "ingest_started", job)
    session.commit()

    with tempfile.TemporaryDirectory(prefix="docintel-") as tmp:
        local = Path(tmp) / "original"
        storage.download(document.storage_path, local)
        try:
            found = reader.probe(local, settings)
            document.source_kind = found.kind.source_kind
            document.mime_type = found.kind.mime_type
            document.page_count = found.page_count
            if job is not None:
                job.progress_done = 0
                job.progress_total = found.page_count
            session.commit()
            if found.kind.is_paged:
                _save_pages(session, document, job, local, found.kind, settings)
            else:
                _save_sheets(session, document, local, found.kind)
        except IngestError as exc:
            session.rollback()
            _fail(session, document, job, exc)
            return False

    _event(session, document, "ingested", job, kind=found.kind.value, pages=found.page_count)
    session.commit()
    logger.info("ingest %s done: %s", document.id, found.kind.value)
    return True


def _save_pages(
    session: Session,
    document: Document,
    job: Job | None,
    path: Path,
    kind: FileKind,
    settings: Settings,
) -> None:
    pending = 0
    for page in reader.iter_pages(path, kind, settings):
        session.add(
            Page(
                document_id=document.id,
                page_number=page.page_number,
                text=page.text,
                method=page.method,
                ocr_confidence=page.ocr_confidence,
            )
        )
        if page.skew_degrees is not None and abs(page.skew_degrees) >= 90:
            # Tesseract read it upside down (D64); the vision step turns it the same way (D82).
            _event(session, document, "page_turned", job, page=page.page_number)
        pending += 1
        if job is not None:
            job.progress_done = page.page_number
        if pending >= settings.pdf_page_batch_size:
            session.commit()
            pending = 0
    session.commit()


def _save_sheets(session: Session, document: Document, path: Path, kind: FileKind) -> None:
    # Rows are not stored here: Phase 2 maps columns and turns rows into invoices.
    for sheet in reader.read_sheets(path, kind):
        session.add(
            Sheet(
                document_id=document.id,
                sheet_index=sheet.sheet_index,
                sheet_name=sheet.sheet_name,
                header_row=sheet.header_row,
                column_mapping={"headers": sheet.headers},
                row_count=sheet.row_count,
            )
        )
    session.commit()
