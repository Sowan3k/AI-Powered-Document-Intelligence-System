"""Extract invoices from an ingested document and store them.

PDFs and images: low-confidence OCR pages go to the vision model first, then
pages go to the text model in overlapping windows, and the results are merged,
normalised and checked against the source text. Spreadsheets: columns are
mapped and rows converted in code.

Each invoice is stored with its typed values, per-field confidence, evidence
and flags (`field_meta`), and the model's raw reply (`raw_extraction`).
Validation (Phase 3) reads these. Running extraction again replaces the
document's invoices.
"""

import logging
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import DocumentStatus, PageMethod, ReviewStatus, SourceKind
from app.db.models import Document, Invoice, Job, LineItem, Page, ProcessingEvent, Sheet
from app.extract import prompts, segment, vision
from app.extract.build import build_invoice
from app.extract.columns import map_columns, rows_to_invoices
from app.extract.llm import LlmClient, LlmOutputError, LlmUsage, generate_structured, require_model
from app.extract.normalise import norm_invoice_number, norm_supplier
from app.extract.schemas import FIELDS, InvoiceData, LlmExtraction, LlmInvoice
from app.ingest import reader
from app.ingest.schemas import MIME_TYPES, FileKind
from app.storage import FileStorage

logger = logging.getLogger(__name__)

EXTRACTION_FAILED = "EXTRACTION_FAILED"
MONEY_LIMIT = Decimal("1e12")  # NUMERIC(14,2) holds 12 digits before the point
KIND_BY_MIME = {mime: kind for kind, mime in MIME_TYPES.items()}


@dataclass
class ExtractionOutcome:
    invoices: int = 0
    vision_pages: int = 0
    usages: list[LlmUsage] = field(default_factory=list)

    @property
    def prompt_tokens(self) -> int:
        return sum(u.prompt_tokens for u in self.usages)

    @property
    def output_tokens(self) -> int:
        return sum(u.output_tokens for u in self.usages)


def _event(session: Session, document: Document, job: Job | None, event: str, **detail: object):
    session.add(
        ProcessingEvent(
            document_id=document.id,
            job_id=job.id if job else None,
            event=event,
            detail=detail or None,
        )
    )


def _fit(value: Decimal | None, places: int, flags: list[str]) -> Decimal | None:
    """Fit a value into its NUMERIC column, flagging rounding or overflow."""
    if value is None:
        return None
    if abs(value) >= MONEY_LIMIT:
        flags.append("out_of_range")
        return None
    fitted = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if fitted != value:
        flags.append("rounded")
    return fitted


def _store(
    session: Session,
    document: Document,
    data: InvoiceData,
    raw: dict | None,
    sheet_id: int | None = None,
) -> Invoice:
    for name in ("subtotal", "tax", "total"):
        fv = data.field(name)
        fv.value = _fit(fv.value, 2, fv.flags)
    meta: dict[str, object] = {
        name: {
            "confidence": data.field(name).confidence,
            "evidence": data.field(name).evidence,
            "raw": data.field(name).raw,
            "flags": data.field(name).flags,
        }
        for name in FIELDS
    }
    meta["currencies_seen"] = data.currencies_seen
    invoice = Invoice(
        id=uuid.uuid4(),
        document_id=document.id,
        page_start=data.page_start,
        page_end=data.page_end,
        sheet_id=sheet_id,
        row_start=data.row_start,
        row_end=data.row_end,
        invoice_number=data.invoice_number.value,
        invoice_date=data.invoice_date.value,
        supplier_name=data.supplier_name.value,
        customer_name=data.customer_name.value,
        subtotal=data.subtotal.value,
        tax=data.tax.value,
        total=data.total.value,
        currency=data.currency.value,
        invoice_number_norm=norm_invoice_number(data.invoice_number.value),
        supplier_norm=norm_supplier(data.supplier_name.value),
        field_meta=meta,
        raw_extraction=raw,
        review_status=ReviewStatus.PENDING,
    )
    session.add(invoice)
    for item in data.line_items:
        flags: list[str] = []
        session.add(
            LineItem(
                invoice_id=invoice.id,
                position=item.position,
                description=item.description,
                quantity=_fit(item.quantity, 4, flags),
                unit_price=_fit(item.unit_price, 4, flags),
                amount=_fit(item.amount, 2, flags),
                confidence=item.confidence,
            )
        )
    return invoice


def extract_pages(
    llm: LlmClient,
    model: str,
    pages: list[tuple[int, str]],
    settings: Settings,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[LlmInvoice], list[LlmUsage]]:
    """Run the windows and merge. `pages` is (page number, text) in order.

    `on_progress(done, total)` is called after each window, so a long PDF can
    show "window 12 of 143" while it runs.
    """
    texts = dict(pages)
    results: list[tuple[list[int], list[LlmInvoice]]] = []
    usages: list[LlmUsage] = []
    all_windows = segment.windows(
        [n for n, _ in pages], settings.segment_window_pages, settings.segment_overlap_pages
    )
    for done, window in enumerate(all_windows, start=1):
        if on_progress is not None:
            on_progress(done - 1, len(all_windows))
        if not any(texts[n].strip() for n in window):
            continue  # blank pages: nothing to read, no call
        found, used = generate_structured(
            llm,
            LlmExtraction,
            purpose="extract_invoices",
            model=model,
            system=prompts.EXTRACTION_SYSTEM,
            parts=[prompts.extraction_prompt([(n, texts[n]) for n in window])],
            check=segment.page_range_check(window),
        )
        usages += used
        results.append((window, found.invoices))
    if on_progress is not None:
        on_progress(len(all_windows), len(all_windows))
    return segment.merge_windows(results), usages


def _download(storage: FileStorage, document: Document, tmp: str) -> tuple[Path, FileKind]:
    if document.storage_path is None or document.mime_type not in KIND_BY_MIME:
        raise ValueError(f"document {document.id} has no stored file of a known type")
    local = Path(tmp) / "original"
    storage.download(document.storage_path, local)
    return local, KIND_BY_MIME[document.mime_type]


def _vision_fallback(
    session: Session,
    storage: FileStorage,
    llm: LlmClient,
    document: Document,
    job: Job | None,
    pages: list[Page],
    settings: Settings,
    outcome: ExtractionOutcome,
) -> None:
    weak = {
        p.page_number: p
        for p in pages
        if p.method is PageMethod.OCR
        and p.ocr_confidence is not None  # None: a blank page, nothing to read
        and p.ocr_confidence < settings.ocr_confidence_threshold
    }
    if not weak:
        return
    if not settings.gemini_vision_model:
        logger.warning("document %s: %d weak OCR pages, no vision model", document.id, len(weak))
        return
    models = [settings.gemini_vision_model, settings.gemini_model]
    with tempfile.TemporaryDirectory(prefix="docintel-") as tmp:
        local, kind = _download(storage, document, tmp)
        for number, png in vision.page_images(local, kind, set(weak), settings.vision_dpi):
            result = vision.transcribe_with_fallback(llm, models, png)
            if result.text is None:
                # Keep the Tesseract text; its low confidence still sends the invoice to review.
                _event(session, document, job, "vision_failed", page=number, errors=result.errors)
                continue
            if result.usage is not None:
                outcome.usages.append(result.usage)
            page = weak[number]
            page.text = result.text
            page.method = PageMethod.VISION  # ocr_confidence keeps the Tesseract score
            outcome.vision_pages += 1
            _event(session, document, job, "vision_page", page=number, model=result.model)
    session.commit()


def extract_document(
    session: Session,
    storage: FileStorage,
    llm: LlmClient | None,
    document_id: uuid.UUID,
    settings: Settings,
    job: Job | None = None,
) -> ExtractionOutcome | None:
    """Extract and store invoices. Returns None if the model's output failed twice.

    Network and quota errors (LlmError) propagate, so the job queue can retry.
    PDFs and images need the model; spreadsheets whose columns map by rule do not.
    """
    document = session.get(Document, document_id)
    if document is None:
        raise ValueError(f"document {document_id} not found")
    paged = document.source_kind in (SourceKind.PDF, SourceKind.IMAGE)
    if paged and llm is None:
        raise RuntimeError("GEMINI_API_KEY must be set to extract PDFs and images")
    model = require_model(settings.gemini_model, "GEMINI_MODEL") if paged else settings.gemini_model
    outcome = ExtractionOutcome()
    session.execute(delete(Invoice).where(Invoice.document_id == document.id))
    _event(session, document, job, "extract_started")
    session.commit()

    try:
        if paged:
            assert llm is not None and model is not None  # noqa: S101 (checked above)
            _extract_paged(session, storage, llm, model, document, job, settings, outcome)
        else:
            _extract_sheets(session, storage, llm, model, document, settings, outcome)
    except LlmOutputError:
        session.rollback()
        document.status = DocumentStatus.FAILED
        document.error_code = EXTRACTION_FAILED
        document.error_message = "the model's reply did not match the schema twice"
        _event(session, document, job, "extract_failed", error_code=EXTRACTION_FAILED)
        session.commit()
        logger.info("extract %s failed: %s", document.id, EXTRACTION_FAILED)
        return None

    for usage in outcome.usages:
        _event(session, document, job, "llm_call", **usage.as_detail())
    _event(
        session,
        document,
        job,
        "extracted",
        invoices=outcome.invoices,
        vision_pages=outcome.vision_pages,
        prompt_tokens=outcome.prompt_tokens,
        output_tokens=outcome.output_tokens,
    )
    session.commit()
    logger.info("extract %s done: invoices=%d", document.id, outcome.invoices)
    return outcome


def _extract_paged(
    session: Session,
    storage: FileStorage,
    llm: LlmClient,
    model: str,
    document: Document,
    job: Job | None,
    settings: Settings,
    outcome: ExtractionOutcome,
) -> None:
    pages = list(
        session.scalars(
            select(Page).where(Page.document_id == document.id).order_by(Page.page_number)
        )
    )
    _vision_fallback(session, storage, llm, document, job, pages, settings, outcome)
    texts = [(p.page_number, p.text) for p in pages]
    by_number = dict(texts)

    def progress(done: int, total: int) -> None:
        # The job's progress switches from pages read to windows extracted.
        if job is not None:
            job.progress_done, job.progress_total = done, total
            session.commit()

    _event(session, document, job, "extract_windows", pages=len(texts))
    session.commit()
    found, usages = extract_pages(llm, model, texts, settings, on_progress=progress)
    outcome.usages += usages
    for inv in found:
        source = "\n".join(by_number.get(n, "") for n in range(inv.page_start, inv.page_end + 1))
        data = build_invoice(inv, source, day_first=settings.date_day_first)
        _store(session, document, data, inv.model_dump(mode="json"))
        outcome.invoices += 1
    session.commit()


def _extract_sheets(
    session: Session,
    storage: FileStorage,
    llm: LlmClient | None,
    model: str | None,
    document: Document,
    settings: Settings,
    outcome: ExtractionOutcome,
) -> None:
    sheet_ids = {
        s.sheet_index: s
        for s in session.scalars(select(Sheet).where(Sheet.document_id == document.id))
    }
    with tempfile.TemporaryDirectory(prefix="docintel-") as tmp:
        local, kind = _download(storage, document, tmp)
        sheets = reader.read_sheets(local, kind)
    for sheet in sheets:
        if not sheet.rows:
            continue
        mapping = map_columns(sheet, llm, model)
        outcome.usages += mapping.usages
        row = sheet_ids.get(sheet.sheet_index)
        if row is not None:
            row.column_mapping = {
                "headers": sheet.headers,
                "fields": mapping.columns,
                "by_llm": sorted(mapping.by_llm),
            }
        for data in rows_to_invoices(sheet, mapping, day_first=settings.date_day_first):
            raw = {"sheet": sheet.sheet_name, "row_start": data.row_start, "row_end": data.row_end}
            _store(session, document, data, raw, sheet_id=row.id if row is not None else None)
            outcome.invoices += 1
    session.commit()
