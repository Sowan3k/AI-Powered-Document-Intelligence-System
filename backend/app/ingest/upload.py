"""Accept an uploaded file: hash it, check size and type, store it under a UUID key.

This runs in the API process, so it imports only detection and storage, never
the PDF or OCR libraries (they stay in the worker). A file that fails the
checks is still recorded, with status `failed` and its error code, so the
rest of the batch goes on (CLAUDE.md coding rule 3).
"""

import hashlib
import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import DocumentStatus
from app.db.models import Document, Job, ProcessingEvent
from app.ingest.detect import detect_kind
from app.ingest.errors import IngestError
from app.ingest.limits import check_file_size
from app.storage import FileStorage, StorageError, object_key

logger = logging.getLogger(__name__)

MAX_FILENAME = 255
STORAGE_ERROR = "STORAGE_ERROR"


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
    try:
        storage.upload(key, source, kind.mime_type)
    except StorageError as exc:
        # Storage is down: this file fails, the rest of the batch still gets a try.
        document.status = DocumentStatus.FAILED
        document.error_code = STORAGE_ERROR
        document.error_message = "the file could not be stored; upload it again later"
        session.add(document)
        _event(session, document, "rejected", None, error_code=STORAGE_ERROR, error=str(exc))
        logger.warning("upload %s not stored: %s", document.id, exc)
        return document
    document.storage_path = key
    document.mime_type = kind.mime_type
    document.source_kind = kind.source_kind
    session.add(document)
    _event(session, document, "uploaded", None, kind=kind.value, size_bytes=size)
    logger.info("upload %s stored as %s", document.id, kind.value)
    return document
