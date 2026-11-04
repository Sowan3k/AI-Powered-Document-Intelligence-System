"""Keep each invoice searchable: full-text vector and embedding (D23, D31).

The full-text vector gives names and numbers weight A and line item
descriptions weight B. Each part is indexed twice: with `simple`, so codes
like "INV-2026-0007" stay whole, and with `english`, so "cartridges" finds
"cartridge". The query is built from both configurations too, and each half
needs its own forms in the index, or a negated word ("-acme") would slip
through the half that stems it differently.

The embedding text follows the D31 document format exactly. Embeddings are
made in the worker, never in an API request: a correction clears the
invoice's embedding and queues an `index` job.
"""

import logging
import uuid

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Invoice
from app.extract import prompts
from app.extract.llm import LlmClient, LlmUsage

logger = logging.getLogger(__name__)

EMBED_BATCH = 50


def head_text(inv: Invoice) -> str:
    parts = [inv.invoice_number, inv.supplier_name, inv.customer_name, inv.currency]
    return " ".join(p for p in parts if p)


def body_text(inv: Invoice) -> str:
    return " ".join(li.description for li in inv.line_items if li.description)


# Weights are inline literals: setweight() takes PostgreSQL's "char" type,
# which a bound string parameter (varchar) does not convert to.
WEIGHT_A = literal_column("'A'")
WEIGHT_B = literal_column("'B'")


def _both(text: str):  # type: ignore[no-untyped-def]
    """Index text in both forms, so each half of the search query finds its own words."""
    return func.to_tsvector("simple", text).op("||")(func.to_tsvector("english", text))


def refresh_search_vector(inv: Invoice) -> None:
    head = func.setweight(_both(head_text(inv)), WEIGHT_A)
    body = func.setweight(_both(body_text(inv)), WEIGHT_B)
    inv.search_vector = head.op("||")(body)


def embedding_text(inv: Invoice) -> str:
    number = inv.invoice_number or "without number"
    title = f"Invoice {number} from {inv.supplier_name or 'unknown supplier'}"
    facts = [
        f"Customer: {inv.customer_name}" if inv.customer_name else None,
        f"Date: {inv.invoice_date.isoformat()}" if inv.invoice_date else None,
        f"Total: {inv.total} {inv.currency or ''}".strip() if inv.total is not None else None,
        f"Items: {'; '.join(d for d in (li.description for li in inv.line_items) if d)}"
        if inv.line_items
        else None,
    ]
    return prompts.embed_document(title, ". ".join(f for f in facts if f))


def index_document(
    session: Session, llm: LlmClient | None, document_id: uuid.UUID, settings: Settings
) -> list[LlmUsage]:
    """Refresh every invoice's search vector, and embed those without an embedding."""
    invoices = list(session.scalars(select(Invoice).where(Invoice.document_id == document_id)))
    for inv in invoices:
        refresh_search_vector(inv)
    session.flush()
    usages: list[LlmUsage] = []
    missing = [inv for inv in invoices if inv.embedding is None]
    if missing and (llm is None or not settings.gemini_embed_model):
        logger.warning("document %s: no embedding model, semantic search skips it", document_id)
    elif missing and llm is not None and settings.gemini_embed_model:
        for start in range(0, len(missing), EMBED_BATCH):
            batch = missing[start : start + EMBED_BATCH]
            vectors, usage = llm.embed(
                model=settings.gemini_embed_model,
                texts=[embedding_text(inv) for inv in batch],
                dim=settings.embed_dim,
            )
            usages.append(usage)
            for inv, vector in zip(batch, vectors, strict=True):
                inv.embedding = vector
    session.commit()
    return usages
