"""Keyword, semantic and hybrid search over invoices, with the same filters.

Keyword mode matches the full-text vector with `websearch_to_tsquery`, so
people can type phrases, OR and -words, and ranks with `ts_rank`. Semantic
mode embeds the query with the D31 query format and orders by cosine
distance on the pgvector column. Hybrid mode (D68) takes the top results of
both and merges them by reciprocal rank fusion, so an exact invoice number
and a loose description both find what they mean; if the embedding model is
unavailable it falls back to keyword results. Filters narrow every mode in
SQL, with bound parameters only (security rule 6).
"""

import contextlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.db.enums import ReviewStatus
from app.db.models import Document, Invoice
from app.extract import prompts
from app.extract.llm import LlmClient, LlmError, require_model

Mode = Literal["keyword", "semantic", "hybrid"]
# Reciprocal rank fusion: score = sum of 1 / (RRF_K + rank) over both lists.
RRF_K = 60
HYBRID_CANDIDATES = 50  # taken from each list before merging


@dataclass
class Filters:
    supplier: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    currency: str | None = None
    status: ReviewStatus | None = None
    document_id: object | None = None


@dataclass
class Hit:
    invoice: Invoice
    filename: str
    score: float | None


def _filtered(query: Select, f: Filters, settings: Settings) -> Select:
    if f.supplier:
        name = f.supplier.lower()
        query = query.where(
            (Invoice.supplier_name.ilike(f"%{_escape(f.supplier)}%", escape="\\"))
            | (func.similarity(Invoice.supplier_norm, name) >= settings.supplier_similarity)
        )
    if f.date_from:
        query = query.where(Invoice.invoice_date >= f.date_from)
    if f.date_to:
        query = query.where(Invoice.invoice_date <= f.date_to)
    if f.amount_min is not None:
        query = query.where(Invoice.total >= f.amount_min)
    if f.amount_max is not None:
        query = query.where(Invoice.total <= f.amount_max)
    if f.currency:
        query = query.where(Invoice.currency == f.currency.upper())
    if f.status:
        query = query.where(Invoice.review_status == f.status)
    if f.document_id:
        query = query.where(Invoice.document_id == f.document_id)
    return query


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _base() -> Select:
    return (
        select(Invoice, Document.filename)
        .join(Document, Document.id == Invoice.document_id)
        .options(selectinload(Invoice.line_items))
    )


def search(
    session: Session,
    *,
    mode: Mode,
    q: str | None,
    filters: Filters,
    settings: Settings,
    llm: LlmClient | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Hit], int]:
    """Return one page of hits and the total count that matched."""
    query = _filtered(_base(), filters, settings)
    if mode == "hybrid":
        if not q:
            raise ValueError("hybrid search needs a query")
        return _hybrid(session, query, q, settings, llm, limit, offset)
    if mode == "semantic":
        if not q:
            raise ValueError("semantic search needs a query")
        return _semantic(session, query, q, settings, llm, limit, offset)
    if q:
        return _keyword(session, query, q, limit, offset)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.order_by(Invoice.invoice_date.desc().nulls_last(), Invoice.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [Hit(r[0], r[1], None) for r in rows], total


def _keyword(
    session: Session, query: Select, q: str, limit: int, offset: int
) -> tuple[list[Hit], int]:
    tsquery = func.websearch_to_tsquery("simple", q).op("||")(
        func.websearch_to_tsquery("english", q)
    )
    rank = func.ts_rank(Invoice.search_vector, tsquery)
    query = query.where(Invoice.search_vector.op("@@")(tsquery))
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.add_columns(rank.label("rank"))
        .order_by(rank.desc(), Invoice.invoice_date.desc().nulls_last(), Invoice.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [Hit(r[0], r[1], round(float(r[2]), 4)) for r in rows], total


def _semantic(
    session: Session,
    query: Select,
    q: str,
    settings: Settings,
    llm: LlmClient | None,
    limit: int,
    offset: int,
) -> tuple[list[Hit], int]:
    if llm is None:
        raise RuntimeError("semantic search needs the embedding model")
    model = require_model(settings.gemini_embed_model, "GEMINI_EMBED_MODEL")
    [vector], _ = llm.embed(model=model, texts=[prompts.embed_query(q)], dim=settings.embed_dim)
    distance = Invoice.embedding.cosine_distance(vector)
    query = query.where(Invoice.embedding.is_not(None))
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.add_columns(distance.label("distance"))
        .order_by(distance, Invoice.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [Hit(r[0], r[1], round(1 - float(r[2]), 4)) for r in rows], total


def _hybrid(
    session: Session,
    query: Select,
    q: str,
    settings: Settings,
    llm: LlmClient | None,
    limit: int,
    offset: int,
) -> tuple[list[Hit], int]:
    lists = [_keyword(session, query, q, HYBRID_CANDIDATES, 0)[0]]
    with contextlib.suppress(RuntimeError, LlmError):  # no embedding model: keyword alone
        lists.append(_semantic(session, query, q, settings, llm, HYBRID_CANDIDATES, 0)[0])
    scores: dict[object, float] = {}
    hits: dict[object, Hit] = {}
    for ranked in lists:
        for position, hit in enumerate(ranked, start=1):
            key = hit.invoice.id
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + position)
            hits.setdefault(key, hit)
    order = sorted(scores, key=lambda k: (-scores[k], str(k)))
    page = [
        Hit(hits[k].invoice, hits[k].filename, round(scores[k], 5))
        for k in order[offset : offset + limit]
    ]
    return page, len(order)
