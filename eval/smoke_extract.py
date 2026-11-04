"""Smoke test of extraction with the real Gemini API.

Generates a few synthetic invoices (digital PDFs in three layouts and one
light scan), runs the real extraction path on them, and compares the values
with the ground truth. Prints one line per invoice and the token totals.
Exits with status 1 if a call fails or the schema is rejected.

Run from backend/ (the GitHub Actions workflow "Gemini smoke test" does this):

    PYTHONPATH=.:../eval/generate python ../eval/smoke_extract.py

Needs GEMINI_API_KEY, GEMINI_MODEL and GEMINI_VISION_MODEL in the environment.
The data is synthetic, so printing values here exposes nothing real.
"""

import json
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.extract.build import build_invoice
from app.extract.llm import LlmError, get_llm_client, require_model
from app.extract.normalise import norm_supplier
from app.extract.service import extract_pages
from app.extract.vision import page_images, transcribe_with_fallback
from app.ingest.reader import read_document
from synth.dataset import build

FILES = ["digital_classic_0.pdf", "digital_modern_0.pdf", "digital_european_0.pdf",
         "planted_missing_tax.pdf", "scanned_light.pdf"]  # fmt: skip


def compare(got, want: dict) -> list[str]:  # type: ignore[no-untyped-def]
    wrong = []
    checks = {
        "invoice_number": (got.invoice_number.value, want["invoice_number"]),
        "invoice_date": (got.invoice_date.value, date.fromisoformat(want["invoice_date"])),
        "supplier_name": (
            norm_supplier(got.supplier_name.value),
            norm_supplier(want["supplier_name"]),
        ),
        "customer_name": (got.customer_name.value, want["customer_name"]),
        "currency": (got.currency.value, want["currency"]),
    }
    for key in ("subtotal", "tax", "total"):
        checks[key] = (got.field(key).value, None if want[key] is None else Decimal(want[key]))
    for name, (a, b) in checks.items():
        if a != b:
            wrong.append(name)
    return wrong


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    llm = get_llm_client(settings)
    model = require_model(settings.gemini_model, "GEMINI_MODEL")
    vision_model = require_model(settings.gemini_vision_model, "GEMINI_VISION_MODEL")
    tokens = [0, 0]
    fields = mismatched = 0
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        build(out)
        for name in FILES:
            truth = json.loads((out / f"{name}.json").read_text())
            doc = read_document(out / name, settings)
            texts = {p.page_number: p.text for p in doc.pages}
            try:
                if name.startswith("scanned"):
                    pages = page_images(out / name, doc.kind, set(texts), settings.vision_dpi)
                    for n, png in pages:
                        result = transcribe_with_fallback(llm, [vision_model, model], png)
                        for error in result.errors:
                            print(f"  vision page {n}: {error}")
                        if result.text is None or result.usage is None:
                            print(f"  vision page {n}: every model failed, kept Tesseract text")
                            continue
                        print(f"  vision page {n}: read by {result.model}")
                        texts[n] = result.text
                        tokens[0] += result.usage.prompt_tokens
                        tokens[1] += result.usage.output_tokens
                found, usages = extract_pages(llm, model, sorted(texts.items()), settings)
            except LlmError as exc:
                print(f"FAIL {name}: {exc}")
                return 1
            tokens[0] += sum(u.prompt_tokens for u in usages)
            tokens[1] += sum(u.output_tokens for u in usages)
            built = [build_invoice(i, texts[i.page_start]) for i in found]
            print(f"{name}: {len(built)} invoices found, {len(truth['invoices'])} expected")
            for got, want in zip(built, truth["invoices"], strict=False):
                wrong = compare(got, want)
                fields += 8
                mismatched += len(wrong)
                flags = sorted({f for n in ("invoice_number", "total") for f in got.field(n).flags})
                print(
                    f"  {want['invoice_number']}: wrong={wrong or 'none'} flags={flags or 'none'}"
                )
    print(f"fields correct: {fields - mismatched}/{fields}")
    print(f"tokens: prompt={tokens[0]} output={tokens[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
