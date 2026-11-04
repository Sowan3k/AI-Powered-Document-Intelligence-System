"""Search: full-text behaviour, filters, and semantic order."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import ReviewStatus
from app.db.models import Document, Invoice, LineItem
from app.extract.normalise import norm_invoice_number, norm_supplier
from app.search.index import embedding_text, index_document
from app.search.service import Filters, search
from tests.conftest import FakeLlmClient

SETTINGS = Settings(gemini_embed_model="embed-model")


@pytest.fixture
def corpus(db: Session) -> Document:
    doc = Document(id=uuid.uuid4(), filename="c.pdf", sha256="0" * 64, size_bytes=1)
    db.add(doc)
    rows = [
        ("INV-2026-0007", "Acme Traders Ltd", "120.00", "USD", date(2026, 3, 1), "Toner cartridge"),
        (
            "INV-2026-0008",
            "Delta Hardware Co",
            "45.50",
            "EUR",
            date(2026, 6, 1),
            "Steel bolts, box",
        ),
        ("B-77", "Padma Printing House", "980.00", "BDT", date(2026, 9, 1), "Printing, per page"),
    ]
    for number, supplier, total, cur, on, item in rows:
        inv = Invoice(
            id=uuid.uuid4(), document_id=doc.id, invoice_number=number,
            invoice_number_norm=norm_invoice_number(number), supplier_name=supplier,
            supplier_norm=norm_supplier(supplier), total=Decimal(total), currency=cur,
            invoice_date=on, review_status=ReviewStatus.OK,
        )  # fmt: skip
        inv.line_items.append(LineItem(position=1, description=item, amount=Decimal(total)))
        db.add(inv)
    db.flush()
    index_document(db, FakeLlmClient(), doc.id, SETTINGS)
    return doc


def numbers(db: Session, **kw) -> list[str]:  # type: ignore[no-untyped-def]
    filters = kw.pop("filters", Filters())
    hits, _ = search(db, filters=filters, settings=SETTINGS, **kw)
    return [h.invoice.invoice_number for h in hits]


def test_keyword_matches_numbers_whole_and_stems_words(db: Session, corpus: Document) -> None:
    assert numbers(db, mode="keyword", q="INV-2026-0007") == ["INV-2026-0007"]
    assert numbers(db, mode="keyword", q="cartridges") == ["INV-2026-0007"]  # stemmed
    assert set(numbers(db, mode="keyword", q="bolts OR printing")) == {"INV-2026-0008", "B-77"}
    assert numbers(db, mode="keyword", q="toner -acme") == []


def test_filters(db: Session, corpus: Document) -> None:
    def only(**f) -> list[str]:  # type: ignore[no-untyped-def]
        return numbers(db, mode="keyword", q=None, filters=Filters(document_id=corpus.id, **f))

    assert only(currency="eur") == ["INV-2026-0008"]
    assert only(amount_min=Decimal("100"), amount_max=Decimal("500")) == ["INV-2026-0007"]
    assert only(date_from=date(2026, 5, 1), date_to=date(2026, 7, 1)) == ["INV-2026-0008"]
    assert only(supplier="ACME TRADRES") == ["INV-2026-0007"]  # fuzzy, typo included
    assert only(supplier="100%_") == []  # wildcards are escaped
    assert only(status=ReviewStatus.NEEDS_REVIEW) == []


def test_semantic_orders_by_meaning(db: Session, corpus: Document) -> None:
    fake = FakeLlmClient()
    found = numbers(db, mode="semantic", q="steel bolts", llm=fake,
                    filters=Filters(document_id=corpus.id))  # fmt: skip
    assert found[0] == "INV-2026-0008"
    assert fake.embedded == ["task: search result | query: steel bolts"]


def test_semantic_needs_a_query_and_a_model(db: Session, corpus: Document) -> None:
    with pytest.raises(ValueError):
        search(
            db, mode="semantic", q=None, filters=Filters(), settings=SETTINGS, llm=FakeLlmClient()
        )
    with pytest.raises(RuntimeError):
        search(db, mode="semantic", q="x", filters=Filters(), settings=SETTINGS, llm=None)


def test_embedding_text_uses_the_d31_document_format(db: Session, corpus: Document) -> None:
    inv = next(i for i in corpus.invoices if i.invoice_number == "INV-2026-0007")
    text = embedding_text(inv)
    assert text.startswith(f"title: Invoice {inv.invoice_number} from {inv.supplier_name} | text: ")
    assert "Items: Toner cartridge" in text
