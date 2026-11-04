from datetime import date
from decimal import Decimal

import pytest

from app.extract.normalise import (
    currencies_in,
    norm_invoice_number,
    norm_supplier,
    parse_amount,
    parse_currency,
    parse_date,
)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("$1,234.50", "1234.50"),
        ("1.234,50 EUR", "1234.50"),
        ("BDT 1 234,50", "1234.50"),
        ("Tk. 450", "450"),
        ("(12.00)", "-12.00"),
        ("-5.00", "-5.00"),
        ("450,-", "450"),
        ("12,50", "12.50"),
        ("1,234", "1234"),
        ("0,125", "0.125"),
        ("€ 0.125", "0.125"),
        ("1,234,567", "1234567"),
        ("1.234.567", "1234567"),
        ("1,234.5", "1234.5"),
        ("USD 99", "99"),
        # Bangladesh: lakh grouping, Bengali digits, "/-" and "/=" endings, the word taka.
        ("12,34,567.00", "1234567.00"),
        ("Tk 1,25,000/-", "125000"),
        ("৳ ১,২৫,০০০.৫০", "125000.50"),
        ("১২৩৪.০০ টাকা", "1234.00"),
        ("5,000/=", "5000"),
        ("1,00,00,000.00", "10000000.00"),
    ],
)
def test_parse_amount(text: str, value: str) -> None:
    assert parse_amount(text) == Decimal(value)


@pytest.mark.parametrize(
    "text",
    [None, "", "abc", "1,2,3", "12.5.6", "123,45,678", "1,234,56", "12.34.567", "$", "1.2,3"],
)
def test_parse_amount_refuses_unclear_text(text: str | None) -> None:
    assert parse_amount(text) is None


def test_amounts_are_decimal_not_float() -> None:
    assert isinstance(parse_amount("0.10"), Decimal)
    assert parse_amount("0.10") + parse_amount("0.20") == Decimal("0.30")


@pytest.mark.parametrize(
    ("text", "expected", "ambiguous"),
    [
        ("2026-10-03", date(2026, 10, 3), False),
        ("2026/10/03", date(2026, 10, 3), False),
        ("13/10/2026", date(2026, 10, 13), False),
        ("10/13/2026", date(2026, 10, 13), False),
        ("03/10/2026", date(2026, 10, 3), True),
        ("05.06.26", date(2026, 6, 5), True),
        ("07/07/2026", date(2026, 7, 7), False),
        ("3 Oct 2026", date(2026, 10, 3), False),
        ("3rd October 2026", date(2026, 10, 3), False),
        ("October 3, 2026", date(2026, 10, 3), False),
        ("2026-10-03T00:00:00", date(2026, 10, 3), False),
    ],
)
def test_parse_date(text: str, expected: date, ambiguous: bool) -> None:
    assert parse_date(text) == (expected, ambiguous)


def test_parse_date_month_first_setting() -> None:
    assert parse_date("03/10/2026", day_first=False) == (date(2026, 3, 10), True)


@pytest.mark.parametrize("text", [None, "", "31/02/2026", "soon", "2026-13-01", "Oct 2026"])
def test_parse_date_refuses_bad_dates(text: str | None) -> None:
    assert parse_date(text)[0] is None


def test_currency() -> None:
    assert parse_currency("$") == "USD"
    assert parse_currency("Tk") == "BDT"
    assert parse_currency("৳ 500") == "BDT"
    assert parse_currency("eur") == "EUR"
    assert parse_currency("Amount due (GBP)") == "GBP"
    assert parse_currency("USD or EUR") is None  # two currencies: not a single answer
    assert parse_currency("dollars") == "USD"
    assert parse_currency("points") is None
    assert currencies_in("Total $12 and EUR 5, plus $3") == ["USD", "EUR"]


def test_normalised_keys() -> None:
    assert norm_invoice_number("inv-2026/00012") == "INV202600012"
    assert norm_invoice_number(" ") is None
    assert (
        norm_supplier("ACME TRADERS LIMITED")
        == norm_supplier("Acme Traders Ltd.")
        == ("acme traders")
    )


def test_bengali_dates_and_numbers() -> None:
    assert parse_date("১৩/১০/২০২৬") == (date(2026, 10, 13), False)
    assert parse_date("৫ নভেম্বর ২০২৬") == (date(2026, 11, 5), False)
    assert parse_date("জানুয়ারি 3, 2026") == (date(2026, 1, 3), False)
    assert norm_invoice_number("চালান-১২৩") == "123"
    assert currencies_in("মোট ১২০০ টাকা") == ["BDT"]
