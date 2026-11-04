"""Spreadsheet rows to invoices: map columns by rule, ask the model only when stuck (D12).

Known header names map by rule. If an invoice field is still unmapped and some
columns are still unused, the model sees the headers and a few sample rows,
once per sheet, and names the column for each field. Its answer is checked:
only real, unused headers are accepted.

A sheet that does not list invoices (a staff list, a price list) gives no
invoices. The model says so when it is asked; otherwise the rules decide: a
sheet needs a money column and at least two mapped fields.

Then every row is converted in plain Python. Rows that share an invoice number
and carry line item columns form one invoice with several lines. Otherwise
each row is one invoice. The cells are already text (Phase 1), so no data
frame library is needed (D37).
"""

import re
from dataclasses import dataclass, field

from app.extract import prompts
from app.extract.llm import LlmClient, LlmUsage, generate_structured
from app.extract.normalise import (
    clean_text,
    currencies_in,
    norm_invoice_number,
    parse_amount,
    parse_currency,
    parse_date,
    signed_adjustment,
)
from app.extract.schemas import (
    AdjustmentData,
    FieldValue,
    InvoiceData,
    LineItemData,
    LlmColumnMapping,
)
from app.ingest.schemas import SheetContent

INVOICE_FIELDS = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "subtotal",
    "tax",
    "total",
    "currency",
)
LINE_FIELDS = ("description", "quantity", "unit_price", "amount")
ALL_FIELDS = INVOICE_FIELDS + LINE_FIELDS
# Fields worth an LLM call when the rules miss them.
WANTED = ("invoice_number", "invoice_date", "supplier_name", "total")

ALIASES = {
    "invoice_number": ["invoice no", "invoice number", "invoice num", "inv no", "invoice",
                       "invoice id", "bill no", "bill number", "invoice ref", "reference",
                       "ref no", "document no"],
    "invoice_date": ["invoice date", "date", "inv date", "bill date", "issue date",
                     "date issued", "document date"],
    "supplier_name": ["supplier", "supplier name", "vendor", "vendor name", "seller",
                      "from", "issued by", "company"],
    "customer_name": ["customer", "customer name", "client", "client name", "buyer",
                      "bill to", "billed to", "sold to"],
    "subtotal": ["subtotal", "sub total", "net", "net amount", "amount before tax",
                 "taxable amount"],
    "tax": ["tax", "vat", "gst", "tax amount", "vat amount", "sales tax"],
    "total": ["total", "total amount", "grand total", "amount due", "invoice total",
              "gross amount", "total due"],
    "currency": ["currency", "ccy", "currency code", "cur"],
    "description": ["description", "item", "item description", "product", "details"],
    "quantity": ["qty", "quantity", "units"],
    "unit_price": ["unit price", "price", "rate", "unit cost"],
    "amount": ["amount", "line total", "line amount", "value"],
}  # fmt: skip
# Discount and charge columns, by rule only. The header becomes the label.
ADJUSTMENT_HEADERS = {
    "discount", "discount amount", "less discount", "rebate", "delivery", "delivery charge",
    "shipping", "shipping charge", "freight", "service charge", "other charges", "rounding",
    "round off", "sd", "supplementary duty",
}  # fmt: skip
RULE_CONFIDENCE = 0.95
LLM_CONFIDENCE = 0.85


def norm_header(text: str) -> str:
    text = text.lower().replace("#", " no ").replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


@dataclass
class Mapping:
    columns: dict[str, str] = field(default_factory=dict)  # field -> header
    by_llm: set[str] = field(default_factory=set)
    usages: list[LlmUsage] = field(default_factory=list)
    lists_invoices: bool = True


def looks_like_invoices(columns: dict[str, str]) -> bool:
    """The rule when the model is not asked: a money column and two mapped fields."""
    fields = set(columns)
    return bool(fields & {"total", "subtotal", "amount"}) and len(fields) >= 2


def map_by_rule(headers: list[str]) -> dict[str, str]:
    normalised = {h: norm_header(h) for h in headers}
    mapping: dict[str, str] = {}
    used: set[str] = set()
    # Exact alias matches first, in alias order, so "total" beats "subtotal".
    for name in ALL_FIELDS:
        for alias in ALIASES[name]:
            hit = next((h for h, n in normalised.items() if n == alias and h not in used), None)
            if hit:
                mapping[name] = hit
                used.add(hit)
                break
    return mapping


def map_columns(
    sheet: SheetContent, llm: LlmClient | None, model: str | None, sample_rows: int = 5
) -> Mapping:
    result = Mapping(columns=map_by_rule(sheet.headers))
    missing = [f for f in WANTED if f not in result.columns]
    unused = [h for h in sheet.headers if h not in result.columns.values()]
    if not missing or not unused or llm is None or not model:
        result.lists_invoices = not missing or looks_like_invoices(result.columns)
        return result
    answer, usages = generate_structured(
        llm,
        LlmColumnMapping,
        purpose="column_mapping",
        model=model,
        system=prompts.COLUMN_MAPPING_SYSTEM,
        parts=[
            prompts.column_mapping_prompt(sheet.headers, sheet.rows[:sample_rows], result.columns)
        ],
    )
    result.usages = usages
    result.lists_invoices = answer.lists_invoices
    if not answer.lists_invoices:
        return result
    for name in ALL_FIELDS:
        header = getattr(answer, name)
        if name in result.columns or header not in unused:
            continue  # rule mappings stay; invented or reused headers are ignored
        result.columns[name] = header
        result.by_llm.add(name)
        unused.remove(header)
    return result


def _cell(row: dict[str, str | None], mapping: Mapping, name: str) -> str | None:
    header = mapping.columns.get(name)
    return row.get(header) if header else None


def _field(row, mapping: Mapping, name: str, parse, row_number: int) -> FieldValue:  # type: ignore[no-untyped-def]
    raw = _cell(row, mapping, name)
    out = FieldValue(raw=raw)
    if raw is None:
        return out
    header = mapping.columns[name]
    out.evidence = f"row {row_number}, {header}: {raw}"
    out.confidence = LLM_CONFIDENCE if name in mapping.by_llm else RULE_CONFIDENCE
    out.value = parse(raw)
    if out.value is None:
        out.flags.append("unparsed")
        out.confidence = 0.0
    return out


def rows_to_invoices(
    sheet: SheetContent, mapping: Mapping, *, day_first: bool = True
) -> list[InvoiceData]:
    if not mapping.lists_invoices:
        return []
    rows = [dict(zip(sheet.headers, r, strict=True)) for r in sheet.rows]
    has_lines = any(f in mapping.columns for f in ("description", "quantity", "unit_price"))
    groups: list[list[int]] = []
    if has_lines and "invoice_number" in mapping.columns:
        index: dict[str, int] = {}
        for i, row in enumerate(rows):
            key = norm_invoice_number(_cell(row, mapping, "invoice_number"))
            if key and key in index:
                groups[index[key]].append(i)
            else:
                if key:
                    index[key] = len(groups)
                groups.append([i])
    else:
        groups = [[i] for i in range(len(rows))]

    used = set(mapping.columns.values())
    adjustment_headers = [
        h for h in sheet.headers if h not in used and norm_header(h) in ADJUSTMENT_HEADERS
    ]

    def date_value(text: str):  # type: ignore[no-untyped-def]
        return parse_date(text, day_first=day_first)[0]

    parsers = {
        "invoice_number": clean_text,
        "invoice_date": date_value,
        "supplier_name": clean_text,
        "customer_name": clean_text,
        "subtotal": parse_amount,
        "tax": parse_amount,
        "total": parse_amount,
        "currency": parse_currency,
    }
    invoices = []
    for group in groups:
        first = rows[group[0]]
        number = sheet.row_numbers[group[0]]
        if not any(_cell(first, mapping, f) for f in INVOICE_FIELDS):
            continue  # a row with nothing an invoice needs (a total line, a note)
        inv = InvoiceData(
            sheet_index=sheet.sheet_index,
            row_start=number,
            row_end=sheet.row_numbers[group[-1]],
        )
        for name, parse in parsers.items():
            setattr(inv, name, _field(first, mapping, name, parse, number))
        if has_lines:
            inv.line_items = [
                LineItemData(
                    position=n,
                    description=clean_text(_cell(rows[i], mapping, "description")),
                    quantity=parse_amount(_cell(rows[i], mapping, "quantity")),
                    unit_price=parse_amount(_cell(rows[i], mapping, "unit_price")),
                    amount=parse_amount(_cell(rows[i], mapping, "amount")),
                    confidence=RULE_CONFIDENCE,
                )
                for n, i in enumerate(group, start=1)
            ]
        for header in adjustment_headers:
            raw = first.get(header)
            if raw:
                adj = AdjustmentData(
                    label=header, raw=raw, evidence=f"row {number}, {header}: {raw}"
                )
                adj.amount = signed_adjustment(header, parse_amount(raw))
                if adj.amount is None:
                    adj.flags.append("unparsed")
                if adj.amount != 0:
                    inv.adjustments.append(adj)
        seen = [inv.currency.value] if inv.currency.value else []
        for name in ("subtotal", "tax", "total"):
            for code in currencies_in(inv.field(name).raw):
                if code not in seen:
                    seen.append(code)
        inv.currencies_seen = seen
        invoices.append(inv)
    return invoices
