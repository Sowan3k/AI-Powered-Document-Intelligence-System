"""Every rule against a clean invoice and against planted errors."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.db.enums import Severity
from app.validate.rules import InvoiceView, Issue, LineView, check_invoice

TODAY = date(2026, 11, 4)
D = Decimal


def meta(confidence: float = 0.95, flags: list[str] | None = None) -> dict:
    return {"confidence": confidence, "evidence": "x", "raw": "x", "flags": flags or []}


def clean() -> InvoiceView:
    names = ("invoice_number", "invoice_date", "supplier_name", "customer_name",
             "subtotal", "tax", "total", "currency")  # fmt: skip
    return InvoiceView(
        invoice_number="INV-1",
        invoice_date=date(2026, 10, 1),
        supplier_name="Acme Traders Ltd",
        customer_name="Riverside Clinic",
        subtotal=D("130.00"),
        tax=D("6.50"),
        total=D("136.50"),
        currency="USD",
        line_items=[
            LineView(1, D("2"), D("62.00"), D("124.00")),
            LineView(2, D("48"), D("0.125"), D("6.00")),
        ],
        field_meta={**{n: meta() for n in names}, "currencies_seen": ["USD"]},
    )


def run(inv: InvoiceView) -> list[Issue]:
    return check_invoice(
        inv, today=TODAY, tolerance=D("0.01"), confidence_threshold=0.7, max_age_years=10
    )


def codes(inv: InvoiceView, severity: Severity | None = None) -> list[str]:
    return [i.rule_code for i in run(inv) if severity is None or i.severity is severity]


def test_clean_invoice_has_no_issues() -> None:
    assert run(clean()) == []


@pytest.mark.parametrize("name", ["invoice_number", "invoice_date", "supplier_name", "total"])
def test_r01_required_field_missing(name: str) -> None:
    inv = replace(clean(), **{name: None})
    issues = [i for i in run(inv) if i.rule_code == "R01"]
    assert [(i.severity, i.field) for i in issues] == [(Severity.ERROR, name)]


@pytest.mark.parametrize("name", ["customer_name", "tax"])
def test_r01_recommended_field_missing_is_a_warning(name: str) -> None:
    inv = replace(clean(), **{name: None})
    if name == "tax":
        inv = replace(inv, total=D("130.00"))
    assert [(i.rule_code, i.severity) for i in run(inv)] == [("R01", Severity.WARNING)]


def test_r02_unparsed_and_negative() -> None:
    inv = clean()
    inv.total = None
    inv.field_meta["total"] = meta(0.0, ["unparsed"])
    issues = run(inv)
    assert ("R02", Severity.ERROR) in [(i.rule_code, i.severity) for i in issues]
    assert "R01" not in [i.rule_code for i in issues]  # not "missing": it was there, unreadable
    negative = replace(clean(), tax=D("-6.50"), total=D("123.50"))
    assert "R02" in codes(negative, Severity.ERROR)
    qty = clean()
    qty.line_items[0] = LineView(1, D("-2"), D("62.00"), D("-124.00"))
    assert "R02" in codes(qty)


def test_r03_line_sum() -> None:
    inv = replace(clean(), subtotal=D("135.00"), total=D("141.50"))
    [issue] = [i for i in run(inv) if i.rule_code == "R03"]
    assert issue.severity is Severity.ERROR
    assert issue.details == {"lines_sum": "130.00", "subtotal": "135.00", "difference": "5.00"}
    assert codes(inv) == ["R03"]


def test_r03_compares_with_total_when_no_subtotal_or_tax() -> None:
    inv = replace(clean(), subtotal=None, tax=None, total=D("131.00"))
    assert "R03" in codes(inv)
    assert "R03" not in codes(replace(inv, total=D("130.00")))


def test_r03_within_tolerance() -> None:
    assert "R03" not in codes(replace(clean(), subtotal=D("130.01"), total=D("136.51")))


def test_r04_line_math() -> None:
    inv = clean()
    inv.line_items[0] = LineView(1, D("2"), D("62.00"), D("125.00"))
    inv.subtotal, inv.total = D("131.00"), D("137.50")
    [issue] = run(inv)
    assert issue.rule_code == "R04" and issue.details["position"] == 1
    assert "2 x 62 is 124.00" in issue.message


def test_r04_rounds_half_up_like_an_invoice() -> None:
    inv = clean()
    inv.line_items = [LineView(1, D("3"), D("0.125"), D("0.38"))]  # 0.375 rounds to 0.38
    inv.subtotal, inv.tax, inv.total = D("0.38"), D("0"), D("0.38")
    assert run(inv) == []


def test_r05_total() -> None:
    inv = replace(clean(), total=D("146.50"))
    [issue] = run(inv)
    assert (issue.rule_code, issue.details["difference"]) == ("R05", "10.00")


def test_r05_without_tax() -> None:
    inv = replace(clean(), tax=None, total=D("140.00"))
    assert "R05" in codes(inv)


def test_r08_dates() -> None:
    assert codes(replace(clean(), invoice_date=date(2026, 11, 5))) == ["R08"]
    assert codes(replace(clean(), invoice_date=TODAY)) == []
    old = run(replace(clean(), invoice_date=date(2015, 1, 1)))
    assert [(i.rule_code, i.severity) for i in old] == [("R08", Severity.WARNING)]


def test_r09_low_confidence() -> None:
    inv = clean()
    inv.field_meta["total"] = meta(0.4)
    inv.field_meta["customer_name"] = meta(0.5)
    issues = {(i.field, i.severity) for i in run(inv) if i.rule_code == "R09"}
    assert issues == {("total", Severity.ERROR), ("customer_name", Severity.WARNING)}


def test_r09_ignores_null_fields() -> None:
    inv = replace(clean(), customer_name=None)
    inv.field_meta["customer_name"] = meta(0.0)
    assert "R09" not in codes(inv)


def test_r10_evidence_not_found() -> None:
    inv = clean()
    inv.field_meta["invoice_number"] = meta(0.9, ["evidence_not_found"])
    inv.field_meta["supplier_name"] = meta(0.9, ["evidence_not_found"])
    issues = {(i.field, i.severity) for i in run(inv) if i.rule_code == "R10"}
    assert issues == {("invoice_number", Severity.ERROR), ("supplier_name", Severity.WARNING)}


def test_r11_currency() -> None:
    assert codes(replace(clean(), currency=None)) == ["R11"]
    mixed = clean()
    mixed.field_meta["currencies_seen"] = ["USD", "EUR"]
    [issue] = run(mixed)
    assert (issue.rule_code, issue.severity) == ("R11", Severity.ERROR)


def test_messages_name_the_numbers() -> None:
    [issue] = run(replace(clean(), total=D("146.50")))
    assert "136.50" in issue.message and "146.50" in issue.message
