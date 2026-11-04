"""Build a dataset folder: files, ground truth JSON beside each, and a manifest.

The manifest says what ingestion must produce for each file: a kind with page
or sheet facts and strings that must appear in the text, or a failure code.
"""

import json
import random
from pathlib import Path

import cv2

from synth import broken, layouts, scans, sheets
from synth.model import Invoice, make_invoice, plant


def _write_truth(path: Path, invoices: list[Invoice], **extra: object) -> None:
    truth = {"file": path.name, "invoices": [i.truth() for i in invoices], **extra}
    path.with_name(path.name + ".json").write_text(json.dumps(truth, indent=2))


def build(out: Path, seed: int = 7, scale: int = 1) -> list[dict]:
    """Write the dataset into `out` and return the manifest entries.

    scale=1 is the small set the unit tests use. Phase 6 raises it.
    """
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    counter = iter(range(1, 100_000))
    manifest: list[dict] = []

    def new(currency: str | None = None) -> Invoice:
        return make_invoice(rng, next(counter), currency)

    def add(
        name: str, expect: dict, invoices: list[Invoice] | None = None, **extra: object
    ) -> Path:
        path = out / name
        manifest.append({"file": name, "expect": expect})
        if invoices is not None:
            _write_truth(path, invoices, **extra)
        return path

    # Digital PDFs, one per layout, plus planted errors.
    layout_names = list(layouts.LAYOUTS)
    for n in range(scale):
        for layout in layout_names:
            inv = new()
            path = add(
                f"digital_{layout}_{n}.pdf",
                {
                    "kind": "pdf",
                    "pages": 1,
                    "methods": ["digital"],
                    "contains": [inv.invoice_number],
                },
                [inv],
                layout=layout,
            )
            layouts.invoice_pdf([(inv, layout)]).save(path)
    for error in ("wrong_total", "wrong_line_sum", "missing_tax", "missing_customer"):
        inv = plant(new(), error)
        path = add(
            f"planted_{error}.pdf",
            {"kind": "pdf", "pages": 1, "methods": ["digital"], "contains": [inv.invoice_number]},
            [inv],
            layout="classic",
        )
        layouts.invoice_pdf([(inv, "classic")]).save(path)

    # A multi-invoice PDF, several pages.
    multi = [(new(), layout_names[i % 3]) for i in range(4 * scale)]
    path = add(
        "multi_invoice.pdf",
        {"kind": "pdf", "pages": len(multi), "methods": ["digital"],
         "contains": [m[0].invoice_number for m in multi]},
        [m[0] for m in multi],
        pages=[[i + 1, i + 1] for i in range(len(multi))],
        layouts=[m[1] for m in multi],
    )  # fmt: skip
    good_doc = layouts.invoice_pdf(multi)
    good_doc.save(path)
    good_pdf = path.read_bytes()

    # Scans: a scanned PDF (light), a heavy-noise JPEG, a PNG and a 2-page TIFF.
    scan_invs = [new("USD"), new("EUR")]
    scan_doc = layouts.invoice_pdf([(scan_invs[0], "classic"), (scan_invs[1], "modern")])
    clean = [scans.render(page) for page in scan_doc]
    light = [scans.degrade(img, rng, "light") for img in clean]
    path = add(
        "scanned_light.pdf",
        {
            "kind": "pdf",
            "pages": 2,
            "methods": ["ocr"],
            "contains": ["INVOICE"],
            "min_confidence": 60,
        },
        scan_invs,
    )
    scans.scanned_pdf(light).save(path)
    path = add("scan_heavy.jpg", {"kind": "jpeg", "pages": 1, "methods": ["ocr"]}, scan_invs[:1])
    cv2.imwrite(str(path), scans.degrade(clean[0], rng, "heavy"))
    path = add(
        "scan_clean.png",
        {"kind": "png", "pages": 1, "methods": ["ocr"], "contains": [scan_invs[1].invoice_number],
         "min_confidence": 75},
        scan_invs[1:],
    )  # fmt: skip
    cv2.imwrite(str(path), clean[1])
    path = add(
        "scan_two_pages.tiff",
        {"kind": "tiff", "pages": 2, "methods": ["ocr"], "contains": ["INVOICE"]},
        scan_invs,
    )
    scans.save_tiff(light, str(path))

    # Spreadsheets: an .xlsx with two sheets, an .xls, two CSV variants.
    sheet_a, sheet_b = [new() for _ in range(5)], [new() for _ in range(3)]
    path = add(
        "register.xlsx",
        {"kind": "xlsx", "sheets": [{"name": "October", "rows": 5, "header_row": 3},
                                    {"name": "November", "rows": 3, "header_row": 3}],
         "contains": [sheet_a[0].invoice_number]},
        sheet_a + sheet_b,
    )  # fmt: skip
    sheets.write_xlsx(path, {"October": sheet_a, "November": sheet_b})
    path = add(
        "register.xls",
        {"kind": "xls", "sheets": [{"name": "Register", "rows": 5, "header_row": 3}],
         "contains": [sheet_a[1].invoice_number]},
        sheet_a,
    )  # fmt: skip
    sheets.write_xls(path, sheet_a)
    path = add(
        "register.csv",
        {"kind": "csv", "sheets": [{"name": "csv", "rows": 5, "header_row": 1}],
         "contains": [sheet_a[2].invoice_number]},
        sheet_a,
    )  # fmt: skip
    sheets.write_csv(path, sheet_a)
    sheet_b[0].customer_name = "Café Lumière"
    path = add(
        "register_semicolon_cp1252.csv",
        {"kind": "csv", "sheets": [{"name": "csv", "rows": 3, "header_row": 1}],
         "contains": ["Café Lumière"]},
        sheet_b,
    )  # fmt: skip
    sheets.write_csv(path, sheet_b, delimiter=";", encoding="cp1252")

    # A real PNG renamed to .pdf: detection must follow the bytes.
    path = add("renamed_png.pdf", {"kind": "png", "pages": 1, "methods": ["ocr"]})
    cv2.imwrite(str(out / "_tmp.png"), clean[1])
    path.write_bytes((out / "_tmp.png").read_bytes())
    png_bytes = (out / "_tmp.png").read_bytes()
    (out / "_tmp.png").unlink()

    # Broken files.
    broken.truncated_pdf(good_pdf, add("truncated.pdf", {"error": "CORRUPTED_FILE"}))
    broken.garbage_pdf(add("garbage.pdf", {"error": "CORRUPTED_FILE"}))
    broken.encrypted_pdf(good_pdf, add("encrypted.pdf", {"error": "ENCRYPTED_PDF"}))
    broken.empty_file(add("empty.pdf", {"error": "EMPTY_FILE"}))
    broken.whitespace_file(add("whitespace.csv", {"error": "EMPTY_FILE"}))
    broken.text_named_pdf(add("note_renamed.pdf", {"error": "UNSUPPORTED_TYPE"}))
    broken.docx_like(add("letter.xlsx", {"error": "UNSUPPORTED_TYPE"}))
    broken.corrupted_xlsx(add("corrupted.xlsx", {"error": "CORRUPTED_FILE"}))
    broken.truncated_png(png_bytes, add("truncated.png", {"error": "CORRUPTED_FILE"}))

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
