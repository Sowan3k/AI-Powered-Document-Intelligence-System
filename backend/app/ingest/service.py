"""Store uploads and save what the readers find into the database.

`register_upload` runs in the API when a file arrives: it hashes the file,
checks size and type by magic bytes, and stores it under a UUID key. A file
that fails these checks is still recorded, with status `failed` and its error
code, so the rest of the batch goes on (CLAUDE.md coding rule 3).

`ingest_document` runs in the worker: it downloads the file, reads it, and
writes `pages` or `sheets` rows. Pages are committed batch by batch, and the
job's progress counts pages done out of the total.
"""

import hashlib
import logging
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import DocumentStatus
from app.db.models import Document, Job, Page, ProcessingEvent, Sheet
from app.ingest import reader
from app.ingest.detect import detect_kind
from app.ingest.errors import IngestError
from app.ingest.limits import check_file_size
from app.ingest.schemas import FileKind
from app.storage import FileStorage, object_key

logger = logging.getLogger(__name__)

MAX_FILENAME = 255


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _display_name(filename: str) -> str:
    """Keep only the last path part, for display. It never becomes a storage path."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return "".join(ch for ch in name if ch.isprintable())[:MAX_FILENAME] or "unnamed"


def _event(
    session: Session, document: Document, event: str, job: Job | None, **detail: object
) -> None:
    session.add(
        ProcessingEvent(
            document_id=document.id,
            job_id=job.id if job else None,
            event=event,
            detail=detail or None,
        )
    )


def register_upload(
    session: Session, storage: FileStorage, filename: str, source: Path, settings: Settings
) -> Document:
    """Create the document row and store the file. Does not commit."""
    size = source.stat().st_size
    document = Document(
        id=uuid.uuid4(),
        filename=_display_name(filename),
        sha256=sha256_of(source),
        size_bytes=size,
        status=DocumentStatus.QUEUED,
    )
    try:
        check_file_size(size, settings)
        kind = detect_kind(source, settings)
    except IngestError as exc:
        document.status = DocumentStatus.FAILED
        document.error_code = exc.code.value
        document.error_message = exc.message
        session.add(document)
        _event(session, document, "rejected", None, error_code=exc.code.value)
        logger.info("upload %s rejected: %s", document.id, exc.code.value)
        return document

    key = object_key(document.id, kind.extension)
    storage.upload(key, source, kind.mime_type)
    document.storage_path = key
    document.mime_type = kind.mime_type
    document.source_kind = kind.source_kind
    session.add(document)
    _event(session, document, "uploaded", None, kind=kind.value, size_bytes=size)
    logger.info("upload %s stored as %s", document.id, kind.value)
    return document


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
