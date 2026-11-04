"""Phase 2 exit test on the synthetic fixtures.

The fake model is a perfect reader: it copies each value exactly as the
generator printed it, with the matching line of page text as evidence. So
this test checks everything code does with a reply (schema validation,
windows, normalisation of three date and amount styles, currency detection,
the evidence check, and nulls for missing fields) against the ground truth.
Real model accuracy is measured in Phase 6.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from synth.layouts import SYMBOLS, fmt_amount, fmt_qty

from app.core.config import Settings
from app.extract.build import build_invoice
from app.extract.columns import map_columns, rows_to_invoices
from app.extract.normalise import norm_supplier
from app.extract.schemas import FIELDS, InvoiceData
from app.extract.service import extract_pages
from app.ingest.reader import read_document
from tests.conftest import FakeCall, FakeLlmClient

PDFS = [
    "digital_classic_0.pdf",
    "digital_modern_0.pdf",
    "digital_european_0.pdf",
    "planted_wrong_total.pdf",
    "planted_wrong_line_sum.pdf",
    "planted_missing_tax.pdf",
    "planted_missing_customer.pdf",
    "multi_invoice.pdf",
    "long_statement.pdf",
]


def printed(truth: dict, layout: str) -> dict[str, object]:
    """The strings each layout prints (see eval/generate/synth/layouts.py)."""
    layout = "classic" if layout == "classic_two_page" else layout
    d = date.fromisoformat(truth["invoice_date"])
    cur = truth["currency"]

    def money(key: str) -> str | None:
        if truth[key] is None:
            return None
        v = Decimal(truth[key])
        if layout == "classic":
            return f"{SYMBOLS[cur]}{fmt_amount(v, 'us')}"
        if layout == "modern":
            return fmt_amount(v, "us")
        return f"{fmt_amount(v, 'eu')} {cur}"

    items = []
    for li in truth["line_items"]:
        price = {"classic": f"{SYMBOLS[cur]}{li['unit_price']}", "modern": li["unit_price"]}
        items.append(
            {
                "description": li["description"],
                "quantity": fmt_qty(Decimal(li["quantity"])),
                "unit_price": price.get(layout),
                "amount": money_of(Decimal(li["amount"]), layout, cur),
            }
        )
    return {
        "invoice_number": truth["invoice_number"],
        "invoice_date": {
            "classic": d.isoformat(),
            "modern": d.strftime("%d/%m/%Y"),
            "european": d.strftime("%d %b %Y"),
        }[layout],
        "supplier_name": truth["supplier_name"].upper()
        if layout == "european"
        else truth["supplier_name"],
        "customer_name": truth["customer_name"],
        "subtotal": money("subtotal"),
        "tax": money("tax"),
        "total": money("total"),
        "currency": cur,
        "line_items": items,
    }


def money_of(v: Decimal, layout: str, cur: str) -> str:
    if layout == "classic":
        return f"{SYMBOLS[cur]}{fmt_amount(v, 'us')}"
    if layout == "modern":
        return fmt_amount(v, "us")
    return f"{fmt_amount(v, 'eu')} {cur}"


def find_line(text: str, value: str) -> str | None:
    for row in text.splitlines():
        if value in row:
            return row.strip() if len(row.strip()) <= 80 else value
    return None


def perfect_reader(truth: dict, page_texts: dict[int, str]):  # type: ignore[no-untyped-def]
    """Copies every value printed on the pages the prompt shows, as a careful reader would.

    An invoice only partly inside the window gives the fields visible there and
    null for the rest. For an invoice wholly inside, a value the generator
    printed but the page lacks means this test's formats are wrong, so it fails.
    """
    ranges = truth.get("pages") or [[1, 1]] * len(truth["invoices"])
    layouts = truth.get("layouts") or [truth["layout"]] * len(truth["invoices"])

    def reply(call: FakeCall) -> dict:
        prompt = call.turns[0].parts[0]
        shown = [int(x.split(" ---")[0]) for x in prompt.split("--- page ")[1:]]
        out = []
        for inv, (start, end), layout in zip(truth["invoices"], ranges, layouts, strict=True):
            visible = [n for n in range(start, end + 1) if n in shown]
            if not visible:
                continue
            whole = len(visible) == end - start + 1
            text = "\n".join(page_texts[n] for n in visible)
            p = printed(inv, layout)
            entry: dict[str, object] = {"page_start": visible[0], "page_end": visible[-1]}
            for name in FIELDS:
                value = p[name]
                line = find_line(text, value) if value is not None else None
                if value is not None and line is None and whole:
                    raise AssertionError(f"{value!r} is not printed; the test's formats are wrong")
                found = line is not None
                entry[name] = {
                    "value": value if found else None,
                    "confidence": 0.95,
                    "evidence": line if found else None,
                }
            items = []
            for li in p["line_items"]:
                page = next((n for n in visible if li["description"] in page_texts[n]), None)
                if page is None and whole:
                    raise AssertionError(f"line {li['description']!r} is not printed")
                if page is not None:
                    items.append({**li, "page": page, "confidence": 0.9})
            entry["line_items"] = items
            out.append(entry)
        return {"invoices": out}

    return reply


def assert_matches(got: InvoiceData, want: dict) -> None:
    assert got.invoice_number.value == want["invoice_number"]
    assert got.invoice_date.value == date.fromisoformat(want["invoice_date"])
    assert norm_supplier(got.supplier_name.value) == norm_supplier(want["supplier_name"])
    assert got.customer_name.value == want["customer_name"]
    for key in ("subtotal", "tax", "total"):
        expected = None if want[key] is None else Decimal(want[key])
        assert got.field(key).value == expected, key
    assert got.currency.value == want["currency"]
    amounts = [li.amount for li in got.line_items]
    assert amounts == [Decimal(li["amount"]) for li in want["line_items"]]


@pytest.mark.parametrize("name", PDFS)
def test_pdf_extraction_matches_ground_truth(synthetic_dir: Path, name: str) -> None:
    truth = json.loads((synthetic_dir / f"{name}.json").read_text())
    doc = read_document(synthetic_dir / name, Settings())
    texts = {p.page_number: p.text for p in doc.pages}
    fake = FakeLlmClient(perfect_reader(truth, texts))
    settings = Settings(segment_window_pages=3, segment_overlap_pages=1)
    found, _ = extract_pages(fake, "m", list(texts.items()), settings)
    built = [
        build_invoice(inv, "\n".join(texts[n] for n in range(inv.page_start, inv.page_end + 1)))
        for inv in found
    ]

    assert len(built) == len(truth["invoices"])
    assert [[b.page_start, b.page_end] for b in built] == (
        truth.get("pages") or [[1, 1]] * len(built)
    )
    for got, want in zip(built, truth["invoices"], strict=True):
        assert_matches(got, want)
        for field in FIELDS:
            assert "evidence_not_found" not in got.field(field).flags, field
            assert "unparsed" not in got.field(field).flags, field


def test_missing_fields_come_back_null(synthetic_dir: Path) -> None:
    for name, field in (
        ("planted_missing_tax.pdf", "tax"),
        ("planted_missing_customer.pdf", "customer_name"),
    ):
        truth = json.loads((synthetic_dir / f"{name}.json").read_text())
        doc = read_document(synthetic_dir / name, Settings())
        texts = {p.page_number: p.text for p in doc.pages}
        found, _ = extract_pages(
            FakeLlmClient(perfect_reader(truth, texts)), "m", list(texts.items()), Settings()
        )
        [inv] = [build_invoice(i, texts[1]) for i in found]
        assert inv.field(field).value is None
        assert inv.field(field).evidence is None


@pytest.mark.parametrize(
    "name", ["register.xlsx", "register.xls", "register.csv", "register_semicolon_cp1252.csv"]
)
def test_sheet_extraction_matches_ground_truth(synthetic_dir: Path, name: str) -> None:
    truth = json.loads((synthetic_dir / f"{name}.json").read_text())
    doc = read_document(synthetic_dir / name, Settings())
    fake = FakeLlmClient([])  # standard headers map by rule: no model call
    got = []
    for sheet in doc.sheets:
        got += rows_to_invoices(sheet, map_columns(sheet, fake, "m"))
    assert fake.calls == []
    assert len(got) == len(truth["invoices"])
    for inv, want in zip(got, truth["invoices"], strict=True):
        assert inv.invoice_number.value == want["invoice_number"]
        assert inv.invoice_date.value == date.fromisoformat(want["invoice_date"])
        assert inv.customer_name.value == want["customer_name"]
        assert inv.total.value == Decimal(want["total"])
        assert inv.currency.value == want["currency"]


def prompt_pages(prompt: str) -> dict[int, str]:
    """Page texts as the model sees them in an extraction prompt."""
    body = prompt.split("<<<DOCUMENT_DATA>>>", 1)[1].rsplit("<<<END_DOCUMENT_DATA>>>", 1)[0]
    pages = {}
    for chunk in body.split("--- page ")[1:]:
        number, _, text = chunk.partition(" ---\n")
        pages[int(number)] = text
    return pages


def reader_for_truths(truths: list[dict]):  # type: ignore[no-untyped-def]
    """A perfect reader for several files: picks the file whose invoices the prompt shows."""

    def reply(call: FakeCall) -> dict:
        if call.purpose != "extract_invoices":
            raise AssertionError(f"unexpected call {call.purpose}")
        prompt = call.turns[0].parts[0]
        # Only PDF truths say how each page was laid out; pick the best match.
        paged = [t for t in truths if "layout" in t or "layouts" in t]
        scored = [(sum(inv["invoice_number"] in prompt for inv in t["invoices"]), t) for t in paged]
        candidates = sorted((x for x in scored if x[0] > 0), key=lambda x: -x[0])
        for _, truth in candidates:
            try:  # two files can share invoice numbers (a duplicate in another layout)
                return perfect_reader(truth, prompt_pages(prompt))(call)
            except AssertionError:
                continue
        if candidates:
            raise AssertionError("no ground truth matches the printed values")
        return {"invoices": []}

    return reply


@pytest.mark.parametrize(("window", "overlap"), [(8, 1), (5, 2), (2, 1)])
def test_long_statement_segments_at_any_window_size(
    synthetic_dir: Path, window: int, overlap: int
) -> None:
    """Two-page invoices cross window edges at every size; each must come out whole."""
    truth = json.loads((synthetic_dir / "long_statement.pdf.json").read_text())
    doc = read_document(synthetic_dir / "long_statement.pdf", Settings())
    texts = {p.page_number: p.text for p in doc.pages}
    fake = FakeLlmClient(perfect_reader(truth, texts))
    settings = Settings(segment_window_pages=window, segment_overlap_pages=overlap)
    found, _ = extract_pages(fake, "m", list(texts.items()), settings)
    assert [[i.page_start, i.page_end] for i in found] == truth["pages"]
    assert [i.invoice_number.value for i in found] == [
        t["invoice_number"] for t in truth["invoices"]
    ]
    for inv, want in zip(found, truth["invoices"], strict=True):
        assert len(inv.line_items) == len(want["line_items"])  # no line lost or counted twice
