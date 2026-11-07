"""Cross-verify two documents: a PDF against a PDF, or a PDF against a spreadsheet (D16).

Matching runs in two passes:

1. The same normalised invoice number.
2. For what is left: a similar supplier name (trigram score), the same date,
   and the same total within the money tolerance. A pair found this way
   whose numbers differ is reported as mismatched on `invoice_number`, which
   points at a misread or re-numbered invoice.

Each matched pair is compared field by field with exact Decimals. The report
lists matched pairs, mismatched pairs with the differing fields, and the
invoices found only in A or only in B. The model is not involved.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Document, Invoice, Reconciliation
from app.extract.normalise import norm_invoice_number, norm_supplier
from app.validate.similarity import similarity

COMPARED = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "subtotal",
    "tax",
    "total",
    "currency",
)


@dataclass
class Record:
    id: str
    invoice_number: str | None
    invoice_number_norm: str | None
    invoice_date: date | None
    supplier_name: str | None
    customer_name: str | None
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    currency: str | None
    where: str  # "pages 3-4" or "sheet row 12"

    @classmethod
    def of(cls, inv: Invoice) -> "Record":
        if inv.page_start is not None:
            same = inv.page_end in (None, inv.page_start)
            where = f"page {inv.page_start}" if same else f"pages {inv.page_start}-{inv.page_end}"
        else:
            same = inv.row_end in (None, inv.row_start)
            where = f"row {inv.row_start}" if same else f"rows {inv.row_start}-{inv.row_end}"
        return cls(
            id=str(inv.id),
            invoice_number=inv.invoice_number,
            invoice_number_norm=inv.invoice_number_norm,
            invoice_date=inv.invoice_date,
            supplier_name=inv.supplier_name,
            customer_name=inv.customer_name,
            subtotal=inv.subtotal,
            tax=inv.tax,
            total=inv.total,
            currency=inv.currency,
            where=where,
        )


def _plain(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _equal(name: str, a: object, b: object, tolerance: Decimal) -> bool:
    if name == "invoice_number" and (not a or not b):
        return True  # a blank number is why the fallback match exists; not a conflict
    if a is None or b is None:
        return a is b
    if isinstance(a, Decimal) and isinstance(b, Decimal):
        return abs(a - b) <= tolerance
    if name == "supplier_name":
        return norm_supplier(str(a)) == norm_supplier(str(b))
    if name == "invoice_number":
        return norm_invoice_number(str(a)) == norm_invoice_number(str(b))
    if isinstance(a, str) and isinstance(b, str):
        return " ".join(a.lower().split()) == " ".join(b.lower().split())
    return a == b


def _summary(r: Record) -> dict[str, Any]:
    return {
        "invoice_id": r.id,
        "invoice_number": r.invoice_number,
        "supplier_name": r.supplier_name,
        "invoice_date": _plain(r.invoice_date),
        "total": _plain(r.total),
        "where": r.where,
    }


def reconcile(
    a: list[Record], b: list[Record], *, tolerance: Decimal, supplier_similarity: float
) -> dict[str, Any]:
    left, right = list(a), list(b)
    pairs: list[tuple[Record, Record, str]] = []

    for ra in list(left):
        if not ra.invoice_number_norm:
            continue
        # Short numbers like "1001" repeat across suppliers: among the same number,
        # take the most similar supplier, not simply the first row (D88).
        same = [x for x in right if x.invoice_number_norm == ra.invoice_number_norm]
        rb = max(
            same,
            key=lambda x: similarity(
                norm_supplier(ra.supplier_name), norm_supplier(x.supplier_name)
            ),
            default=None,
        )
        if rb is not None:
            pairs.append((ra, rb, "invoice_number"))
            left.remove(ra)
            right.remove(rb)

    for ra in list(left):
        if ra.invoice_date is None or ra.total is None:
            continue
        candidates = [
            (similarity(norm_supplier(ra.supplier_name), norm_supplier(x.supplier_name)), x)
            for x in right
            if x.invoice_date == ra.invoice_date
            and x.total is not None
            and abs(x.total - ra.total) <= tolerance
        ]
        candidates = [c for c in candidates if c[0] >= supplier_similarity]
        if candidates:
            _, rb = max(candidates, key=lambda c: c[0])
            pairs.append((ra, rb, "supplier_date_total"))
            left.remove(ra)
            right.remove(rb)

    matched, mismatched = [], []
    for ra, rb, how in pairs:
        diffs = [
            {"field": name, "a": _plain(getattr(ra, name)), "b": _plain(getattr(rb, name))}
            for name in COMPARED
            if not _equal(name, getattr(ra, name), getattr(rb, name), tolerance)
        ]
        entry = {"a": _summary(ra), "b": _summary(rb), "matched_on": how}
        if diffs:
            mismatched.append({**entry, "differences": diffs})
        else:
            matched.append(entry)

    return {
        "summary": {
            "invoices_a": len(a),
            "invoices_b": len(b),
            "matched": len(matched),
            "mismatched": len(mismatched),
            "only_in_a": len(left),
            "only_in_b": len(right),
        },
        "matched": matched,
        "mismatched": mismatched,
        "only_in_a": [_summary(r) for r in left],
        "only_in_b": [_summary(r) for r in right],
    }


def _records(session: Session, document_id: uuid.UUID) -> list[Record]:
    invoices = session.scalars(
        select(Invoice)
        .where(Invoice.document_id == document_id)
        .order_by(Invoice.page_start, Invoice.row_start)
    )
    return [Record.of(inv) for inv in invoices]


def reconcile_documents(
    session: Session, document_a: uuid.UUID, document_b: uuid.UUID, settings: Settings
) -> Reconciliation:
    """Compare two stored documents and save the report. Commits."""
    if document_a == document_b:
        raise ValueError("choose two different documents")
    for doc_id in (document_a, document_b):
        if session.get(Document, doc_id) is None:
            raise ValueError(f"document {doc_id} not found")
    result = reconcile(
        _records(session, document_a),
        _records(session, document_b),
        tolerance=settings.money_tolerance,
        supplier_similarity=settings.supplier_similarity,
    )
    row = Reconciliation(document_a_id=document_a, document_b_id=document_b, result=result)
    session.add(row)
    session.commit()
    return row
