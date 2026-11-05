"""Search: full-text behaviour, filters, and semantic order."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
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


def test_hybrid_finds_exact_codes_and_loose_words(db: Session, corpus: Document) -> None:
    mine = Filters(document_id=corpus.id)
    # An exact number: keyword ranks it first, semantic agrees or not; fusion keeps it first.
    assert numbers(db, mode="hybrid", q="INV-2026-0008", llm=FakeLlmClient(), filters=mine)[0] == (
        "INV-2026-0008"
    )
    # Loose words that full text cannot match: the semantic list carries the answer.
    assert numbers(db, mode="keyword", q="steel bolts rivets", filters=mine) == []
    loose = numbers(db, mode="hybrid", q="steel bolts rivets", llm=FakeLlmClient(), filters=mine)
    assert loose[0] == "INV-2026-0008"
    hits, total = search(
        db, mode="hybrid", q="toner", filters=mine, settings=SETTINGS, llm=FakeLlmClient()
    )
    assert total == 3 and hits[0].invoice.invoice_number == "INV-2026-0007"
    assert hits[0].score > hits[1].score  # in both lists beats in one


def test_hybrid_falls_back_to_keyword_without_the_model(db: Session, corpus: Document) -> None:
    found = numbers(db, mode="hybrid", q="toner", llm=None, filters=Filters(document_id=corpus.id))
    assert found == ["INV-2026-0007"]
    with pytest.raises(ValueError):
        numbers(db, mode="hybrid", q=None, llm=None)


class FixedQuery:
    """Embeds every query as the same vector, so the test controls the geometry."""

    def __init__(self, vector: list[float]) -> None:
        self.vector = vector

    def embed(self, *, model: str, texts: list[str], dim: int):  # type: ignore[no-untyped-def]
        from app.extract.llm import LlmUsage

        return [self.vector for _ in texts], LlmUsage("embed", model, len(texts), 0)


def test_semantic_search_sees_past_dead_index_entries(db: Session) -> None:
    """Deleted or reprocessed invoices leave dead entries in the HNSW graph until
    vacuum. An approximate index scan visits a fixed number of candidates
    (ef_search); if all of them are dead it returns nothing, though a live match
    exists. That emptied a bare cosine query in a test on 5 Nov 2026. Semantic
    search ranks exactly today (its plan does not use the HNSW index, even with
    sequential scans off); this test fails if a change ever makes it rely on it."""
    dim = SETTINGS.embed_dim
    query = [1.0] + [0.0] * (dim - 1)
    doc = Document(id=uuid.uuid4(), filename="live.pdf", sha256="1" * 64, size_bytes=1)
    db.add(doc)
    db.add(
        Invoice(
            document_id=doc.id, invoice_number="LIVE-1", embedding=[0.6, 0.8] + [0.0] * (dim - 2)
        )
    )
    db.flush()
    # 300 invoices closer to the query, inserted and rolled back: dead graph entries.
    ghosts = db.begin_nested()
    gone = Document(id=uuid.uuid4(), filename="gone.pdf", sha256="2" * 64, size_bytes=1)
    db.add(gone)
    for i in range(300):
        vector = [1.0, 0.001 * i] + [0.0] * (dim - 2)
        db.add(Invoice(document_id=gone.id, invoice_number=f"GONE-{i}", embedding=vector))
    db.flush()
    ghosts.rollback()
    # On a large table the planner picks the HNSW index; force that here.
    db.execute(text("SET LOCAL enable_seqscan = off"))
    hits, _ = search(
        db,
        mode="semantic",
        q="anything",
        filters=Filters(),
        settings=SETTINGS,
        llm=FixedQuery(query),
    )  # type: ignore[arg-type]
    assert [h.invoice.invoice_number for h in hits] == ["LIVE-1"]
