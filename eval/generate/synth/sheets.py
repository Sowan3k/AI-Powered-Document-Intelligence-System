"""Invoice registers as .xlsx, .xls and CSV, with title rows, merged cells and gaps."""

import csv
from pathlib import Path

import openpyxl

from synth.model import Invoice

HEADERS = [
    "Invoice No",
    "Invoice Date",
    "Supplier",
    "Customer",
    "Currency",
    "Subtotal",
    "Tax",
    "Total",
]


def rows_of(invoices: list[Invoice]) -> list[list[object]]:
    return [
        [i.invoice_number, i.invoice_date, i.supplier_name, i.customer_name, i.currency,
         float(i.subtotal), float(i.tax) if i.tax is not None else None, float(i.total)]
        for i in invoices
    ]  # fmt: skip


def write_xlsx(path: Path, sheets: dict[str, list[Invoice]]) -> None:
    """Each sheet: merged title row, blank row, header row, data, a blank row inside."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, invoices in sheets.items():
        ws = wb.create_sheet(name)
        ws.append([f"Invoice register: {name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(HEADERS))
        ws.append([])
        ws.append(HEADERS)
        for n, row in enumerate(rows_of(invoices)):
            if n == 2:
                ws.append([])  # an empty row in the middle of the data
            ws.append(row)
            ws.cell(ws.max_row, 2).number_format = "yyyy-mm-dd"
    wb.save(path)


def write_xls(path: Path, invoices: list[Invoice]) -> None:
    import xlwt  # dev dependency, only needed to write .xls fixtures

    wb = xlwt.Workbook()
    ws = wb.add_sheet("Register")
    date_style = xlwt.easyxf(num_format_str="YYYY-MM-DD")
    ws.write_merge(0, 0, 0, len(HEADERS) - 1, "Invoice register")
    for c, name in enumerate(HEADERS):
        ws.write(2, c, name)
    for r, row in enumerate(rows_of(invoices), start=3):
        for c, value in enumerate(row):
            if c == 1:
                ws.write(r, c, value, date_style)
            elif value is not None:
                ws.write(r, c, value)
    wb.save(str(path))


def write_csv(
    path: Path, invoices: list[Invoice], delimiter: str = ",", encoding: str = "utf-8"
) -> None:
    with path.open("w", newline="", encoding=encoding) as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        writer.writerow(HEADERS)
        for i in invoices:
            tax = "" if i.tax is None else i.tax
            customer = i.customer_name or ""
            writer.writerow(
                [i.invoice_number, i.invoice_date.isoformat(), i.supplier_name, customer,
                 i.currency, i.subtotal, tax, i.total]
            )  # fmt: skip
