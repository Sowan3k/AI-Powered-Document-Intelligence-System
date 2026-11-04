"""GET /api/search: keyword (full text) or semantic (embeddings), with filters."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_llm
from app.api.schemas import InvoiceOut, LineItemOut, SearchHit, SearchResponse
from app.core.config import Settings, get_settings
from app.db.enums import ReviewStatus
from app.db.session import get_db
from app.extract.llm import LlmClient, LlmError
from app.search.service import Filters, search

router = APIRouter(tags=["search"], dependencies=[Depends(current_user)])


@router.get("/search", response_model=SearchResponse, responses={400: {}, 503: {}})
def search_invoices(
    mode: Literal["keyword", "semantic"] = "keyword",
    q: str | None = Query(
        None, max_length=300, description="Words, or a question in semantic mode"
    ),
    supplier: str | None = Query(None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: Decimal | None = Query(None, ge=0),
    amount_max: Decimal | None = Query(None, ge=0),
    currency: str | None = Query(None, pattern=r"^[A-Za-z]{3}$"),
    status_filter: ReviewStatus | None = Query(None, alias="status"),
    document_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    llm: LlmClient | None = Depends(get_llm),
) -> SearchResponse:
    filters = Filters(
        supplier=supplier,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        currency=currency,
        status=status_filter,
        document_id=document_id,
    )
    query = q.strip() if q and q.strip() else None
    try:
        hits, total = search(
            db, mode=mode, q=query, filters=filters, settings=settings, llm=llm,
            limit=limit, offset=offset,
        )  # fmt: skip
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except (RuntimeError, LlmError):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "semantic search is not available right now"
        ) from None
    items = [
        SearchHit(
            **InvoiceOut.model_validate(h.invoice).model_dump(),
            filename=h.filename,
            score=h.score,
            line_items=[LineItemOut.model_validate(li) for li in h.invoice.line_items],
        )
        for h in hits
    ]
    return SearchResponse(
        mode=mode, query=query, items=items, total=total, limit=limit, offset=offset
    )
