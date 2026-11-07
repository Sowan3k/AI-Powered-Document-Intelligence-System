"""R06 and R07: duplicates against every stored invoice, with fuzzy supplier names.

The invoice number or the date narrows the search through an index first;
`similarity()` from pg_trgm then compares supplier names, so "Acme Traders
Ltd" and "ACME TRADERS LIMITED" count as one supplier (D30). The database
only proposes candidates; the totals are compared as exact Decimals.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.enums import Severity
from app.db.models import Document, Invoice
from app.validate.rules import Issue

CANDIDATE_LIMIT = 5


def _same_supplier(invoice: Invoice, threshold: float):  # type: ignore[no-untyped-def]
    return or_(
        Invoice.supplier_norm == invoice.supplier_norm,
        func.similarity(Invoice.supplier_norm, invoice.supplier_norm) >= threshold,
    )


def _describe(other: Invoice, filename: str | None) -> dict[str, object]:
    return {
        "invoice_id": str(other.id),
        "document_id": str(other.document_id),
        "invoice_number": other.invoice_number,
        "filename": filename,
    }


def _where(invoice: Invoice, matches: list[tuple[Invoice, str | None]]) -> str:
    """Name the file that holds the other copy, so the reviewer need not hunt (D87)."""
    first, filename = matches[0]
    place = (
        "earlier in this file" if first.document_id == invoice.document_id else f'in "{filename}"'
    )
    others = len({o.document_id for o, _ in matches}) - 1
    if others > 0:
        place += f" and {others} other file{'s' if others > 1 else ''}"
    return place


def find_duplicates(session: Session, invoice: Invoice, threshold: float) -> list[Issue]:
    if not invoice.supplier_norm:
        return []
    issues: list[Issue] = []
    if invoice.invoice_number_norm:
        same = session.execute(
            select(Invoice, Document.filename)
            .join(Document, Document.id == Invoice.document_id)
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
                    f"already stored {_where(invoice, same)}",
                    "invoice_number",
                    {"matches": [_describe(o, f) for o, f in same]},
                )
            )
    if invoice.invoice_date is not None and invoice.total is not None:
        number_differs = or_(
            Invoice.invoice_number_norm.is_(None),
            Invoice.invoice_number_norm != (invoice.invoice_number_norm or ""),
        )
        alike = session.execute(
            select(Invoice, Document.filename)
            .join(Document, Document.id == Invoice.document_id)
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
            other = alike[0][0]
            # Either invoice may have no number at all, so say what the other one is.
            name = (
                f"invoice {other.invoice_number}"
                if other.invoice_number
                else "an invoice with no number"
            )
            issues.append(
                Issue(
                    "R07",
                    Severity.WARNING,
                    f"possible duplicate: same supplier, date and total as {name} "
                    f"{_where(invoice, alike)}",
                    "invoice_number",
                    {"matches": [_describe(o, f) for o, f in alike]},
                )
            )
    return issues
