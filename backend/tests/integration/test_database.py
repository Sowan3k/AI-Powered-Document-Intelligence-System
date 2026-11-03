from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.enums import DocumentStatus, JobStatus, PageMethod, ReviewStatus, SourceKind
from app.db.models import EMBED_DIM, Document, Invoice, Job, LineItem, Page


def make_document(**overrides: object) -> Document:
    values: dict[str, object] = {
        "filename": "invoice.pdf",
        "mime_type": "application/pdf",
        "sha256": "a" * 64,
        "size_bytes": 1024,
        "source_kind": SourceKind.PDF,
    }
    values.update(overrides)
    return Document(**values)


def test_money_round_trips_as_exact_decimal(db: Session) -> None:
    document = make_document()
    invoice = Invoice(
        document=document,
        invoice_number="INV-001",
        invoice_date=date(2026, 10, 1),
        subtotal=Decimal("1000.10"),
        tax=Decimal("150.02"),
        total=Decimal("1150.12"),
        currency="BDT",
        field_meta={"total": {"confidence": 0.93, "evidence": "Total: 1,150.12"}},
    )
    invoice.line_items.append(
        LineItem(
            position=1,
            description="Widget",
            quantity=Decimal("3"),
            unit_price=Decimal("333.3667"),
            amount=Decimal("1000.10"),
        )
    )
    db.add(invoice)
    db.flush()
    db.expire_all()

    stored = db.get(Invoice, invoice.id)
    assert stored is not None
    assert stored.subtotal + stored.tax == stored.total == Decimal("1150.12")
    assert stored.line_items[0].unit_price == Decimal("333.3667")
    assert stored.review_status == ReviewStatus.PENDING
    assert stored.field_meta["total"]["evidence"] == "Total: 1,150.12"


def test_embedding_supports_cosine_distance(db: Session) -> None:
    document = make_document()
    near = [1.0] + [0.0] * (EMBED_DIM - 1)
    far = [0.0, 1.0] + [0.0] * (EMBED_DIM - 2)
    db.add_all(
        [
            Invoice(document=document, invoice_number="NEAR", embedding=near),
            Invoice(document=document, invoice_number="FAR", embedding=far),
        ]
    )
    db.flush()

    query = [0.9, 0.1] + [0.0] * (EMBED_DIM - 2)
    best = db.scalars(
        select(Invoice.invoice_number).order_by(Invoice.embedding.cosine_distance(query)).limit(1)
    ).one()
    assert best == "NEAR"


def test_search_vector_matches_keywords(db: Session) -> None:
    document = make_document()
    invoice = Invoice(document=document, invoice_number="INV-77", supplier_name="Acme Traders")
    db.add(invoice)
    db.flush()
    db.execute(
        text(
            "UPDATE invoices SET search_vector = to_tsvector('simple', supplier_name) "
            "WHERE id = :id"
        ),
        {"id": invoice.id},
    )
    hits = db.scalars(
        select(Invoice.invoice_number).where(
            Invoice.search_vector.op("@@")(func.plainto_tsquery("simple", "acme"))
        )
    ).all()
    assert hits == ["INV-77"]


def test_deleting_a_document_removes_its_children(db: Session) -> None:
    document = make_document()
    document.pages.append(Page(page_number=1, text="hello", method=PageMethod.DIGITAL))
    document.jobs.append(Job(job_type="process_document"))
    invoice = Invoice(document=document, invoice_number="X")
    invoice.line_items.append(LineItem(position=1, amount=Decimal("1.00")))
    db.add(invoice)
    db.flush()

    db.delete(document)
    db.flush()
    for table in ("pages", "jobs", "invoices", "line_items"):
        assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0  # noqa: S608


def test_defaults_are_set_by_the_database(db: Session) -> None:
    document = make_document()
    job = Job(document=document, job_type="process_document")
    db.add(job)
    db.flush()
    db.refresh(job)
    db.refresh(document)
    assert document.status == DocumentStatus.QUEUED
    assert job.status == JobStatus.QUEUED
    assert (job.attempts, job.max_attempts, job.progress_done) == (0, 3, 0)
    assert job.run_after is not None and document.created_at is not None


def test_database_rejects_an_unknown_status(db: Session) -> None:
    db.add(make_document())
    db.flush()
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE documents SET status = 'exploded'"))


def test_database_rejects_duplicate_page_numbers(db: Session) -> None:
    document = make_document()
    document.pages.append(Page(page_number=1, method=PageMethod.OCR))
    document.pages.append(Page(page_number=1, method=PageMethod.OCR))
    db.add(document)
    with pytest.raises(IntegrityError):
        db.flush()
