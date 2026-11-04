"""Live numbers for the whole system: outcomes, time, tokens and cost (D62).

Everything comes from tables the pipeline already writes: document status,
invoice review status, and the `llm_call` and `completed` events. Nothing
here holds document content.
"""

import statistics
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Integer, func, literal_column, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.pricing import PRICES_CHECKED, PRICES_USD_PER_M, cost_usd
from app.db.enums import DocumentStatus
from app.db.models import Document, Invoice, ProcessingEvent
from app.db.session import get_db

router = APIRouter(tags=["stats"], dependencies=[Depends(current_user)])

RECENT_DOCUMENTS = 1000  # processing time is measured over the latest documents


class ModelUsage(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    thinking_tokens: int  # billed as output
    cost_usd: float | None


class StatsResponse(BaseModel):
    documents: dict[str, int]
    success_rate: float | None  # completed / finished (completed + failed)
    failure_rate: float | None
    invoices: dict[str, int]
    processing_seconds_mean: float | None
    processing_seconds_p95: float | None
    tokens_input: int
    tokens_output: int
    tokens_thinking: int
    by_model: dict[str, ModelUsage]
    cost_usd: float | None  # None if a model has no listed price
    cost_per_completed_document_usd: float | None
    prices_checked: str
    prices_usd_per_million: dict[str, tuple[float, float]]


@router.get("/stats", response_model=StatsResponse)
def stats(db: Session = Depends(get_db)) -> StatsResponse:
    docs = {
        s.value: n
        for s, n in db.execute(select(Document.status, func.count()).group_by(Document.status))
    }
    done, failed = (
        docs.get(DocumentStatus.COMPLETED.value, 0),
        docs.get(DocumentStatus.FAILED.value, 0),
    )
    finished = done + failed
    invoices = {
        s.value: n
        for s, n in db.execute(
            select(Invoice.review_status, func.count()).group_by(Invoice.review_status)
        )
    }

    detail = ProcessingEvent.detail
    # An inline constant key, so SELECT and GROUP BY render the same expression.
    model_name = detail.op("->>")(literal_column("'model'"))
    rows = db.execute(
        select(
            model_name,
            func.count(),
            func.coalesce(func.sum(detail["prompt_tokens"].astext.cast(Integer)), 0),
            func.coalesce(func.sum(detail["output_tokens"].astext.cast(Integer)), 0),
            func.coalesce(func.sum(detail["thinking_tokens"].astext.cast(Integer)), 0),
        )
        .where(ProcessingEvent.event == "llm_call")
        .group_by(model_name)
    ).all()
    by_model = {
        str(model): ModelUsage(
            calls=calls,
            input_tokens=tin,
            output_tokens=tout,
            thinking_tokens=think,
            cost_usd=cost_usd(str(model), tin, tout + think),
        )
        for model, calls, tin, tout, think in rows
    }
    costs = [m.cost_usd for m in by_model.values()]
    total_cost = None if any(c is None for c in costs) else round(sum(c for c in costs if c), 6)

    first_start = (
        select(ProcessingEvent.document_id, func.min(ProcessingEvent.created_at).label("start"))
        .where(ProcessingEvent.event == "job_started")
        .group_by(ProcessingEvent.document_id)
        .subquery()
    )
    last_done = (
        select(ProcessingEvent.document_id, func.max(ProcessingEvent.created_at).label("end"))
        .where(ProcessingEvent.event == "completed")
        .group_by(ProcessingEvent.document_id)
        .subquery()
    )
    spans: list[tuple[datetime, datetime]] = db.execute(
        select(first_start.c.start, last_done.c.end)
        .join(last_done, last_done.c.document_id == first_start.c.document_id)
        .order_by(last_done.c.end.desc())
        .limit(RECENT_DOCUMENTS)
    ).all()  # type: ignore[assignment]
    seconds = sorted((end - start).total_seconds() for start, end in spans)
    p95 = seconds[min(len(seconds) - 1, int(round(0.95 * (len(seconds) - 1))))] if seconds else None

    return StatsResponse(
        documents=docs,
        success_rate=round(done / finished, 4) if finished else None,
        failure_rate=round(failed / finished, 4) if finished else None,
        invoices=invoices,
        processing_seconds_mean=round(statistics.fmean(seconds), 1) if seconds else None,
        processing_seconds_p95=round(p95, 1) if p95 is not None else None,
        tokens_input=sum(m.input_tokens for m in by_model.values()),
        tokens_output=sum(m.output_tokens for m in by_model.values()),
        tokens_thinking=sum(m.thinking_tokens for m in by_model.values()),
        by_model=by_model,
        cost_usd=total_cost,
        cost_per_completed_document_usd=round(total_cost / done, 6)
        if total_cost is not None and done
        else None,
        prices_checked=PRICES_CHECKED,
        prices_usd_per_million=PRICES_USD_PER_M,
    )
