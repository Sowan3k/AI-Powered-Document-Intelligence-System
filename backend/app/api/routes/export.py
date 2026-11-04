"""Invoices as a CSV file that opens in Excel, for entry into other systems.

The file starts with a UTF-8 byte order mark, so Excel shows Bengali and
other non-Latin text correctly. Text from documents is untrusted: a cell
that starts with = + - @ or a tab could run as a formula in Excel (CSV
injection), so such text cells get a leading apostrophe. Numbers are
written by this code and never escaped.
"""

import csv
import io
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import current_user
from app.db.enums import ReviewStatus
from app.db.models import Document, Invoice
from app.db.session import get_db
from app.validate.service import adjustments_of

router = APIRouter(tags=["export"], dependencies=[Depends(current_user)])

MAX_ROWS = 20_000  # about 4 MB: safe on the 512 MB instance
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
HEADERS = [
    "Invoice number", "Invoice date", "Supplier", "Customer", "Currency", "Subtotal", "Tax",
    "Discounts and charges", "Total", "Review status", "Open issues", "First issue", "File",
    "Pages or rows", "Invoice ID",
]  # fmt: skip


def safe_text(value: str | None) -> str:
    if not value:
        return ""
    return "'" + value if value.startswith(FORMULA_START) else value


def _money(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _where(inv: Invoice) -> str:
    if inv.page_start is not None:
        end = inv.page_end or inv.page_start
        return (
            f"page {inv.page_start}" if end == inv.page_start else f"pages {inv.page_start}-{end}"
        )
    if inv.row_start is not None:
        return f"rows {inv.row_start}-{inv.row_end or inv.row_start}"
    return ""


@router.get(
    "/export/invoices.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV with a UTF-8 BOM"}},
)
def export_invoices(
    review_status: ReviewStatus | None = Query(default=None),
    document_id: list[uuid.UUID] | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
) -> Response:
    """Every extracted invoice (newest first, up to 20,000), optionally by review
    status or for the marked documents only (repeat `document_id`)."""
    query = (
        select(Invoice, Document.filename)
        .join(Document, Document.id == Invoice.document_id)
        .options(selectinload(Invoice.issues))
        .order_by(Invoice.created_at.desc(), Invoice.id)
        .limit(MAX_ROWS)
    )
    if review_status is not None:
        query = query.where(Invoice.review_status == review_status)
    if document_id:
        query = query.where(Invoice.document_id.in_(document_id))

    out = io.StringIO()
    out.write("﻿")
    writer = csv.writer(out)
    writer.writerow(HEADERS)
    for inv, filename in db.execute(query):
        adjustments = adjustments_of(inv.field_meta or {})
        adjusted = sum((a.amount for a in adjustments if a.amount is not None), Decimal(0))
        open_issues = [i for i in inv.issues if not i.resolved]
        writer.writerow(
            [
                safe_text(inv.invoice_number),
                inv.invoice_date.isoformat() if inv.invoice_date else "",
                safe_text(inv.supplier_name),
                safe_text(inv.customer_name),
                inv.currency or "",
                _money(inv.subtotal),
                _money(inv.tax),
                _money(adjusted) if adjustments else "",
                _money(inv.total),
                inv.review_status.value,
                len(open_issues),
                safe_text(open_issues[0].message) if open_issues else "",
                safe_text(filename),
                _where(inv),
                str(inv.id),
            ]
        )
    name = f"docintel-invoices-{date.today().isoformat()}.csv"
    return Response(
        content=out.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
