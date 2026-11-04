"""Draw invoices onto PDF pages with PyMuPDF. Three layouts with different labels."""

from decimal import Decimal

import pymupdf

from synth.model import Invoice

SYMBOLS = {"USD": "$", "EUR": "EUR ", "BDT": "BDT ", "GBP": "GBP "}


def fmt_amount(value: Decimal, style: str) -> str:
    text = f"{value:,.2f}"
    if style == "eu":  # 1.234,50
        text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    return text


def fmt_qty(value: Decimal) -> str:
    return f"{value.normalize():f}"


def _text(page: pymupdf.Page, x: float, y: float, text: str, size: float = 10, bold: bool = False):
    page.insert_text((x, y), text, fontsize=size, fontname="hebo" if bold else "helv")


def classic(page: pymupdf.Page, inv: Invoice) -> None:
    sym = SYMBOLS[inv.currency]
    _text(page, 50, 60, inv.supplier_name, 18, bold=True)
    _text(page, 50, 80, "12 Commerce Road, Dhaka")
    _text(page, 400, 60, "INVOICE", 20, bold=True)
    _text(page, 400, 90, f"Invoice No: {inv.invoice_number}")
    _text(page, 400, 105, f"Date: {inv.invoice_date.isoformat()}")
    _text(page, 50, 130, "Bill To:", bold=True)
    _text(page, 50, 145, inv.customer_name or "")
    y = 190
    for x, label in ((50, "Description"), (300, "Qty"), (370, "Unit Price"), (470, "Amount")):
        _text(page, x, y, label, bold=True)
    page.draw_line((50, y + 5), (545, y + 5))
    for item in inv.line_items:
        y += 18
        _text(page, 50, y, item.description)
        _text(page, 300, y, fmt_qty(item.quantity))
        _text(page, 370, y, f"{sym}{item.unit_price}")
        _text(page, 470, y, f"{sym}{fmt_amount(item.amount, 'us')}")
    y += 30
    _text(page, 370, y, "Subtotal:")
    _text(page, 470, y, f"{sym}{fmt_amount(inv.subtotal, 'us')}")
    if inv.tax is not None:
        y += 16
        _text(page, 370, y, f"Tax ({inv.tax_rate}%):")
        _text(page, 470, y, f"{sym}{fmt_amount(inv.tax, 'us')}")
    y += 16
    _text(page, 370, y, "Total:", bold=True)
    _text(page, 470, y, f"{sym}{fmt_amount(inv.total, 'us')}", bold=True)
    _text(page, 50, y + 60, f"Currency: {inv.currency}. Payment due within 30 days.")


def modern(page: pymupdf.Page, inv: Invoice) -> None:
    page.draw_rect(pymupdf.Rect(0, 0, 595, 70), color=None, fill=(0.85, 0.9, 1.0))
    _text(page, 40, 45, "TAX INVOICE", 22, bold=True)
    _text(page, 330, 30, f"Bill #: {inv.invoice_number}")
    _text(page, 330, 45, f"Issued: {inv.invoice_date.strftime('%d/%m/%Y')}")
    _text(page, 40, 110, "From", bold=True)
    _text(page, 40, 125, inv.supplier_name)
    if inv.customer_name:
        _text(page, 320, 110, "Customer", bold=True)
        _text(page, 320, 125, inv.customer_name)
    y = 170
    for x, label in ((40, "Item"), (330, "Quantity"), (400, "Rate"), (480, "Line Total")):
        _text(page, x, y, label, bold=True)
    for item in inv.line_items:
        y += 18
        _text(page, 40, y, item.description)
        _text(page, 330, y, fmt_qty(item.quantity))
        _text(page, 400, y, f"{item.unit_price}")
        _text(page, 480, y, fmt_amount(item.amount, "us"))
    y += 34
    _text(page, 330, y, f"Net amount ({inv.currency})")
    _text(page, 480, y, fmt_amount(inv.subtotal, "us"))
    if inv.tax is not None:
        y += 16
        _text(page, 330, y, f"VAT {inv.tax_rate}%")
        _text(page, 480, y, fmt_amount(inv.tax, "us"))
    y += 16
    _text(page, 330, y, f"Amount due ({inv.currency})", bold=True)
    _text(page, 480, y, fmt_amount(inv.total, "us"), bold=True)


def european(page: pymupdf.Page, inv: Invoice) -> None:
    _text(page, 50, 50, inv.supplier_name.upper(), 14, bold=True)
    _text(page, 50, 90, "Rechnung / Invoice", 16, bold=True)
    _text(page, 50, 115, f"Reference: {inv.invoice_number}")
    _text(page, 50, 130, f"Invoice date: {inv.invoice_date.strftime('%d %b %Y')}")
    _text(page, 330, 115, f"Customer: {inv.customer_name or '-'}")
    y = 175
    for item in inv.line_items:
        _text(page, 50, y, f"{fmt_qty(item.quantity)} x {item.description}")
        _text(page, 450, y, f"{fmt_amount(item.amount, 'eu')} {inv.currency}")
        y += 18
    y += 20
    _text(page, 300, y, "Subtotal")
    _text(page, 450, y, f"{fmt_amount(inv.subtotal, 'eu')} {inv.currency}")
    if inv.tax is not None:
        y += 16
        _text(page, 300, y, f"Tax {inv.tax_rate}%")
        _text(page, 450, y, f"{fmt_amount(inv.tax, 'eu')} {inv.currency}")
    y += 16
    _text(page, 300, y, "Total", bold=True)
    _text(page, 450, y, f"{fmt_amount(inv.total, 'eu')} {inv.currency}", bold=True)


def classic_two_page(doc: pymupdf.Document, inv: Invoice) -> None:
    """The classic layout over two pages. The second page repeats no invoice number,
    so the reader must join it to the first (window edges, D39). Each page is drawn
    before the next is created: PyMuPDF retires earlier page objects."""
    sym = SYMBOLS[inv.currency]
    half = (len(inv.line_items) + 1) // 2

    def items(page: pymupdf.Page, lines: list, y: float) -> float:  # type: ignore[type-arg]
        for x, label in ((50, "Description"), (300, "Qty"), (370, "Unit Price"), (470, "Amount")):
            _text(page, x, y, label, bold=True)
        for item in lines:
            y += 18
            _text(page, 50, y, item.description)
            _text(page, 300, y, fmt_qty(item.quantity))
            _text(page, 370, y, f"{sym}{item.unit_price}")
            _text(page, 470, y, f"{sym}{fmt_amount(item.amount, 'us')}")
        return y

    first = doc.new_page(width=595, height=842)
    _text(first, 50, 60, inv.supplier_name, 18, bold=True)
    _text(first, 400, 60, "INVOICE", 20, bold=True)
    _text(first, 400, 90, f"Invoice No: {inv.invoice_number}")
    _text(first, 400, 105, f"Date: {inv.invoice_date.isoformat()}")
    _text(first, 50, 130, "Bill To:", bold=True)
    _text(first, 50, 145, inv.customer_name or "")
    items(first, inv.line_items[:half], 190)
    _text(first, 50, 780, "Continued on the next page")

    second = doc.new_page(width=595, height=842)
    _text(second, 50, 50, f"{inv.supplier_name}, continued", 10, bold=True)
    y = items(second, inv.line_items[half:], 90) + 30
    _text(second, 370, y, "Subtotal:")
    _text(second, 470, y, f"{sym}{fmt_amount(inv.subtotal, 'us')}")
    if inv.tax is not None:
        y += 16
        _text(second, 370, y, f"Tax ({inv.tax_rate}%):")
        _text(second, 470, y, f"{sym}{fmt_amount(inv.tax, 'us')}")
    y += 16
    _text(second, 370, y, "Total:", bold=True)
    _text(second, 470, y, f"{sym}{fmt_amount(inv.total, 'us')}", bold=True)
    _text(second, 50, y + 60, f"Currency: {inv.currency}. Payment due within 30 days.")


LAYOUTS = {"classic": classic, "modern": modern, "european": european}
TWO_PAGE = {"classic_two_page": classic_two_page}


def invoice_pdf(invoices: list[tuple[Invoice, str]]) -> pymupdf.Document:
    """A4 pages, each invoice in its named layout (two pages for a TWO_PAGE layout)."""
    doc = pymupdf.open()
    for inv, layout in invoices:
        if layout in TWO_PAGE:
            TWO_PAGE[layout](doc, inv)
        else:
            LAYOUTS[layout](doc.new_page(width=595, height=842), inv)
    return doc
