"""Manual corrections and the review queue."""

import logging
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import current_user
from app.api.routes.documents import invoice_detail
from app.api.schemas import InvoiceDetail, InvoiceOut, InvoicePatch, ReviewItem, ReviewPage
from app.core.config import Settings, get_settings
from app.db.enums import ReviewStatus, Severity
from app.db.models import Correction, Document, Invoice, ValidationIssue
from app.db.session import get_db
from app.extract.normalise import norm_invoice_number, norm_supplier
from app.search.index import refresh_search_vector
from app.validate.service import validate_invoice
from app.worker import queue

logger = logging.getLogger(__name__)
router = APIRouter(tags=["invoices"], dependencies=[Depends(current_user)])

EDITABLE = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "subtotal",
    "tax",
    "total",
    "currency",
)


def _json(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


@router.patch("/invoices/{invoice_id}", response_model=InvoiceDetail, responses={404: {}})
def correct_invoice(
    invoice_id: uuid.UUID,
    patch: InvoicePatch,
    user: str = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> InvoiceDetail:
    """Save corrections, record who changed what, re-run validation and refresh search."""
    invoice = db.scalars(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .options(selectinload(Invoice.line_items), selectinload(Invoice.issues))
    ).first()
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    meta = dict(invoice.field_meta or {})
    changed = []
    for name in EDITABLE:
        if name not in patch.model_fields_set:
            continue
        new = getattr(patch, name)
        if name == "currency" and new is not None:
            new = new.upper()
        if isinstance(new, str) and not new:
            new = None
        old = getattr(invoice, name)
        if old == new:
            continue
        setattr(invoice, name, new)
        db.add(
            Correction(
                invoice_id=invoice.id,
                field=name,
                old_value=_json(old),
                new_value=_json(new),
                username=user,
            )
        )
        meta[name] = {
            "confidence": 1.0,
            "evidence": f"corrected by {user}",
            "raw": None if new is None else str(_json(new)),
            "flags": ["corrected"],
        }
        changed.append(name)
    if "currency" in changed:
        meta["currencies_seen"] = [invoice.currency] if invoice.currency else []
    invoice.field_meta = meta
    invoice.invoice_number_norm = norm_invoice_number(invoice.invoice_number)
    invoice.supplier_norm = norm_supplier(invoice.supplier_name)
    if changed:
        refresh_search_vector(invoice)
        invoice.embedding = None  # the worker embeds it again
        if not queue.active_job(db, invoice.document_id, queue.JOB_INDEX):
            queue.enqueue(db, invoice.document_id, queue.JOB_INDEX, settings)
    db.flush()
    validate_invoice(db, invoice, settings)
    if patch.mark_reviewed:
        invoice.review_status = ReviewStatus.REVIEWED
    db.commit()
    db.refresh(invoice)
    logger.info(
        "invoice %s corrected: fields=%s reviewed=%s", invoice.id, changed, patch.mark_reviewed
    )
    return invoice_detail(invoice)


@router.get("/review-queue", response_model=ReviewPage)
def review_queue(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ReviewPage:
    """Invoices with at least one error-level issue, oldest first."""
    query = (
        select(Invoice, Document.filename, Document.mime_type)
        .join(Document, Document.id == Invoice.document_id)
        .where(Invoice.review_status == ReviewStatus.NEEDS_REVIEW)
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(Invoice.created_at).limit(limit).offset(offset)).all()
    ids = [r[0].id for r in rows]
    counts: dict[tuple[uuid.UUID, Severity], int] = {}
    top: dict[uuid.UUID, str] = {}
    if ids:
        for issue in db.scalars(
            select(ValidationIssue)
            .where(
                ValidationIssue.invoice_id.in_(ids),
                ValidationIssue.resolved.is_(False),
                ValidationIssue.severity == Severity.ERROR,
            )
            .order_by(ValidationIssue.id)
        ):
            top.setdefault(issue.invoice_id, issue.message)
        for inv_id, severity, n in db.execute(
            select(ValidationIssue.invoice_id, ValidationIssue.severity, func.count())
            .where(ValidationIssue.invoice_id.in_(ids), ValidationIssue.resolved.is_(False))
            .group_by(ValidationIssue.invoice_id, ValidationIssue.severity)
        ):
            counts[(inv_id, severity)] = n
    items = [
        ReviewItem(
            **InvoiceOut.model_validate(inv).model_dump(),
            filename=filename,
            mime_type=mime_type,
            error_count=counts.get((inv.id, Severity.ERROR), 0),
            warning_count=counts.get((inv.id, Severity.WARNING), 0),
            top_issue=top.get(inv.id),
        )
        for inv, filename, mime_type in rows
    ]
    return ReviewPage(items=items, total=total, limit=limit, offset=offset)
