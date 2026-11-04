"""Turn the model's printed strings into an InvoiceData with typed values and flags."""

from app.extract import evidence
from app.extract.normalise import (
    clean_text,
    currencies_in,
    parse_amount,
    parse_currency,
    parse_date,
    parse_quantity,
)
from app.extract.schemas import FieldValue, InvoiceData, LineItemData, LlmField, LlmInvoice

AMOUNT_FIELDS = ("subtotal", "tax", "total")
TEXT_FIELDS = ("invoice_number", "supplier_name", "customer_name")
AMBIGUOUS_DATE_FACTOR = 0.8
SYMBOL_ONLY = {"$"}  # "$" alone could be US, Canadian, Australian or Singapore dollars


def _base(field: LlmField, source: str, *, amount: bool = False) -> FieldValue:
    out = FieldValue(confidence=field.confidence, evidence=field.evidence, raw=field.value)
    if not evidence.is_proven(field, source, amount=amount):
        out.flags.append(evidence.FLAG)
        out.confidence = round(out.confidence * evidence.PENALTY, 3)
    return out


def _unparsed(out: FieldValue) -> FieldValue:
    out.flags.append("unparsed")
    out.confidence = 0.0
    return out


def build_invoice(inv: LlmInvoice, source: str, *, day_first: bool = True) -> InvoiceData:
    data = InvoiceData(page_start=inv.page_start, page_end=inv.page_end)

    for name in TEXT_FIELDS:
        field = getattr(inv, name)
        out = _base(field, source)
        out.value = clean_text(field.value)
        setattr(data, name, out)

    date_field = _base(inv.invoice_date, source)
    if inv.invoice_date.value is not None:
        parsed, ambiguous = parse_date(inv.invoice_date.value, day_first=day_first)
        if parsed is None:
            _unparsed(date_field)
        else:
            date_field.value = parsed
            if ambiguous:
                date_field.flags.append("ambiguous_date")
                date_field.confidence = round(date_field.confidence * AMBIGUOUS_DATE_FACTOR, 3)
    data.invoice_date = date_field

    seen: list[str] = []
    for name in AMOUNT_FIELDS:
        field = getattr(inv, name)
        out = _base(field, source, amount=True)
        if field.value is not None:
            out.value = parse_amount(field.value)
            if out.value is None:
                _unparsed(out)
        for code in currencies_in(field.value):
            if code not in seen:
                seen.append(code)
        setattr(data, name, out)

    currency = _base(inv.currency, source)
    if inv.currency.value is not None:
        currency.value = parse_currency(inv.currency.value)
        if currency.value is None:
            _unparsed(currency)
        elif inv.currency.value.strip() in SYMBOL_ONLY:
            currency.flags.append("symbol_only")
        if currency.value and currency.value not in seen:
            seen.insert(0, currency.value)
    elif len(seen) == 1:
        # No currency field, but every amount names the same one.
        currency.value = seen[0]
        currency.confidence = 0.6
        currency.flags.append("currency_from_amounts")
    data.currency = currency
    data.currencies_seen = seen

    data.line_items = [
        LineItemData(
            position=n,
            description=clean_text(item.description),
            quantity=parse_quantity(item.quantity),
            unit_price=parse_amount(item.unit_price),
            amount=parse_amount(item.amount),
            confidence=item.confidence,
        )
        for n, item in enumerate(inv.line_items, start=1)
    ]
    return data
