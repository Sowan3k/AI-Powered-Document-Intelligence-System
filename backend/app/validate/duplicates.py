"""R06 and R07: duplicates against every stored invoice, with fuzzy supplier names.

The invoice number or the date narrows the search through an index first;
`similarity()` from pg_trgm then compares supplier names, so "Acme Traders
Ltd" and "ACME TRADERS LIMITED" count as one supplier (D30). The database
only proposes candidates; the totals are compared as exact Decimals.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.enums import Severity
from app.db.models import Invoice
from app.validate.rules import Issue

CANDIDATE_LIMIT = 5


def _same_supplier(invoice: Invoice, threshold: float):  # type: ignore[no-untyped-def]
    return or_(
        Invoice.supplier_norm == invoice.supplier_norm,
        func.similarity(Invoice.supplier_norm, invoice.supplier_norm) >= threshold,
    )


def _describe(other: Invoice) -> dict[str, object]:
    return {
        "invoice_id": str(other.id),
        "document_id": str(other.document_id),
        "invoice_number": other.invoice_number,
    }


def find_duplicates(session: Session, invoice: Invoice, threshold: float) -> list[Issue]:
    if not invoice.supplier_norm:
        return []
    issues: list[Issue] = []
    if invoice.invoice_number_norm:
        same = session.scalars(
            select(Invoice)
            .where(
                Invoice.id != invoice.id,
                Invoice.invoice_number_norm == invoice.invoice_number_norm,
                _same_supplier(invoice, threshold),
            )
            .order_by(Invoice.created_at)
            .limit(CANDIDATE_LIMIT)
        ).all()
        if same:
            issues.append(
                Issue(
                    "R06",
                    Severity.ERROR,
                    f"duplicate: invoice {invoice.invoice_number} from this supplier is "
                    f"already stored ({len(same)} match{'es' if len(same) > 1 else ''})",
                    "invoice_number",
                    {"matches": [_describe(o) for o in same]},
                )
            )
    if invoice.invoice_date is not None and invoice.total is not None:
        number_differs = or_(
            Invoice.invoice_number_norm.is_(None),
            Invoice.invoice_number_norm != (invoice.invoice_number_norm or ""),
        )
        alike = session.scalars(
            select(Invoice)
            .where(
                Invoice.id != invoice.id,
                Invoice.invoice_date == invoice.invoice_date,
                Invoice.total == invoice.total,
                number_differs,
                _same_supplier(invoice, threshold),
            )
            .order_by(Invoice.created_at)
            .limit(CANDIDATE_LIMIT)
        ).all()
        if alike:
            issues.append(
                Issue(
                    "R07",
                    Severity.WARNING,
                    "possible duplicate: same supplier, date and total under another number",
                    "invoice_number",
                    {"matches": [_describe(o) for o in alike]},
                )
            )
    return issues
