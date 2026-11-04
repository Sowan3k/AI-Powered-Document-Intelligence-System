"""Validation and reconciliation on Postgres, including pg_trgm duplicate search."""

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import ReviewStatus, Severity
from app.db.models import (
    Document,
    Invoice,
    LineItem,
    ProcessingEvent,
    Reconciliation,
    ValidationIssue,
)
from app.extract.normalise import norm_invoice_number, norm_supplier
from app.extract.service import extract_document
from app.ingest.service import ingest_document, register_upload
from app.storage.local import LocalStorage
from app.validate.reconcile import reconcile_documents
from app.validate.service import validate_document, validate_invoice
from tests.conftest import FakeLlmClient
from tests.unit.extract.test_extract_fixtures import perfect_reader

TODAY = date(2026, 11, 4)
FIELDS = ("invoice_number", "invoice_date", "supplier_name", "customer_name",
          "subtotal", "tax", "total", "currency")  # fmt: skip


def document(db: Session) -> Document:
    doc = Document(id=uuid.uuid4(), filename="x.pdf", sha256="0" * 64, size_bytes=1)
    db.add(doc)
    db.flush()
    return doc


def invoice(db: Session, doc: Document, number: str, supplier: str, total: str = "136.50",
            subtotal: str = "130.00", on: date = date(2026, 10, 1)) -> Invoice:  # fmt: skip
    inv = Invoice(
        id=uuid.uuid4(),
        document_id=doc.id,
        page_start=1,
        page_end=1,
        invoice_number=number,
        invoice_number_norm=norm_invoice_number(number),
        invoice_date=on,
        supplier_name=supplier,
        supplier_norm=norm_supplier(supplier),
        customer_name="Riverside Clinic",
        subtotal=Decimal(subtotal),
        tax=Decimal("6.50"),
        total=Decimal(total),
        currency="USD",
        field_meta={
            **{f: {"confidence": 0.95, "evidence": "x", "flags": []} for f in FIELDS},
            "currencies_seen": ["USD"],
        },
    )
    db.add(inv)
    db.flush()
    return inv


def rules(issues) -> set[tuple[str, Severity]]:  # type: ignore[no-untyped-def]
    return {(i.rule_code, i.severity) for i in issues}


def test_clean_invoice_is_ok(db: Session) -> None:
    inv = invoice(db, document(db), "INV-1", "Acme Traders Ltd")
    assert validate_invoice(db, inv, Settings(), TODAY) == []
    assert inv.review_status is ReviewStatus.OK


def test_r06_duplicate_with_a_differently_spelled_supplier(db: Session) -> None:
    first = invoice(db, document(db), "INV-2026-0042", "Acme Traders Ltd")
    second = invoice(db, document(db), "inv 2026 0042", "ACME TRADRES LIMITED")  # OCR slip
    issues = validate_invoice(db, second, Settings(), TODAY)
    assert rules(issues) == {("R06", Severity.ERROR)}
    assert issues[0].details["matches"][0]["invoice_id"] == str(first.id)
    assert second.review_status is ReviewStatus.NEEDS_REVIEW


def test_same_number_from_another_supplier_is_not_a_duplicate(db: Session) -> None:
    invoice(db, document(db), "INV-1", "Acme Traders Ltd")
    other = invoice(db, document(db), "INV-1", "Delta Hardware Co")
    assert validate_invoice(db, other, Settings(), TODAY) == []


def test_r07_possible_duplicate(db: Session) -> None:
    invoice(db, document(db), "INV-1", "Acme Traders Ltd")
    again = invoice(db, document(db), "INV-77", "Acme Traders Limited")
    assert rules(validate_invoice(db, again, Settings(), TODAY)) == {("R07", Severity.WARNING)}
    assert again.review_status is ReviewStatus.OK  # a warning alone does not block
    other_total = invoice(db, document(db), "INV-78", "Acme Traders Ltd", "99.00", "92.50")
    assert validate_invoice(db, other_total, Settings(), TODAY) == []


def test_validating_again_replaces_open_issues(db: Session) -> None:
    inv = invoice(db, document(db), "INV-1", "Acme Traders Ltd", total="999.00")
    validate_invoice(db, inv, Settings(), TODAY)
    validate_invoice(db, inv, Settings(), TODAY)
    db.flush()
    stored = db.scalars(select(ValidationIssue).where(ValidationIssue.invoice_id == inv.id)).all()
    assert [i.rule_code for i in stored] == ["R05"]
    inv.total = Decimal("136.50")  # a correction
    validate_invoice(db, inv, Settings(), TODAY)
    db.flush()
    assert (
        db.scalars(select(ValidationIssue).where(ValidationIssue.invoice_id == inv.id)).all() == []
    )
    assert inv.review_status is ReviewStatus.OK


def test_reviewed_status_is_kept(db: Session) -> None:
    inv = invoice(db, document(db), "INV-1", "Acme Traders Ltd", total="999.00")
    inv.review_status = ReviewStatus.REVIEWED
    assert validate_invoice(db, inv, Settings(), TODAY)
    assert inv.review_status is ReviewStatus.REVIEWED


def test_line_items_are_checked(db: Session) -> None:
    inv = invoice(db, document(db), "INV-1", "Acme Traders Ltd", "16.50", "10.00")
    db.add(LineItem(invoice_id=inv.id, position=1, quantity=Decimal("2"),
                    unit_price=Decimal("4.50"), amount=Decimal("10.00")))  # fmt: skip
    db.flush()
    db.refresh(inv)
    assert rules(validate_invoice(db, inv, Settings(), TODAY)) == {("R04", Severity.ERROR)}


def test_validate_document_records_an_event(db: Session) -> None:
    doc = document(db)
    invoice(db, doc, "INV-1", "Acme Traders Ltd")
    invoice(db, doc, "INV-2", "Acme Traders Ltd", total="999.00")
    counts = validate_document(db, doc.id, Settings(), today=TODAY)
    assert counts == {"R05": 1}
    [event] = db.scalars(
        select(ProcessingEvent).where(
            ProcessingEvent.document_id == doc.id, ProcessingEvent.event == "validated"
        )
    )
    assert event.detail == {"invoices": 2, "needs_review": 1, "issues": {"R05": 1}}


# Phase 3 exit test: every planted error is caught by the right rule.

EXPECTED = {
    "wrong_total": {("R05", Severity.ERROR)},
    "wrong_line_sum": {("R03", Severity.ERROR)},
    "wrong_line_amount": {("R04", Severity.ERROR)},
    "missing_tax": {("R01", Severity.WARNING)},
    "missing_customer": {("R01", Severity.WARNING)},
    "future_date": {("R08", Severity.ERROR)},
    "duplicate": {("R06", Severity.ERROR)},
    "near_duplicate": {("R07", Severity.WARNING)},
}


@pytest.fixture
def pipeline(db: Session, tmp_path: Path, synthetic_dir: Path):  # type: ignore[no-untyped-def]
    storage = LocalStorage(tmp_path / "store")
    settings = Settings(gemini_model="m", segment_window_pages=3, segment_overlap_pages=1)

    def run(name: str) -> Document:
        doc = register_upload(db, storage, name, synthetic_dir / name, settings)
        db.commit()
        assert ingest_document(db, storage, doc.id, settings)
        truth = json.loads((synthetic_dir / f"{name}.json").read_text())
        if name.endswith(".pdf"):
            from app.db.models import Page

            pages = db.scalars(select(Page).where(Page.document_id == doc.id))
            fake = FakeLlmClient(perfect_reader(truth, {p.page_number: p.text for p in pages}))
        else:
            fake = FakeLlmClient([])
        assert extract_document(db, storage, fake, doc.id, settings) is not None
        validate_document(db, doc.id, settings, today=TODAY)
        return doc

    return run, settings


def test_every_planted_error_is_caught_by_the_right_rule(
    db: Session,
    pipeline,
    synthetic_dir: Path,
    manifest: list[dict],  # type: ignore[no-untyped-def]
) -> None:
    run, _ = pipeline
    digital = [
        e["file"]
        for e in manifest
        if e["file"].endswith(".pdf") and e["expect"].get("methods") == ["digital"]
    ]
    assert len(digital) >= 13
    for name in digital:
        doc = run(name)
        truth = json.loads((synthetic_dir / f"{name}.json").read_text())
        stored = db.scalars(
            select(Invoice).where(Invoice.document_id == doc.id).order_by(Invoice.page_start)
        ).all()
        assert len(stored) == len(truth["invoices"]), name
        for inv, want in zip(stored, truth["invoices"], strict=True):
            issues = db.scalars(select(ValidationIssue).where(ValidationIssue.invoice_id == inv.id))
            found = rules(issues)
            expected = (
                set().union(*(EXPECTED[p] for p in want["planted"])) if want["planted"] else set()
            )
            assert found == expected, (name, want["invoice_number"], found)
            has_error = any(sev is Severity.ERROR for _, sev in expected)
            assert inv.review_status is (
                ReviewStatus.NEEDS_REVIEW if has_error else ReviewStatus.OK
            )


def test_reconcile_pdf_against_workbook(db: Session, pipeline, synthetic_dir: Path) -> None:  # type: ignore[no-untyped-def]
    run, settings = pipeline
    pdf, sheet = run("recon_statement.pdf"), run("recon_register.xlsx")
    row = reconcile_documents(db, pdf.id, sheet.id, settings)
    want = json.loads((synthetic_dir / "recon_register.xlsx.json").read_text())["expected"]
    got = row.result
    assert [[m["a"]["invoice_number"], m["matched_on"]] for m in got["matched"]] == want["matched"]
    assert [
        [m["a"]["invoice_number"], [d["field"] for d in m["differences"]]]
        for m in got["mismatched"]
    ] == want["mismatched"]
    assert [r["invoice_number"] for r in got["only_in_a"]] == want["only_in_a"]
    assert [r["invoice_number"] for r in got["only_in_b"]] == want["only_in_b"]
    assert db.get(Reconciliation, row.id) is not None


def test_reconcile_refuses_bad_input(db: Session) -> None:
    doc = document(db)
    with pytest.raises(ValueError, match="two different"):
        reconcile_documents(db, doc.id, doc.id, Settings())
    with pytest.raises(ValueError, match="not found"):
        reconcile_documents(db, doc.id, uuid.uuid4(), Settings())
