"""Evaluation run: the full pipeline on the labelled synthetic dataset.

Generates the dataset, uploads every file through the same code the API
uses, lets the real worker process the queue (ingest, OCR, Gemini
extraction, validation, indexing), then scores the stored results against
the ground truth. Writes a JSON report and a Markdown summary.

Run from backend/ with a throwaway database (the GitHub Actions workflow
"Evaluation" does this with the GEMINI_API_KEY secret):

    PYTHONPATH=.:../eval/generate python ../eval/run_eval.py --scale 2

`--fake` swaps Gemini for the test suite's perfect-reader model, to check
the scoring code without spending tokens; its accuracy numbers mean nothing.
"""

import argparse
import json
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import Document, Invoice, Job, Page, ProcessingEvent, ValidationIssue
from app.db.session import get_sessionmaker
from app.extract.llm import get_llm_client
from app.extract.normalise import norm_invoice_number, norm_supplier
from app.ingest.upload import register_upload
from app.storage.local import LocalStorage
from app.worker import queue
from app.worker.main import Worker
from sqlalchemy import func, select
from synth.dataset import build

FIELDS = ("invoice_number", "invoice_date", "supplier_name", "customer_name",
          "subtotal", "tax", "total", "currency")  # fmt: skip
# The rule each planted error must trigger (PHASES.md Phase 3).
EXPECTED_RULE = {
    "wrong_total": "R05", "wrong_line_sum": "R03", "wrong_line_amount": "R04",
    "missing_tax": "R01", "missing_customer": "R01", "future_date": "R08",
    "duplicate": "R06", "near_duplicate": "R07", "missing_number": "R01",
}  # fmt: skip


def norm(field: str, value: object) -> object:
    """Compare values the way a person would: normalised text, exact numbers."""
    if value in (None, ""):
        return None
    if field == "invoice_number":
        return norm_invoice_number(str(value))
    if field == "supplier_name":
        return norm_supplier(str(value))
    if field == "customer_name":
        return " ".join(str(value).lower().split())
    if field in ("subtotal", "tax", "total"):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    if field == "invoice_date":
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    return str(value).upper()


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def summary(values: list[float]) -> dict[str, float | None]:
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 2) if values else None,
        "p95": round(p95(values), 2) if values else None,
    }


def match_invoices(stored: list[Invoice], truth: list[dict]) -> list[tuple[Invoice | None, dict]]:
    """Pair each true invoice with a stored one: by number, else by position."""
    left = list(stored)
    pairs: list[tuple[Invoice | None, dict]] = []
    for i, want in enumerate(truth):
        key = norm_invoice_number(want["invoice_number"])
        hit = next((s for s in left if key and s.invoice_number_norm == key), None)
        if hit is None and i < len(stored) and stored[i] in left and not key:
            hit = stored[i]
        if hit is not None:
            left.remove(hit)
        pairs.append((hit, want))
    return pairs


def line_scores(inv: Invoice, want: dict) -> tuple[int, int, int]:
    """True positives, extracted count, expected count. A line matches on its amount."""
    got = [li.amount for li in inv.line_items if li.amount is not None]
    expected = [Decimal(li["amount"]) for li in want["line_items"]]
    tp = 0
    pool = list(got)
    for amount in expected:
        if amount in pool:
            pool.remove(amount)
            tp += 1
    return tp, len(inv.line_items), len(expected)


def run(scale: int, fake: bool, workdir: Path, budget_s: float = 45 * 60) -> dict:
    settings = get_settings()
    configure_logging(settings.log_level)
    data = workdir / "data"
    manifest = build(data, seed=7, scale=scale)
    truths = {
        e["file"]: json.loads((data / f"{e['file']}.json").read_text())
        for e in manifest
        if (data / f"{e['file']}.json").exists()
    }
    if fake:
        from tests.conftest import FakeLlmClient
        from tests.unit.extract.test_extract_fixtures import reader_for_truths

        llm = FakeLlmClient(reader_for_truths(list(truths.values())))
    else:
        llm = get_llm_client(settings)
    sessions = get_sessionmaker()
    storage = LocalStorage(workdir / "store")
    worker = Worker(0.1, sessions=sessions, storage=storage, llm=llm, settings=settings)

    started = time.monotonic()
    ids: dict[str, object] = {}
    with sessions() as session:
        for entry in manifest:
            doc = register_upload(session, storage, entry["file"], data / entry["file"], settings)
            session.flush()
            if doc.storage_path:
                queue.enqueue(session, doc.id, queue.JOB_PROCESS, settings)
            ids[entry["file"]] = doc.id
            session.commit()
    jobs = 0
    while True:
        if time.monotonic() - started > budget_s:
            print(
                f"  time budget of {budget_s / 60:.0f} min used; scoring what finished", flush=True
            )
            break
        if worker.run_once():
            jobs += 1
            if jobs % 5 == 0:
                print(f"  {jobs} jobs run, {time.monotonic() - started:.0f}s", flush=True)
            continue
        with sessions() as session:
            waiting = session.scalar(
                select(func.count()).select_from(Job).where(Job.status.in_(queue.ACTIVE))
            )
        if not waiting:
            break
        time.sleep(0.5)  # a retry is waiting for its backoff
    wall_s = time.monotonic() - started

    return score(sessions, manifest, truths, ids, settings, wall_s, scale, fake)


def score(sessions, manifest, truths, ids, settings, wall_s, scale, fake) -> dict:  # type: ignore[no-untyped-def]
    field_hits: Counter[str] = Counter()
    field_total: Counter[str] = Counter()
    found = expected_invoices = 0
    line_tp = line_got = line_want = 0
    outcomes: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    failure_errors: dict[str, str | None] = {}
    expected_failures: dict[str, str] = {}
    timing = defaultdict(list)
    tokens_per_doc: list[int] = []
    tokens_by_purpose: Counter[str] = Counter()
    calls_by_purpose: Counter[str] = Counter()
    pages_by_method: Counter[str] = Counter()
    detection: dict[str, list[bool]] = defaultdict(list)
    clean_flagged = clean_total = 0
    flag_rules: Counter[str] = Counter()
    wrong_fields: Counter[str] = Counter()

    with sessions() as s:
        for entry in manifest:
            name, expect = entry["file"], entry["expect"]
            doc = s.get(Document, ids[name])
            if doc.status.value in ("queued", "processing"):
                outcomes["not processed (time budget)"] += 1
                continue
            if "error" in expect:
                ok = doc.error_code == expect["error"]
                outcomes["correctly rejected" if ok else "wrong outcome on a broken file"] += 1
                expected_failures[name] = doc.error_code or doc.status.value
                continue
            if doc.status.value != "completed":
                outcomes["failed"] += 1
                failures[doc.error_code or "unknown"] += 1
                last = s.scalars(
                    select(Job.last_error).where(Job.document_id == doc.id)
                    .order_by(Job.created_at.desc())
                ).first()  # fmt: skip
                failure_errors[f"{name}: {doc.error_code}"] = last
                continue
            outcomes["completed"] += 1

            events = s.scalars(
                select(ProcessingEvent).where(ProcessingEvent.document_id == doc.id)
                .order_by(ProcessingEvent.id)
            ).all()  # fmt: skip
            at = {e.event: e.created_at for e in events}
            starts = [e.created_at for e in events if e.event == "job_started"]
            end = at.get("completed")
            pages = s.scalars(select(Page).where(Page.document_id == doc.id)).all()
            methods = {p.method.value for p in pages}
            for p in pages:
                pages_by_method[p.method.value] += 1
            path = (
                "spreadsheet" if not pages
                else "vision" if "vision" in methods
                else "ocr" if "ocr" in methods
                else "digital"
            )  # fmt: skip
            if starts and end:
                seconds = (end - starts[-1]).total_seconds()
                timing[f"document:{path}"].append(seconds)
                if pages:
                    timing[f"page:{path}"].append(seconds / len(pages))
            calls = [e for e in events if e.event == "llm_call"]
            tokens = 0
            for e in calls:
                n = int(e.detail["prompt_tokens"]) + int(e.detail["output_tokens"])
                tokens += n
                tokens_by_purpose[e.detail["purpose"]] += n
                calls_by_purpose[e.detail["purpose"]] += 1
            tokens_per_doc.append(tokens)

            truth = truths.get(name)
            if truth is None:
                continue
            stored = s.scalars(
                select(Invoice).where(Invoice.document_id == doc.id)
                .order_by(Invoice.page_start, Invoice.row_start)
            ).all()  # fmt: skip
            expected_invoices += len(truth["invoices"])
            for inv, want in match_invoices(list(stored), truth["invoices"]):
                planted = want.get("planted") or []
                if inv is None:
                    for f in FIELDS:
                        field_total[f] += 1
                    for p in planted:
                        detection[p].append(False)
                    continue
                found += 1
                for f in FIELDS:
                    field_total[f] += 1
                    if norm(f, getattr(inv, f)) == norm(f, want[f]):
                        field_hits[f] += 1
                    else:
                        wrong_fields[f"{f} ({path})"] += 1
                tp, got, exp = line_scores(inv, want)
                if path != "spreadsheet" and (exp or got):  # registers have no line columns
                    line_tp, line_got, line_want = line_tp + tp, line_got + got, line_want + exp
                issues = s.scalars(
                    select(ValidationIssue).where(ValidationIssue.invoice_id == inv.id)
                ).all()
                codes = {i.rule_code for i in issues}
                for p in planted:
                    detection[p].append(EXPECTED_RULE[p] in codes)
                if not planted:
                    # Many fixtures repeat the same invoices on purpose (one invoice as a
                    # PDF, a scan and a TIFF), so R06 and R07 are left out here.
                    errors = {i.rule_code for i in issues if i.severity.value == "error"} - {
                        "R06",
                        "R07",
                    }
                    clean_total += 1
                    if errors:
                        clean_flagged += 1
                        flag_rules.update(errors)
        job_attempts = Counter(j.attempts for j in s.scalars(select(Job)))

    precision = line_tp / line_got if line_got else None
    recall = line_tp / line_want if line_want else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    total_fields = sum(field_total.values())
    return {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "fake_model": fake,
        "models": {
            "text": settings.gemini_model,
            "vision": settings.gemini_vision_model,
            "embedding": settings.gemini_embed_model,
        },
        "dataset": {"scale": scale, "files": len(manifest), "invoices_expected": expected_invoices},
        "wall_seconds": round(wall_s, 1),
        "documents": dict(outcomes),
        "failures_by_cause": dict(failures),
        "failure_errors": failure_errors,
        "broken_files": expected_failures,
        "invoices": {"expected": expected_invoices, "found": found},
        "field_accuracy": {
            f: round(field_hits[f] / field_total[f], 4) for f in FIELDS if field_total[f]
        },
        "field_accuracy_overall": round(sum(field_hits.values()) / total_fields, 4)
        if total_fields
        else None,
        "wrong_fields": dict(wrong_fields.most_common()),
        "line_items": {
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
            "extracted": line_got,
            "expected": line_want,
        },
        "timing_seconds": {k: summary(v) for k, v in sorted(timing.items())},
        "pages_by_method": dict(pages_by_method),
        "validation": {
            "detection": {p: f"{sum(v)}/{len(v)}" for p, v in sorted(detection.items())},
            "detection_rate": round(
                sum(sum(v) for v in detection.values()) / sum(len(v) for v in detection.values()), 4
            )
            if detection
            else None,
            "clean_invoices": clean_total,
            "clean_with_errors": clean_flagged,
            "false_flag_rate": round(clean_flagged / clean_total, 4) if clean_total else None,
            "false_flag_rules": dict(flag_rules),
        },  # fmt: skip
        "tokens": {
            "per_document": summary([float(t) for t in tokens_per_doc]),
            "total": sum(tokens_per_doc),
            "by_purpose": dict(tokens_by_purpose),
            "calls_by_purpose": dict(calls_by_purpose),
        },
        "job_attempts": {str(k): v for k, v in sorted(job_attempts.items())},
    }


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def markdown(r: dict) -> str:
    lines = [
        f"Run: {r['run_at']}. Models: text `{r['models']['text']}`, vision `{r['models']['vision']}`, "
        f"embedding `{r['models']['embedding']}`."
        + (" **Fake model: numbers are not real.**" if r["fake_model"] else ""),
        f"Dataset: {r['dataset']['files']} files (scale {r['dataset']['scale']}), "
        f"{r['dataset']['invoices_expected']} labelled invoices. Wall time {r['wall_seconds']} s.",
        "",
        "| Field | Accuracy |",
        "|---|---|",
        *[f"| {f} | {pct(a)} |" for f, a in r["field_accuracy"].items()],
        f"| **all fields** | **{pct(r['field_accuracy_overall'])}** |",
        "",
        f"Invoices found: {r['invoices']['found']} of {r['invoices']['expected']}.",
        f"Line items: precision {pct(r['line_items']['precision'])}, recall {pct(r['line_items']['recall'])}, "
        f"F1 {pct(r['line_items']['f1'])} ({r['line_items']['extracted']} extracted, {r['line_items']['expected']} expected).",
        "",
        f"Documents: {r['documents']}. Failures by cause: {r['failures_by_cause'] or 'none'}.",
        f"Last error of each failed document: {r['failure_errors'] or 'none'}.",
        f"Broken files and the code each got: {r['broken_files']}.",
        "",
        "| Timing | n | mean (s) | p95 (s) |",
        "|---|---|---|---|",
        *[f"| {k} | {v['n']} | {v['mean']} | {v['p95']} |" for k, v in r["timing_seconds"].items()],
        "",
        f"Pages by method: {r['pages_by_method']}.",
        "",
        f"Validation: planted errors detected {pct(r['validation']['detection_rate'])} "
        f"({r['validation']['detection']}). Clean invoices with an error-level flag: "
        f"{r['validation']['clean_with_errors']} of {r['validation']['clean_invoices']} "
        f"({pct(r['validation']['false_flag_rate'])}), rules: {r['validation']['false_flag_rules'] or 'none'}.",
        "",
        f"Tokens: {r['tokens']['total']} in total; per completed document mean "
        f"{r['tokens']['per_document']['mean']}, p95 {r['tokens']['per_document']['p95']}. "
        f"By purpose: {r['tokens']['by_purpose']}. Calls: {r['tokens']['calls_by_purpose']}.",
        f"Job attempts: {r['job_attempts']}.",
        f"Wrong fields (field and path): {r['wrong_fields'] or 'none'}.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("../eval/reports"))
    parser.add_argument("--budget-min", type=float, default=45, help="stop taking jobs after this")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="docintel-eval-") as tmp:
        report = run(args.scale, args.fake, Path(tmp), args.budget_min * 60)
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = report["run_at"].replace(":", "").replace("-", "")
    (args.out / f"eval-{stamp}.json").write_text(json.dumps(report, indent=2, default=str))
    text = markdown(report)
    (args.out / f"eval-{stamp}.md").write_text(text + "\n")
    print("\n===== EVALUATION REPORT =====")
    print(text)
    print("===== JSON =====")
    print(json.dumps(report, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
