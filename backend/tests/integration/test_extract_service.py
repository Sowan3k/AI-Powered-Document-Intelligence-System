"""Extraction end to end on Postgres: ingest, extract with the fake model, store."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import DocumentStatus, PageMethod, ReviewStatus
from app.db.models import Document, Invoice, LineItem, Page, ProcessingEvent, Sheet
from app.extract.llm import LlmError
from app.extract.service import EXTRACTION_FAILED, extract_document
from app.ingest.service import ingest_document, register_upload
from app.storage.local import LocalStorage
from tests.conftest import FakeCall, FakeLlmClient
from tests.unit.extract.helpers import fld, llm_invoice
from tests.unit.extract.test_extract_fixtures import perfect_reader


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "store")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gemini_model="text-model",
        gemini_vision_model="vision-model",
        segment_window_pages=3,
        segment_overlap_pages=1,
    )


def ingested(db: Session, storage: LocalStorage, path: Path, settings: Settings) -> Document:
    doc = register_upload(db, storage, path.name, path, settings)
    db.commit()
    assert ingest_document(db, storage, doc.id, settings)
    return doc


def invoices_of(db: Session, doc: Document) -> list[Invoice]:
    query = select(Invoice).where(Invoice.document_id == doc.id).order_by(Invoice.page_start)
    return list(db.scalars(query))


def events(db: Session, doc: Document, name: str) -> list[ProcessingEvent]:
    query = select(ProcessingEvent).where(
        ProcessingEvent.document_id == doc.id, ProcessingEvent.event == name
    )
    return list(db.scalars(query))


def reader_for(db: Session, doc: Document, synthetic_dir: Path, name: str) -> FakeLlmClient:
    truth = json.loads((synthetic_dir / f"{name}.json").read_text())
    pages = db.scalars(select(Page).where(Page.document_id == doc.id))
    return FakeLlmClient(perfect_reader(truth, {p.page_number: p.text for p in pages}))


def test_multi_invoice_pdf(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = ingested(db, storage, synthetic_dir / "multi_invoice.pdf", settings)
    fake = reader_for(db, doc, synthetic_dir, "multi_invoice.pdf")
    outcome = extract_document(db, storage, fake, doc.id, settings)
    assert outcome is not None and outcome.invoices == 4
    assert len(fake.calls) == 2  # pages 1-3 and 3-4
    assert all(c.model == "text-model" for c in fake.calls)

    truth = json.loads((synthetic_dir / "multi_invoice.pdf.json").read_text())["invoices"]
    stored = invoices_of(db, doc)
    assert [i.invoice_number for i in stored] == [t["invoice_number"] for t in truth]
    first = stored[0]
    assert first.total == Decimal(truth[0]["total"])
    assert first.review_status is ReviewStatus.PENDING
    assert first.invoice_number_norm == truth[0]["invoice_number"].replace("-", "")
    assert first.supplier_norm and first.supplier_norm == first.supplier_norm.lower()
    assert first.field_meta["total"]["confidence"] == 0.95
    assert first.field_meta["total"]["flags"] == []
    assert first.field_meta["total"]["evidence"]
    assert first.raw_extraction["invoice_number"]["value"] == truth[0]["invoice_number"]
    items = db.scalars(select(LineItem).where(LineItem.invoice_id == first.id))
    assert [li.amount for li in items] == [Decimal(li["amount"]) for li in truth[0]["line_items"]]

    calls = events(db, doc, "llm_call")
    assert len(calls) == 2 and calls[0].detail["prompt_tokens"] == 100
    [done] = events(db, doc, "extracted")
    assert done.detail["invoices"] == 4 and done.detail["prompt_tokens"] == 200
    assert doc.status is DocumentStatus.PROCESSING  # validation (Phase 3) comes next


def test_extract_again_replaces_invoices(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = ingested(db, storage, synthetic_dir / "digital_classic_0.pdf", settings)
    for _ in range(2):
        fake = reader_for(db, doc, synthetic_dir, "digital_classic_0.pdf")
        extract_document(db, storage, fake, doc.id, settings)
    assert len(invoices_of(db, doc)) == 1


@pytest.mark.tesseract
def test_low_confidence_scan_goes_to_vision(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = ingested(db, storage, synthetic_dir / "scan_heavy.jpg", settings)
    [page] = db.scalars(select(Page).where(Page.document_id == doc.id))
    assert page.method is PageMethod.OCR and page.ocr_confidence < 60

    def reply(call: FakeCall):  # type: ignore[no-untyped-def]
        if call.purpose == "vision_transcribe":
            assert call.model == "vision-model"
            assert call.turns[0].parts[0].data.startswith(b"\x89PNG")
            return "INVOICE\nInvoice No: INV-7\nTotal: $12.00"
        assert "INV-7" in call.turns[0].parts[0]  # extraction reads the transcription
        number = fld("INV-7", "Invoice No: INV-7")
        return {"invoices": [llm_invoice(1, invoice_number=number, total=fld("$12.00"))]}

    outcome = extract_document(db, storage, FakeLlmClient(reply), doc.id, settings)
    assert outcome is not None and outcome.vision_pages == 1
    db.refresh(page)
    assert page.method is PageMethod.VISION
    assert page.ocr_confidence < 60  # the Tesseract score is kept
    [inv] = invoices_of(db, doc)
    assert inv.total == Decimal("12.00") and inv.field_meta["total"]["flags"] == []
    assert len(events(db, doc, "vision_page")) == 1


def test_spreadsheet(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = ingested(db, storage, synthetic_dir / "register.xlsx", settings)
    outcome = extract_document(db, storage, FakeLlmClient([]), doc.id, settings)
    assert outcome is not None and outcome.invoices == 8 and outcome.usages == []
    stored = list(db.scalars(select(Invoice).where(Invoice.document_id == doc.id)))
    sheets = {s.id: s for s in db.scalars(select(Sheet).where(Sheet.document_id == doc.id))}
    assert {sheets[i.sheet_id].sheet_name for i in stored} == {"October", "November"}
    assert all(i.row_start and i.page_start is None for i in stored)
    october = next(s for s in sheets.values() if s.sheet_name == "October")
    assert october.column_mapping["fields"]["total"] == "Total"


def test_two_bad_replies_fail_the_document(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = ingested(db, storage, synthetic_dir / "digital_modern_0.pdf", settings)
    assert extract_document(db, storage, FakeLlmClient(["{", "{}"]), doc.id, settings) is None
    assert (doc.status, doc.error_code) == (DocumentStatus.FAILED, EXTRACTION_FAILED)
    assert invoices_of(db, doc) == []
    assert len(events(db, doc, "extract_failed")) == 1


def test_network_errors_propagate_for_the_job_queue(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = ingested(db, storage, synthetic_dir / "digital_modern_0.pdf", settings)

    def down(call: FakeCall) -> str:
        raise LlmError("Gemini call failed with HTTP 503")

    with pytest.raises(LlmError):
        extract_document(db, storage, FakeLlmClient(down), doc.id, settings)


def test_odd_amounts_are_flagged_when_stored(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = ingested(db, storage, synthetic_dir / "digital_modern_0.pdf", settings)
    reply = {"invoices": [llm_invoice(1, total=fld("12.345"), subtotal=fld("9999999999999.00"))]}
    extract_document(db, storage, FakeLlmClient([reply]), doc.id, settings)
    [inv] = invoices_of(db, doc)
    assert inv.total == Decimal("12.35") and "rounded" in inv.field_meta["total"]["flags"]
    assert inv.subtotal is None and "out_of_range" in inv.field_meta["subtotal"]["flags"]
