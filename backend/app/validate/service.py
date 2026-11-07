"""Run every rule on stored invoices and save the issues.

Validating again replaces the invoice's open issues, so a correction (Phase 4)
can re-run validation safely. Any error-level issue sets the invoice to
`needs_review`; otherwise it becomes `ok`. An invoice a person has already
marked `reviewed` keeps that status, and its new issues are still recorded.
"""

import logging
import uuid
from collections import Counter
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import ReviewStatus, Severity
from app.db.models import Document, Invoice, Job, ProcessingEvent, ValidationIssue
from app.validate.duplicates import find_duplicates
from app.validate.rules import AdjustmentView, InvoiceView, Issue, LineView, check_invoice

logger = logging.getLogger(__name__)


def view_of(invoice: Invoice) -> InvoiceView:
    return InvoiceView(
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        supplier_name=invoice.supplier_name,
        customer_name=invoice.customer_name,
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        total=invoice.total,
        currency=invoice.currency,
        line_items=[
            LineView(li.position, li.quantity, li.unit_price, li.amount)
            for li in invoice.line_items
        ],
        adjustments=adjustments_of(invoice.field_meta or {}),
        field_meta=dict(invoice.field_meta or {}),
    )


def adjustments_of(meta: dict) -> list[AdjustmentView]:
    """Discounts and charges as stored by extraction in field_meta (D57)."""
    out = []
    for a in meta.get("adjustments") or []:
        amount = a.get("amount")
        out.append(
            AdjustmentView(a.get("label") or "Adjustment", Decimal(amount) if amount else None)
        )
    return out


def validate_invoice(
    session: Session, invoice: Invoice, settings: Settings, today: date | None = None
) -> list[Issue]:
    issues = check_invoice(
        view_of(invoice),
        today=today or date.today(),
        tolerance=settings.money_tolerance,
        confidence_threshold=settings.field_confidence_threshold,
        max_age_years=settings.max_invoice_age_years,
    )
    issues += find_duplicates(session, invoice, settings.supplier_similarity)
    session.execute(
        delete(ValidationIssue).where(
            ValidationIssue.invoice_id == invoice.id, ValidationIssue.resolved.is_(False)
        )
    )
    for issue in issues:
        session.add(
            ValidationIssue(
                invoice_id=invoice.id,
                rule_code=issue.rule_code,
                severity=issue.severity,
                field=issue.field,
                message=issue.message,
                details=issue.details,
            )
        )
    if invoice.review_status is not ReviewStatus.REVIEWED:
        has_error = any(i.severity is Severity.ERROR for i in issues)
        invoice.review_status = ReviewStatus.NEEDS_REVIEW if has_error else ReviewStatus.OK
    return issues


def recheck_copies_of(session: Session, gone: set[uuid.UUID], settings: Settings) -> int:
    """Check again every invoice flagged as a copy of one that no longer exists
    (its document was deleted, re-uploaded or cancelled), so no stale duplicate
    flag stays behind (D87). Returns how many were checked. Commits."""
    if not gone:
        return 0
    ids = {str(g) for g in gone}
    affected: set[uuid.UUID] = set()
    for issue in session.scalars(
        select(ValidationIssue).where(
            ValidationIssue.rule_code.in_(("R06", "R07")), ValidationIssue.resolved.is_(False)
        )
    ):
        matches = (issue.details or {}).get("matches") or []
        if any(isinstance(m, dict) and m.get("invoice_id") in ids for m in matches):
            affected.add(issue.invoice_id)
    affected -= gone
    for invoice_id in affected:
        invoice = session.get(Invoice, invoice_id)
        if invoice is not None:
            validate_invoice(session, invoice, settings)
    session.commit()
    return len(affected)


def validate_document(
    session: Session,
    document_id: uuid.UUID,
    settings: Settings,
    job: Job | None = None,
    today: date | None = None,
) -> Counter[str]:
    """Validate every invoice of a document. Returns issue counts by rule code."""
    document = session.get(Document, document_id)
    if document is None:
        raise ValueError(f"document {document_id} not found")
    invoices = session.scalars(
        select(Invoice)
        .where(Invoice.document_id == document_id)
        .order_by(Invoice.page_start, Invoice.row_start, Invoice.created_at)
    ).all()
    counts: Counter[str] = Counter()
    review = 0
    for invoice in invoices:
        session.flush()  # earlier invoices of this document are visible to R06 and R07
        found = validate_invoice(session, invoice, settings, today)
        counts.update(i.rule_code for i in found)
        review += invoice.review_status is ReviewStatus.NEEDS_REVIEW
    session.add(
        ProcessingEvent(
            document_id=document.id,
            job_id=job.id if job else None,
            event="validated",
            detail={"invoices": len(invoices), "needs_review": review, "issues": dict(counts)},
        )
    )
    session.commit()
    logger.info("validate %s: invoices=%d needs_review=%d", document.id, len(invoices), review)
    return counts
