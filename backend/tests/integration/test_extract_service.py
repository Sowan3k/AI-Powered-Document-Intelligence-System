"""Extraction end to end on Postgres: ingest, extract with the fake model, store."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import InvoiceOut
from app.core.config import Settings
from app.db.enums import DocumentStatus, PageMethod, ReviewStatus
from app.db.models import Document, Invoice, LineItem, Page, ProcessingEvent, Sheet
from app.extract.columns import ALL_FIELDS
from app.extract.llm import LlmError
from app.extract.service import EXTRACTION_FAILED, extract_document
from app.ingest.service import ingest_document
from app.ingest.upload import register_upload
from app.storage.local import LocalStorage
from app.validate.service import validate_invoice
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
            assert call.turns[0].parts[0].data.startswith(b"\xff\xd8\xff")  # JPEG (D86)
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


@pytest.mark.tesseract
def test_a_confident_photo_still_goes_to_vision(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    """On photos Tesseract's page score hides single wrong letters (run 7, D82)."""
    doc = ingested(db, storage, synthetic_dir / "scan_clean.png", settings)
    [page] = db.scalars(select(Page).where(Page.document_id == doc.id))
    assert page.method is PageMethod.OCR and page.ocr_confidence >= 60

    def reply(call: FakeCall):  # type: ignore[no-untyped-def]
        if call.purpose == "vision_transcribe":
            return "INVOICE\nInvoice No: INV-8\nTotal: $9.00"
        return {"invoices": []}

    outcome = extract_document(db, storage, FakeLlmClient(reply), doc.id, settings)
    assert outcome is not None and outcome.vision_pages == 1
    db.refresh(page)
    assert page.method is PageMethod.VISION
    [seen] = events(db, doc, "vision_page")
    assert seen.detail["reason"] == "photo"


@pytest.mark.tesseract
def test_photos_can_keep_the_ocr_text(
    db: Session, storage: LocalStorage, synthetic_dir: Path
) -> None:
    settings = Settings(
        gemini_model="text-model", gemini_vision_model="vision-model", vision_for_photos=False
    )
    doc = ingested(db, storage, synthetic_dir / "scan_clean.png", settings)
    fake = FakeLlmClient(lambda call: {"invoices": []})
    outcome = extract_document(db, storage, fake, doc.id, settings)
    assert outcome is not None and outcome.vision_pages == 0
    assert all(c.purpose != "vision_transcribe" for c in fake.calls)


@pytest.mark.tesseract
def test_a_confident_tiff_scan_keeps_the_threshold(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    """Scanner output is not a phone photo: only weak pages go to vision."""
    doc = ingested(db, storage, synthetic_dir / "scan_two_pages.tiff", settings)
    pages = list(db.scalars(select(Page).where(Page.document_id == doc.id)))
    weak = [p for p in pages if p.ocr_confidence is not None and p.ocr_confidence < 60]

    def reply(call: FakeCall):  # type: ignore[no-untyped-def]
        if call.purpose == "vision_transcribe":
            return "INVOICE"
        return {"invoices": []}

    outcome = extract_document(db, storage, FakeLlmClient(reply), doc.id, settings)
    assert outcome is not None and outcome.vision_pages == len(weak)


@pytest.mark.tesseract
def test_an_upside_down_photo_is_noted_at_ingest(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = ingested(db, storage, synthetic_dir / "photo_upside_down.jpg", settings)
    [turned] = events(db, doc, "page_turned")
    assert turned.detail["page"] == 1


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


def test_a_sheet_that_is_not_invoices_gives_none(
    db: Session, storage: LocalStorage, settings: Settings, tmp_path: Path
) -> None:
    staff = tmp_path / "staff.csv"
    staff.write_text("Name,Department,Joined,Salary\nRahim,Sales,2026-01-02,45000\n")
    doc = ingested(db, storage, staff, settings)
    reply = {"lists_invoices": False} | dict.fromkeys(ALL_FIELDS)
    outcome = extract_document(db, storage, FakeLlmClient([reply]), doc.id, settings)
    assert outcome is not None and outcome.invoices == 0
    assert invoices_of(db, doc) == []
    [sheet] = db.scalars(select(Sheet).where(Sheet.document_id == doc.id))
    assert sheet.column_mapping["lists_invoices"] is False
    assert len(events(db, doc, "sheet_skipped")) == 1
    assert len(events(db, doc, "no_invoice_found")) == 1


def test_a_pdf_with_no_invoice_says_so(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = ingested(db, storage, synthetic_dir / "digital_modern_0.pdf", settings)
    outcome = extract_document(db, storage, FakeLlmClient([{"invoices": []}]), doc.id, settings)
    assert outcome is not None and outcome.invoices == 0
    assert len(events(db, doc, "no_invoice_found")) == 1


def test_discounts_and_charges_are_stored_and_counted(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = ingested(db, storage, synthetic_dir / "digital_modern_0.pdf", settings)
    adjustments = [
        {"label": "Discount", "amount": "10.00", "evidence": None},
        {"label": "Delivery charge", "amount": "60.00", "evidence": None},
    ]
    reply = {
        "invoices": [
            llm_invoice(
                1,
                subtotal=fld("100.00"),
                tax=fld("15.00"),
                total=fld("165.00"),
                adjustments=adjustments,
            )  # fmt: skip
        ]
    }
    extract_document(db, storage, FakeLlmClient([reply]), doc.id, settings)
    [inv] = invoices_of(db, doc)
    assert [a["amount"] for a in inv.field_meta["adjustments"]] == ["-10.00", "60.00"]
    issues = validate_invoice(db, inv, settings)
    assert "R05" not in {i.rule_code for i in issues}  # 100 + 15 - 10 + 60 = 165
    out = InvoiceOut.model_validate(inv).model_dump(mode="json")
    assert out["adjustments"][0] == {
        "label": "Discount", "amount": "-10.00", "flags": ["evidence_not_found"]
    }  # fmt: skip


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


@pytest.mark.tesseract
def test_vision_outage_keeps_the_ocr_text(
    db: Session, storage: LocalStorage, settings: Settings, synthetic_dir: Path
) -> None:
    doc = ingested(db, storage, synthetic_dir / "scan_heavy.jpg", settings)
    [page] = db.scalars(select(Page).where(Page.document_id == doc.id))
    ocr_text = page.text

    def reply(call: FakeCall):  # type: ignore[no-untyped-def]
        if call.purpose == "vision_transcribe":
            raise LlmError("Gemini call failed with HTTP 503")
        return {"invoices": []}

    outcome = extract_document(db, storage, FakeLlmClient(reply), doc.id, settings)
    assert outcome is not None and outcome.vision_pages == 0
    db.refresh(page)
    assert page.method is PageMethod.OCR and page.text == ocr_text
    [failed] = events(db, doc, "vision_failed")
    assert len(failed.detail["errors"]) == 2  # vision model, then the text model


def test_blank_scanned_page_never_goes_to_vision(
    db: Session, storage: LocalStorage, settings: Settings, tmp_path: Path
) -> None:
    import pymupdf

    blank = pymupdf.open()
    blank.new_page()
    blank.save(tmp_path / "blank.pdf")
    doc = ingested(db, storage, tmp_path / "blank.pdf", settings)
    [page] = db.scalars(select(Page).where(Page.document_id == doc.id))
    assert page.method is PageMethod.OCR and page.ocr_confidence is None
    fake = FakeLlmClient([])
    outcome = extract_document(db, storage, fake, doc.id, settings)
    assert outcome is not None and outcome.vision_pages == 0
    assert fake.calls == []  # a blank window makes no call at all
