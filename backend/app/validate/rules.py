"""Validation rules R01 to R11, in plain Python with Decimal (D09).

Each rule reads an `InvoiceView` and returns issues. Nothing here asks the
model anything. The duplicate rules R06 and R07 need the database and live
in `duplicates.py`; the rest are pure functions, tested one by one.

Severity decides the review status: any `error` sends the invoice to
`needs_review`. Warnings are shown but do not block.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.db.enums import Severity

REQUIRED = ("invoice_number", "invoice_date", "supplier_name", "total")
RECOMMENDED = ("customer_name", "tax")
CENT = Decimal("0.01")


@dataclass
class Issue:
    rule_code: str
    severity: Severity
    message: str
    field: str | None = None
    details: dict[str, Any] | None = None


@dataclass
class LineView:
    position: int
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None


@dataclass
class AdjustmentView:
    label: str
    amount: Decimal | None  # discounts are negative; None when unreadable


@dataclass
class InvoiceView:
    """The values the rules need, independent of the ORM."""

    invoice_number: str | None = None
    invoice_date: date | None = None
    supplier_name: str | None = None
    customer_name: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    line_items: list[LineView] = field(default_factory=list)
    adjustments: list[AdjustmentView] = field(default_factory=list)
    field_meta: dict[str, Any] = field(default_factory=dict)

    def adjustments_sum(self) -> Decimal:
        return sum((a.amount for a in self.adjustments if a.amount is not None), Decimal(0))

    def meta(self, name: str) -> dict[str, Any]:
        value = self.field_meta.get(name)
        return value if isinstance(value, dict) else {}

    def flags(self, name: str) -> list[str]:
        return list(self.meta(name).get("flags") or [])


def _money(value: Decimal) -> str:
    return str(value.quantize(CENT))


def r01_missing(inv: InvoiceView) -> list[Issue]:
    issues = []
    for name in REQUIRED:
        if getattr(inv, name) is None and "unparsed" not in inv.flags(name):
            issues.append(Issue("R01", Severity.ERROR, f"{name} is missing", name))
    for name in RECOMMENDED:
        if getattr(inv, name) is None and "unparsed" not in inv.flags(name):
            issues.append(Issue("R01", Severity.WARNING, f"{name} is not shown", name))
    return issues


def r02_bad_values(inv: InvoiceView) -> list[Issue]:
    issues = []
    for name, meta in inv.field_meta.items():
        if not isinstance(meta, dict):
            continue
        flags = meta.get("flags") or []
        if "unparsed" in flags:
            issues.append(
                Issue(
                    "R02",
                    Severity.ERROR,
                    f"{name} could not be read as a value",
                    name,
                    {"raw": meta.get("raw")},
                )
            )
        if "out_of_range" in flags:
            issues.append(Issue("R02", Severity.ERROR, f"{name} is too large to be real", name))
    for name in ("subtotal", "tax", "total"):
        value = getattr(inv, name)
        if value is not None and value < 0:
            issues.append(
                Issue("R02", Severity.ERROR, f"{name} is negative ({_money(value)})", name)
            )
    for li in inv.line_items:
        if li.quantity is not None and li.quantity < 0:
            issues.append(
                Issue(
                    "R02",
                    Severity.ERROR,
                    f"line {li.position}: quantity is negative",
                    "line_items",
                    {"position": li.position},
                )
            )
    return issues


def r03_line_sum(inv: InvoiceView, tolerance: Decimal) -> list[Issue]:
    """Line amounts must add up to the subtotal (or to the total when no tax or subtotal)."""
    if not inv.line_items or any(li.amount is None for li in inv.line_items):
        return []
    if inv.subtotal is not None:
        target, name = inv.subtotal, "subtotal"
    elif inv.tax is None and inv.total is not None:
        # No subtotal: lines plus any discount or charge must reach the total.
        target, name = inv.total - inv.adjustments_sum(), "total"
    else:
        return []
    lines = sum((li.amount for li in inv.line_items if li.amount is not None), Decimal(0))
    if abs(lines - target) <= tolerance:
        return []
    return [
        Issue(
            "R03",
            Severity.ERROR,
            f"line items add up to {_money(lines)}, but the {name} is {_money(target)}",
            name,
            {
                "lines_sum": _money(lines),
                name: _money(target),
                "difference": _money(target - lines),
            },
        )
    ]


def r04_line_math(inv: InvoiceView, tolerance: Decimal) -> list[Issue]:
    issues = []
    for li in inv.line_items:
        if li.quantity is None or li.unit_price is None or li.amount is None:
            continue
        expected = (li.quantity * li.unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
        if abs(expected - li.amount) > tolerance:
            issues.append(
                Issue(
                    "R04",
                    Severity.ERROR,
                    f"line {li.position}: {li.quantity.normalize():f} x "
                    f"{li.unit_price.normalize():f} is {_money(expected)}, "
                    f"but the amount is {_money(li.amount)}",
                    "line_items",
                    {
                        "position": li.position,
                        "expected": _money(expected),
                        "amount": _money(li.amount),
                    },
                )
            )
    return issues


def r05_total(inv: InvoiceView, tolerance: Decimal) -> list[Issue]:
    if inv.subtotal is None or inv.total is None:
        return []
    unreadable = [a.label for a in inv.adjustments if a.amount is None]
    if unreadable:
        return [
            Issue(
                "R05",
                Severity.ERROR,
                f'the amount of "{unreadable[0]}" could not be read, so the total is unchecked',
                "total",
                {"unreadable": unreadable},
            )
        ]
    tax = inv.tax or Decimal(0)
    expected = inv.subtotal + tax + inv.adjustments_sum()
    if abs(expected - inv.total) <= tolerance:
        return []
    shown = "subtotal plus tax" if inv.tax is not None else "subtotal (no tax shown)"
    if inv.adjustments:
        parts = ", ".join(f"{a.label} {_money(a.amount)}" for a in inv.adjustments if a.amount)
        shown += f" and {parts}"
    return [
        Issue(
            "R05",
            Severity.ERROR,
            f"{shown} is {_money(expected)}, but the total is {_money(inv.total)}",
            "total",
            {
                "expected": _money(expected),
                "total": _money(inv.total),
                "difference": _money(inv.total - expected),
            },
        )
    ]


def r08_date(inv: InvoiceView, today: date, max_age_years: int) -> list[Issue]:
    if inv.invoice_date is None:
        return []
    if inv.invoice_date > today:
        return [
            Issue(
                "R08",
                Severity.ERROR,
                f"invoice date {inv.invoice_date.isoformat()} is in the future",
                "invoice_date",
            )
        ]
    try:
        oldest = today.replace(year=today.year - max_age_years)
    except ValueError:  # 29 February
        oldest = today.replace(year=today.year - max_age_years, day=28)
    if inv.invoice_date < oldest:
        return [
            Issue(
                "R08",
                Severity.WARNING,
                f"invoice date {inv.invoice_date.isoformat()} is more than "
                f"{max_age_years} years old",
                "invoice_date",
            )
        ]
    return []


def r09_confidence(inv: InvoiceView, threshold: float) -> list[Issue]:
    issues = []
    for name, meta in inv.field_meta.items():
        if not isinstance(meta, dict) or getattr(inv, name, None) is None:
            continue
        confidence = meta.get("confidence")
        if confidence is None or confidence >= threshold:
            continue
        severity = Severity.ERROR if name in REQUIRED else Severity.WARNING
        issues.append(
            Issue(
                "R09",
                severity,
                f"{name} was read with low confidence ({confidence:.2f})",
                name,
                {"confidence": confidence, "threshold": threshold},
            )
        )
    return issues


def r10_evidence(inv: InvoiceView) -> list[Issue]:
    issues = []
    for name, meta in inv.field_meta.items():
        if isinstance(meta, dict) and "evidence_not_found" in (meta.get("flags") or []):
            severity = Severity.ERROR if name in ("invoice_number", "total") else Severity.WARNING
            issues.append(
                Issue(
                    "R10",
                    severity,
                    f"{name} does not appear in the source text",
                    name,
                    {"evidence": meta.get("evidence")},
                )
            )
    return issues


def r11_currency(inv: InvoiceView) -> list[Issue]:
    seen = inv.field_meta.get("currencies_seen") or []
    if len(set(seen)) > 1:
        return [
            Issue(
                "R11",
                Severity.ERROR,
                f"more than one currency on one invoice: {', '.join(seen)}",
                "currency",
                {"currencies": seen},
            )
        ]
    if inv.currency is None:
        return [Issue("R11", Severity.WARNING, "currency is missing", "currency")]
    return []


def check_invoice(
    inv: InvoiceView,
    *,
    today: date,
    tolerance: Decimal,
    confidence_threshold: float,
    max_age_years: int,
) -> list[Issue]:
    """Every rule that needs only this invoice. R06 and R07 run in duplicates.py."""
    return [
        *r01_missing(inv),
        *r02_bad_values(inv),
        *r03_line_sum(inv, tolerance),
        *r04_line_math(inv, tolerance),
        *r05_total(inv, tolerance),
        *r08_date(inv, today, max_age_years),
        *r09_confidence(inv, confidence_threshold),
        *r10_evidence(inv),
        *r11_currency(inv),
    ]
