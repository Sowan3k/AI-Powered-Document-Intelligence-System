"""Spreadsheet column mapping and row conversion."""

from datetime import date
from decimal import Decimal

from app.extract.columns import map_by_rule, map_columns, rows_to_invoices
from app.ingest.schemas import SheetContent
from tests.conftest import FakeLlmClient


def sheet(headers: list[str], rows: list[list[str | None]]) -> SheetContent:
    return SheetContent(
        sheet_index=0,
        sheet_name="s",
        header_row=1,
        headers=headers,
        rows=rows,
        row_numbers=list(range(2, 2 + len(rows))),
    )


def test_rule_mapping() -> None:
    mapping = map_by_rule(["Invoice #", "Date", "Vendor", "Bill To", "Sub Total", "VAT", "Total"])
    assert mapping == {
        "invoice_number": "Invoice #",
        "invoice_date": "Date",
        "supplier_name": "Vendor",
        "customer_name": "Bill To",
        "subtotal": "Sub Total",
        "tax": "VAT",
        "total": "Total",
    }


def test_no_llm_call_when_rules_map_everything() -> None:
    fake = FakeLlmClient([])
    s = sheet(
        ["Invoice No", "Invoice Date", "Supplier", "Total"], [["A-1", "2026-01-02", "X", "5"]]
    )
    mapping = map_columns(s, fake, "m")
    assert fake.calls == [] and mapping.by_llm == set()


def test_llm_maps_odd_headers_once_per_sheet() -> None:
    s = sheet(
        ["Doc Ref", "Posted", "Counterparty", "Gross"],
        [["A-1", "2026-01-02", "Acme", "10.00"], ["A-2", "2026-01-03", "Delta", "20.00"]],
    )
    reply = {
        "invoice_number": "Doc Ref", "invoice_date": "Posted", "supplier_name": "Counterparty",
        "customer_name": None, "subtotal": None, "tax": None, "total": "Gross",
        "currency": "Invented Column", "description": None, "quantity": None,
        "unit_price": None, "amount": "Doc Ref",
    }  # fmt: skip
    fake = FakeLlmClient([reply])
    mapping = map_columns(s, fake, "m")
    assert len(fake.calls) == 1 and fake.calls[0].purpose == "column_mapping"
    assert mapping.columns["total"] == "Gross"
    assert "currency" not in mapping.columns  # invented header ignored
    assert "amount" not in mapping.columns  # a header cannot serve two fields
    invoices = rows_to_invoices(s, mapping)
    assert [i.total.value for i in invoices] == [Decimal("10.00"), Decimal("20.00")]
    assert invoices[0].total.confidence == 0.85  # LLM-mapped columns are trusted a bit less
    assert invoices[0].total.evidence == "row 2, Gross: 10.00"


def test_rows_sharing_a_number_become_one_invoice_with_lines() -> None:
    s = sheet(
        ["Invoice No", "Supplier", "Description", "Qty", "Unit Price", "Amount", "Total"],
        [
            ["A-1", "Acme", "Paper", "2", "4.50", "9.00", "21.00"],
            ["A-1", "Acme", "Toner", "1", "12.00", "12.00", "21.00"],
            ["B-7", "Delta", "Bolts", "10", "0.125", "1.25", "1.25"],
        ],
    )
    invoices = rows_to_invoices(s, map_columns(s, None, None))
    assert [i.invoice_number.value for i in invoices] == ["A-1", "B-7"]
    assert [li.description for li in invoices[0].line_items] == ["Paper", "Toner"]
    assert invoices[0].line_items[1].unit_price == Decimal("12.00")
    assert (invoices[0].row_start, invoices[0].row_end) == (2, 3)
    assert invoices[1].line_items[0].unit_price == Decimal("0.125")


def test_bad_cells_are_flagged_and_empty_rows_skipped() -> None:
    s = sheet(
        ["Invoice No", "Invoice Date", "Total"],
        [["A-1", "31/02/2026", "n/a"], [None, None, None], ["A-2", "02/01/2026", "1,200.50"]],
    )
    a, b = rows_to_invoices(s, map_columns(s, None, None))
    assert a.invoice_date.value is None and "unparsed" in a.invoice_date.flags
    assert a.total.value is None and "unparsed" in a.total.flags
    assert b.invoice_date.value == date(2026, 1, 2)
    assert b.total.value == Decimal("1200.50")
