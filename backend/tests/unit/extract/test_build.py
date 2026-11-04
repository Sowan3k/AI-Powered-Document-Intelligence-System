"""From the model's printed strings to typed values, with evidence checks."""

from datetime import date
from decimal import Decimal

from app.extract.build import build_invoice
from app.extract.evidence import is_proven
from app.extract.schemas import LlmField, LlmInvoice
from tests.unit.extract.helpers import fld, line, llm_invoice

SOURCE = """ACME TRADERS LTD
Invoice No: INV-2026-00007     Date: 03/10/2026
Bill To: Riverside Clinic
Toner cartridge   2   $62.00   $124.00
Subtotal: $124.00
Tax (5%): $6.20
Total:    $130.20
"""


def build(**values) -> object:  # type: ignore[no-untyped-def]
    return build_invoice(LlmInvoice.model_validate(llm_invoice(**values)), SOURCE)


def test_typed_values() -> None:
    inv = build(
        invoice_number=fld("INV-2026-00007", "Invoice No: INV-2026-00007"),
        invoice_date=fld("03/10/2026", "Date: 03/10/2026"),
        supplier_name=fld("Acme Traders Ltd", "ACME TRADERS LTD"),
        customer_name=fld("Riverside Clinic"),
        subtotal=fld("$124.00", "Subtotal: $124.00"),
        tax=fld("$6.20", "Tax (5%): $6.20"),
        total=fld("$130.20", "Total:    $130.20"),
        currency=fld("$", "$130.20"),
        items=[line(1, "Toner cartridge", "2", "$62.00", "$124.00")],
    )
    assert inv.invoice_number.value == "INV-2026-00007"
    assert inv.invoice_date.value == date(2026, 10, 3)
    assert "ambiguous_date" in inv.invoice_date.flags
    assert inv.total.value == Decimal("130.20")
    assert inv.tax.value == Decimal("6.20")
    assert inv.currency.value == "USD" and "symbol_only" in inv.currency.flags
    assert inv.line_items[0].quantity == Decimal("2")
    assert inv.line_items[0].amount == Decimal("124.00")
    for name in ("invoice_number", "supplier_name", "total", "subtotal"):
        assert "evidence_not_found" not in inv.field(name).flags, name


def test_missing_values_stay_null() -> None:
    inv = build(invoice_number="INV-2026-00007")
    for name in ("customer_name", "tax", "total", "invoice_date", "currency"):
        assert inv.field(name).value is None, name
        assert inv.field(name).flags == [], name
    assert inv.line_items == []


def test_invented_value_is_flagged_and_loses_confidence() -> None:
    inv = build(
        invoice_number=fld("INV-9999", "Invoice No: INV-9999", confidence=0.9),
        total=fld("$999.00", "Total: $999.00", confidence=0.8),
    )
    assert inv.invoice_number.value == "INV-9999"  # kept, but not trusted
    assert "evidence_not_found" in inv.invoice_number.flags
    assert inv.invoice_number.confidence == 0.45
    assert "evidence_not_found" in inv.total.flags


def test_evidence_that_does_not_show_the_value() -> None:
    field = LlmField(value="$500.00", confidence=0.9, evidence="Total:    $130.20")
    assert not is_proven(field, SOURCE, amount=True)


def test_evidence_matches_amount_in_another_format() -> None:
    # The model normalised "$130.20" to "130.20"; the snippet still proves it.
    field = LlmField(value="130.20", confidence=0.9, evidence="Total:    $130.20")
    assert is_proven(field, SOURCE, amount=True)


def test_missing_evidence_is_not_proof() -> None:
    assert not is_proven(LlmField(value="X", confidence=1, evidence=None), SOURCE)


def test_unparseable_values_are_flagged_not_guessed() -> None:
    inv = build(total=fld("about a hundred", "Total:"), invoice_date=fld("soon", "Date:"))
    assert inv.total.value is None and "unparsed" in inv.total.flags
    assert inv.total.confidence == 0
    assert inv.invoice_date.value is None and "unparsed" in inv.invoice_date.flags


def test_currency_from_amounts_and_mixed_currencies() -> None:
    inv = build(total=fld("EUR 10.00", "EUR 10.00"))
    assert inv.currency.value == "EUR" and "currency_from_amounts" in inv.currency.flags
    mixed = build(currency=fld("USD"), subtotal=fld("EUR 10.00"), total=fld("$11.00"))
    assert set(mixed.currencies_seen) == {"USD", "EUR"}
