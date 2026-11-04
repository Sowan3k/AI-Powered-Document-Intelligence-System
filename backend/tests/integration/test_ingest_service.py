"""Uploads are stored under UUID keys, and ingestion writes pages and sheets."""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import DocumentStatus, JobStatus, PageMethod, SourceKind
from app.db.models import Document, Job, Page, ProcessingEvent, Sheet
from app.ingest.service import ingest_document, register_upload
from app.storage.local import LocalStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "store")


@pytest.fixture
def settings() -> Settings:
    return Settings(pdf_page_batch_size=2)


def events(db: Session, document: Document) -> list[str]:
    rows = db.scalars(
        select(ProcessingEvent.event)
        .where(ProcessingEvent.document_id == document.id)
        .order_by(ProcessingEvent.id)
    )
    return list(rows)


def upload(db: Session, storage: LocalStorage, path: Path, settings: Settings, name: str):
    document = register_upload(db, storage, name, path, settings)
    db.commit()
    return document


def test_pdf_upload_and_ingest(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = upload(db, storage, synthetic_dir / "multi_invoice.pdf", settings, "../../evil name.pdf")
    assert doc.status is DocumentStatus.QUEUED
    assert doc.filename == "evil name.pdf"  # display only
    assert doc.storage_path == f"{doc.id}/original.pdf"  # never the user's name
    assert (storage.root / doc.storage_path).is_file()
    assert len(doc.sha256) == 64

    job = Job(document_id=doc.id, job_type="ingest", status=JobStatus.RUNNING)
    db.add(job)
    db.commit()
    assert ingest_document(db, storage, doc.id, settings, job) is True

    pages = db.scalars(select(Page).where(Page.document_id == doc.id).order_by(Page.page_number))
    pages = list(pages)
    assert [p.page_number for p in pages] == [1, 2, 3, 4]
    assert all(p.method is PageMethod.DIGITAL for p in pages)
    assert doc.page_count == 4 and doc.source_kind is SourceKind.PDF
    assert doc.status is DocumentStatus.PROCESSING  # Phase 2 continues from here
    assert (job.progress_done, job.progress_total) == (4, 4)
    assert events(db, doc) == ["uploaded", "ingest_started", "ingested"]


def test_reingest_replaces_pages(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = upload(db, storage, synthetic_dir / "digital_classic_0.pdf", settings, "a.pdf")
    ingest_document(db, storage, doc.id, settings)
    ingest_document(db, storage, doc.id, settings)
    assert len(list(db.scalars(select(Page).where(Page.document_id == doc.id)))) == 1


def test_spreadsheet_ingest_saves_sheets(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = upload(db, storage, synthetic_dir / "register.xlsx", settings, "register.xlsx")
    assert ingest_document(db, storage, doc.id, settings)
    sheets = list(db.scalars(select(Sheet).where(Sheet.document_id == doc.id)))
    assert [(s.sheet_name, s.header_row, s.row_count) for s in sheets] == [
        ("October", 3, 5),
        ("November", 3, 3),
    ]
    assert sheets[0].column_mapping["headers"][0] == "Invoice No"
    assert doc.source_kind is SourceKind.SPREADSHEET and doc.page_count is None


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("empty.pdf", "EMPTY_FILE"),
        ("note_renamed.pdf", "UNSUPPORTED_TYPE"),
        ("letter.xlsx", "UNSUPPORTED_TYPE"),
    ],
)
def test_rejected_upload_is_recorded_not_stored(
    db: Session,
    storage: LocalStorage,
    settings: Settings,
    synthetic_dir: Path,
    name: str,
    code: str,
) -> None:
    doc = upload(db, storage, synthetic_dir / name, settings, name)
    assert doc.status is DocumentStatus.FAILED
    assert doc.error_code == code
    assert doc.storage_path is None
    assert not storage.root.exists() or not any(storage.root.rglob("*"))
    assert events(db, doc) == ["rejected"]


def test_too_large_upload(
    db: Session, storage: LocalStorage, synthetic_dir: Path, tmp_path: Path
) -> None:
    big = tmp_path / "big.pdf"
    shutil.copy(synthetic_dir / "scanned_light.pdf", big)  # about 1.3 MB
    doc = upload(db, storage, big, Settings(max_file_mb=1), "big.pdf")
    assert (doc.status, doc.error_code) == (DocumentStatus.FAILED, "TOO_LARGE")


@pytest.mark.parametrize(
    ("name", "code"),
    [("encrypted.pdf", "ENCRYPTED_PDF"), ("truncated.pdf", "CORRUPTED_FILE")],
)
def test_file_that_fails_in_the_worker(
    db: Session,
    storage: LocalStorage,
    settings: Settings,
    synthetic_dir: Path,
    name: str,
    code: str,
) -> None:
    # Both pass the upload check (they start with %PDF-) and fail when read.
    doc = upload(db, storage, synthetic_dir / name, settings, name)
    assert doc.status is DocumentStatus.QUEUED
    assert ingest_document(db, storage, doc.id, settings) is False
    assert (doc.status, doc.error_code) == (DocumentStatus.FAILED, code)
    assert events(db, doc) == ["uploaded", "ingest_started", "ingest_failed"]
    assert list(db.scalars(select(Page).where(Page.document_id == doc.id))) == []


def test_one_bad_file_does_not_stop_the_batch(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    names = ["digital_modern_0.pdf", "encrypted.pdf", "register.csv"]
    docs = [upload(db, storage, synthetic_dir / n, settings, n) for n in names]
    results = [ingest_document(db, storage, d.id, settings) for d in docs]
    assert results == [True, False, True]
    assert [d.status for d in docs] == [
        DocumentStatus.PROCESSING,
        DocumentStatus.FAILED,
        DocumentStatus.PROCESSING,
    ]
