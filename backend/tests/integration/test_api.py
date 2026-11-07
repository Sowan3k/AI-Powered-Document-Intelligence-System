"""Every endpoint, end to end on Postgres, with the worker run in-process."""

import contextlib
import csv
import io
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_llm, get_storage
from app.core.config import Settings, get_settings
from app.core.pricing import PRICES_USD_PER_M
from app.core.ratelimit import login_limiter, upload_limiter
from app.db.models import Document, Invoice
from app.db.session import get_db
from app.extract.llm import LlmError
from app.extract.normalise import norm_supplier
from app.main import create_app
from app.storage.local import LocalStorage
from app.worker.main import Worker
from tests.conftest import FakeCall, FakeLlmClient
from tests.unit.extract.test_extract_fixtures import reader_for_truths

PASSWORD = "test-password-not-real"
SECRET = "test-jwt-secret-not-real-0123456789"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        jwt_secret=SECRET,
        demo_username="reviewer",
        demo_password=PASSWORD,
        gemini_model="text-model",
        gemini_vision_model="vision-model",
        gemini_embed_model="embed-model",
        embed_dim=768,
        job_backoff_s=0,
        login_rate_per_minute=5,
        upload_rate_per_minute=20,
        segment_window_pages=3,
        segment_overlap_pages=1,
    )


class Env:
    def __init__(
        self, client: TestClient, db: Session, worker: Worker, fake: FakeLlmClient, dir: Path
    ):  # type: ignore[no-untyped-def]
        self.client, self.db, self.worker, self.fake, self.dir = client, db, worker, fake, dir
        self.headers: dict[str, str] = {}
        self.storage: LocalStorage = worker.storage  # type: ignore[assignment]

    def login(self) -> None:
        r = self.client.post("/api/auth/login", json={"username": "reviewer", "password": PASSWORD})
        assert r.status_code == 200, r.text
        self.headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    def get(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.get(url, headers=self.headers, **kw)

    def post(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.post(url, headers=self.headers, **kw)

    def patch(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.patch(url, headers=self.headers, **kw)

    def delete(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.delete(url, headers=self.headers, **kw)

    def upload(self, *names: str) -> dict:
        files = [
            ("files", (n, (self.dir / n).read_bytes(), "application/octet-stream")) for n in names
        ]
        r = self.post("/api/documents", files=files)
        assert r.status_code == 202, r.text
        return r.json()

    def work(self) -> int:
        """Run the worker until the queue is empty. Returns jobs run."""
        n = 0
        while self.worker.run_once():
            n += 1
            assert n < 50
        return n

    def truth(self, name: str) -> dict:
        return json.loads((self.dir / f"{name}.json").read_text())


@pytest.fixture
def env(db: Session, settings: Settings, tmp_path: Path, synthetic_dir: Path) -> Iterator[Env]:
    storage = LocalStorage(tmp_path / "store")
    fake = FakeLlmClient()
    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_llm] = lambda: fake
    worker = Worker(
        poll_interval_s=0.01,
        sessions=lambda: contextlib.nullcontext(db),
        storage=storage,
        llm=fake,
        settings=settings,
        heartbeats=False,
    )
    login_limiter.reset()
    upload_limiter.reset()
    with TestClient(app) as client:
        yield Env(client, db, worker, fake, synthetic_dir)
    login_limiter.reset()
    upload_limiter.reset()


# --- auth ---


def test_login_and_protected_routes(env: Env) -> None:
    assert env.get("/api/documents").status_code == 401
    bad = env.client.post("/api/auth/login", json={"username": "reviewer", "password": "nope"})
    assert bad.status_code == 401
    env.login()
    assert env.get("/api/documents").status_code == 200
    assert env.client.get("/api/health/live").status_code == 200  # no auth needed


def test_bad_and_expired_tokens(env: Env) -> None:
    def call(token: str) -> int:
        return env.client.get(
            "/api/documents", headers={"Authorization": f"Bearer {token}"}
        ).status_code

    assert call("not-a-jwt") == 401
    past = datetime.now(UTC) - timedelta(hours=3)
    expired = jwt.encode(
        {"sub": "reviewer", "iss": "docintel", "iat": past, "exp": past + timedelta(hours=1)},
        SECRET,
        algorithm="HS256",
    )
    assert call(expired) == 401
    forged = jwt.encode(
        {"sub": "reviewer", "iss": "docintel", "iat": datetime.now(UTC),
         "exp": datetime.now(UTC) + timedelta(hours=1)},
        "another-secret-of-enough-length-000",
        algorithm="HS256",
    )  # fmt: skip
    assert call(forged) == 401


def test_login_is_rate_limited(env: Env) -> None:
    for _ in range(5):
        env.client.post("/api/auth/login", json={"username": "x", "password": "y"})
    r = env.client.post("/api/auth/login", json={"username": "reviewer", "password": PASSWORD})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


def test_login_not_configured(env: Env, settings: Settings) -> None:
    settings.demo_password = None
    r = env.client.post("/api/auth/login", json={"username": "reviewer", "password": "x"})
    assert r.status_code == 503


# --- upload, worker, documents, jobs, results ---


def test_upload_batch_with_a_bad_file(env: Env) -> None:
    env.login()
    body = env.upload("digital_classic_0.pdf", "empty.pdf", "register.csv")
    assert (body["accepted"], body["rejected"]) == (2, 1)
    by_name = {d["filename"]: d for d in body["documents"]}
    assert by_name["empty.pdf"]["error_code"] == "EMPTY_FILE"
    assert by_name["empty.pdf"]["job_id"] is None
    assert by_name["register.csv"]["status"] == "queued"


def test_upload_limits(env: Env, settings: Settings) -> None:
    env.login()
    settings.max_files_per_batch = 2
    files = [("files", (f"f{i}.csv", b"a,b\n1,2\n", "text/csv")) for i in range(3)]
    assert env.post("/api/documents", files=files).status_code == 400
    huge = {"Content-Length": str(10**12), **env.headers}
    assert env.client.post("/api/documents", headers=huge, content=b"x").status_code == 413


def test_upload_is_rate_limited(env: Env, settings: Settings) -> None:
    env.login()
    settings.upload_rate_per_minute = 2
    files = [("files", ("a.csv", b"a,b\n1,2\n", "text/csv"))]
    codes = [env.post("/api/documents", files=files).status_code for _ in range(3)]
    assert codes == [202, 202, 429]


def test_full_pipeline_then_search_and_correct(env: Env) -> None:
    env.login()
    names = ["multi_invoice.pdf", "planted_wrong_total.pdf"]
    env.fake.replies = reader_for_truths([env.truth(n) for n in names])
    body = env.upload(*names)
    assert env.work() == 2
    multi = body["documents"][0]

    job = env.get(f"/api/jobs/{multi['job_id']}").json()
    # Progress counts pages while reading, then extraction windows (4 pages, windows of 3).
    assert (job["status"], job["attempts"], job["progress_done"], job["progress_total"]) == (
        "succeeded", 1, 2, 2,
    )  # fmt: skip

    doc = env.get(f"/api/documents/{multi['document_id']}").json()
    assert doc["status"] == "completed" and doc["invoice_count"] == 4
    history = [e["event"] for e in doc["history"]]
    for step in ("uploaded", "job_queued", "job_started", "ingested", "extracted", "validated",
                 "completed", "job_succeeded"):  # fmt: skip
        assert step in history, step
    purposes = {e["detail"]["purpose"] for e in doc["history"] if e["event"] == "llm_call"}
    assert purposes == {"extract_invoices", "embed"}  # embeddings are counted too

    results = env.get(f"/api/documents/{multi['document_id']}/results?include_pages=true").json()
    truth = env.truth("multi_invoice.pdf")["invoices"]
    assert [i["invoice_number"] for i in results["invoices"]] == [
        t["invoice_number"] for t in truth
    ]
    first = results["invoices"][0]
    assert first["total"] == truth[0]["total"]  # money as a decimal string
    assert first["line_items"] and first["issues"] == []
    assert first["review_status"] == "ok"
    assert len(results["pages"]) == 4

    listing = env.get("/api/documents", params={"status": "completed", "limit": 1}).json()
    assert listing["total"] == 2 and len(listing["items"]) == 1

    # Keyword search: an invoice number, then filters.
    number = truth[2]["invoice_number"]
    hits = env.get("/api/search", params={"q": number}).json()
    assert hits["items"][0]["invoice_number"] == number and hits["items"][0]["score"] > 0
    supplier = truth[0]["supplier_name"]
    by_supplier = env.get("/api/search", params={"supplier": supplier.upper()}).json()
    assert by_supplier["items"]
    assert {norm_supplier(h["supplier_name"]) for h in by_supplier["items"]} == {
        norm_supplier(supplier)
    }
    total = Decimal(truth[1]["total"])
    ranged = env.get(
        "/api/search", params={"amount_min": str(total), "amount_max": str(total)}
    ).json()
    assert truth[1]["invoice_number"] in [h["invoice_number"] for h in ranged["items"]]

    # Semantic search: words from one invoice's line items find it first.
    words = " ".join(li["description"] for li in truth[3]["line_items"])
    semantic = env.get("/api/search", params={"mode": "semantic", "q": words}).json()
    assert semantic["items"][0]["invoice_number"] == truth[3]["invoice_number"]
    assert env.fake.embedded[-1].startswith("task: search result | query: ")
    assert env.get("/api/search", params={"mode": "semantic"}).status_code == 400

    # The planted wrong total is in the review queue.
    queue = env.get("/api/review-queue").json()
    [item] = queue["items"]
    assert item["filename"] == "planted_wrong_total.pdf" and item["error_count"] == 1
    assert item["mime_type"] == "application/pdf"  # the queue offers a retake for photos
    assert item["top_issue"].startswith("subtotal plus tax is")

    # Correct it: the issue goes, the correction is recorded, an index job re-embeds it.
    wrong = env.truth("planted_wrong_total.pdf")["invoices"][0]
    fixed = str(Decimal(wrong["subtotal"]) + Decimal(wrong["tax"] or "0"))
    r = env.patch(f"/api/invoices/{item['id']}", json={"total": fixed, "mark_reviewed": True})
    assert r.status_code == 200, r.text
    corrected = r.json()
    assert corrected["total"] == fixed and corrected["issues"] == []
    assert corrected["review_status"] == "reviewed"
    assert corrected["field_meta"]["total"]["flags"] == ["corrected"]
    [change] = corrected["corrections"]
    assert (change["field"], change["old_value"], change["new_value"], change["username"]) == (
        "total", wrong["total"], fixed, "reviewer",
    )  # fmt: skip
    assert env.get("/api/review-queue").json()["total"] == 0
    embedded = len(env.fake.embedded)
    assert env.work() == 1  # the index job
    assert len(env.fake.embedded) == embedded + 1


def test_correction_validation(env: Env) -> None:
    env.login()
    missing = f"/api/invoices/{uuid.uuid4()}"
    assert env.patch(missing, json={"total": "1.00"}).status_code == 404
    assert env.patch(missing, json={"total": "1.001"}).status_code == 422
    assert env.patch(missing, json={"currency": "DOLLARS"}).status_code == 422
    assert env.patch(missing, json={"unknown": 1}).status_code == 422


def test_failed_job_is_retried_then_succeeds(env: Env, settings: Settings) -> None:
    env.login()
    truth = env.truth("digital_modern_0.pdf")
    healthy = reader_for_truths([truth])
    state = {"down": True}

    def flaky(call: FakeCall):  # type: ignore[no-untyped-def]
        if state["down"]:
            raise LlmError("Gemini call failed with HTTP 503")
        return healthy(call)

    env.fake.replies = flaky
    body = env.upload("digital_modern_0.pdf")
    job_id = body["documents"][0]["job_id"]
    assert env.work() == settings.job_max_attempts  # retried with backoff, then failed
    job = env.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "failed" and job["attempts"] == 3
    assert "HTTP 503" in job["last_error"]
    doc = env.get(f"/api/documents/{body['documents'][0]['document_id']}").json()
    assert (doc["status"], doc["error_code"]) == ("failed", "JOB_FAILED")
    events = [e["event"] for e in doc["history"]]
    assert events.count("job_retry_scheduled") == 2 and "job_failed" in events

    state["down"] = False
    retried = env.post(f"/api/jobs/{job_id}/retry")
    assert retried.status_code == 202 and retried.json()["status"] == "queued"
    assert env.post(f"/api/jobs/{job_id}/retry").status_code == 409  # not failed any more
    assert env.work() == 1
    assert env.get(f"/api/jobs/{job_id}").json()["status"] == "succeeded"
    assert env.get(f"/api/documents/{doc['id']}").json()["status"] == "completed"


def test_unreadable_file_fails_once_without_retries(env: Env) -> None:
    env.login()
    body = env.upload("encrypted.pdf")
    assert env.work() == 1
    job = env.get(f"/api/jobs/{body['documents'][0]['job_id']}").json()
    assert (job["status"], job["attempts"], job["last_error"]) == ("failed", 1, "ENCRYPTED_PDF")
    doc = env.get(f"/api/documents/{body['documents'][0]['document_id']}").json()
    assert doc["error_code"] == "ENCRYPTED_PDF"


def test_reprocess(env: Env) -> None:
    env.login()
    env.fake.replies = reader_for_truths([env.truth("digital_european_0.pdf")])
    body = env.upload("digital_european_0.pdf", "empty.pdf")
    good, rejected = (d["document_id"] for d in body["documents"])
    env.work()
    r = env.post(f"/api/documents/{good}/reprocess")
    assert r.status_code == 202 and r.json()["status"] == "queued"
    assert env.post(f"/api/documents/{good}/reprocess").status_code == 409  # already queued
    assert env.post(f"/api/documents/{rejected}/reprocess").status_code == 409  # nothing stored
    env.work()
    results = env.get(f"/api/documents/{good}/results").json()
    assert len(results["invoices"]) == 1  # replaced, not doubled


def test_not_found(env: Env) -> None:
    env.login()
    missing = uuid.uuid4()
    for url in (f"/api/documents/{missing}", f"/api/documents/{missing}/results",
                f"/api/jobs/{missing}", f"/api/reconciliations/{missing}"):  # fmt: skip
        assert env.get(url).status_code == 404, url
    assert env.post(f"/api/jobs/{missing}/retry").status_code == 404
    assert env.post(f"/api/documents/{missing}/reprocess").status_code == 404


def test_reconcile_endpoint(env: Env) -> None:
    env.login()
    env.fake.replies = reader_for_truths([env.truth("recon_statement.pdf")])
    body = env.upload("recon_statement.pdf", "recon_register.xlsx")
    a, b = (d["document_id"] for d in body["documents"])
    # Not read yet: a partial report would mislead, so it waits (D88).
    early = env.post("/api/reconcile", json={"document_a": a, "document_b": b})
    assert early.status_code == 409 and "still being processed" in early.json()["detail"]
    env.work()
    r = env.post("/api/reconcile", json={"document_a": a, "document_b": b})
    assert r.status_code == 201, r.text
    summary = r.json()["result"]["summary"]
    counts = [summary[k] for k in ("matched", "mismatched", "only_in_a", "only_in_b")]
    assert counts == [2, 1, 1, 1]
    stored = env.get(f"/api/reconciliations/{r.json()['id']}").json()
    assert stored["result"]["summary"] == summary
    assert env.post("/api/reconcile", json={"document_a": a, "document_b": a}).status_code == 400
    missing = {"document_a": a, "document_b": str(uuid.uuid4())}
    assert env.post("/api/reconcile", json=missing).status_code == 404


def test_reconcile_suggestions_rank_pairs_that_share_invoices(env: Env) -> None:
    env.login()
    assert env.get("/api/reconcile/suggestions").json() == {"items": []}
    env.fake.replies = reader_for_truths([env.truth("recon_statement.pdf")])
    body = env.upload("recon_statement.pdf", "recon_register.xlsx", "register.csv")
    statement, register, other = (d["document_id"] for d in body["documents"])
    env.work()
    items = env.get("/api/reconcile/suggestions").json()["items"]
    # The statement and its register share 3 invoices: 2 by number (one with a
    # changed total) and 1 with no number, matched by supplier, date and total.
    # register.csv shares nothing with either.
    assert len(items) == 1
    pair = items[0]
    assert pair["document_a"]["id"] == statement  # the PDF reads as side A
    assert pair["document_b"]["id"] == register
    assert pair["shared"] == 3
    assert pair["document_a"]["invoice_count"] == 4
    assert other not in {pair["document_a"]["id"], pair["document_b"]["id"]}
    assert env.client.get("/api/reconcile/suggestions").status_code == 401


def test_document_list_filters_by_name_and_kind(env: Env) -> None:
    env.login()
    env.upload("register.csv", "register.xlsx", "register_semicolon_cp1252.csv")

    def names(params: str) -> set[str]:
        return {d["filename"] for d in env.get(f"/api/documents?{params}").json()["items"]}

    assert names("q=REGISTER") == {"register.csv", "register.xlsx", "register_semicolon_cp1252.csv"}
    assert names("kind=csv") == {"register.csv", "register_semicolon_cp1252.csv"}
    assert names("q=semicolon&kind=csv") == {"register_semicolon_cp1252.csv"}
    assert names("q=%25") == set()  # a LIKE wildcard is matched literally
    assert names("q=r_g") == set()
    assert env.get("/api/documents?kind=word").status_code == 422


def test_spreadsheet_needs_no_model_but_a_pdf_does(env: Env) -> None:
    env.login()
    env.worker.llm = None  # like docker compose without a Gemini key
    body = env.upload("register.csv", "digital_classic_0.pdf")
    csv_doc, pdf_doc = (d["document_id"] for d in body["documents"])
    env.work()
    assert env.get(f"/api/documents/{csv_doc}").json()["status"] == "completed"
    assert len(env.get(f"/api/documents/{csv_doc}/results").json()["invoices"]) == 5
    pdf = env.get(f"/api/documents/{pdf_doc}").json()
    assert pdf["status"] == "failed"
    assert "GEMINI_API_KEY" in pdf["latest_job"]["last_error"]
    assert pdf["latest_job"]["attempts"] == 1  # missing settings are not retried


def test_activity_shows_stages_and_counts(env: Env) -> None:
    env.login()
    names = ["digital_classic_0.pdf", "planted_wrong_total.pdf", "encrypted.pdf"]
    env.fake.replies = reader_for_truths([env.truth(n) for n in names[:2]])
    env.upload(*names)
    before = env.get("/api/activity").json()
    assert {i["stage"] for i in before["active"]} == {"queued"}
    assert len(before["active"]) == 3 and before["review_count"] == 0
    assert before["active"][0]["stage_label"] == "Waiting in line"

    env.work()
    after = env.get("/api/activity").json()
    assert after["active"] == []
    by_name = {i["filename"]: i for i in after["recent"]}
    assert by_name["digital_classic_0.pdf"]["stage"] == "done"
    assert by_name["digital_classic_0.pdf"]["invoice_count"] == 1
    assert by_name["planted_wrong_total.pdf"]["needs_review"] == 1
    failed = by_name["encrypted.pdf"]
    assert (failed["stage"], failed["error_code"]) == ("failed", "ENCRYPTED_PDF")
    assert after["review_count"] == 1
    assert env.client.get("/api/activity").status_code == 401  # needs a token


def test_activity_stage_mapping() -> None:
    from app.api.routes.activity import STAGE_LABELS, STAGE_OF_EVENT

    order = ["queued", "reading", "extracting", "checking", "indexing", "done"]
    assert set(STAGE_OF_EVENT.values()) <= set(order) | {"failed"}
    assert set(STAGE_LABELS) == set(order) | {"failed"}
    assert STAGE_OF_EVENT["extract_windows"] == "extracting"


def test_export_csv_for_excel(env: Env, tmp_path: Path) -> None:
    env.login()
    env.worker.llm = None  # spreadsheets map by rule
    bad = tmp_path / "evil.csv"
    bad.write_text(
        "Invoice No,Supplier,Customer,Subtotal,Discount,Total\n"
        '=HYPERLINK("http://x"),Acme,রহিম ট্রেডার্স,"1,00,000.00",500.00,"99,500.00"\n'
    )
    env.dir = tmp_path
    env.upload("evil.csv")
    env.work()
    assert env.client.get("/api/export/invoices.csv").status_code == 401
    r = env.get("/api/export/invoices.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")  # BOM, so Excel reads UTF-8
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    head, row = rows[0], rows[1]
    got = dict(zip(head, row, strict=True))
    assert got["Invoice number"].startswith("'=")  # no formula runs in Excel
    assert got["Customer"] == "রহিম ট্রেডার্স"
    assert (got["Subtotal"], got["Discounts and charges"], got["Total"]) == (
        "100000.00", "-500.00", "99500.00"
    )  # fmt: skip
    assert got["Review status"] in {"ok", "needs_review"}
    only = env.get("/api/export/invoices.csv", params={"review_status": "reviewed"})
    assert len(list(csv.reader(io.StringIO(only.content.decode("utf-8-sig"))))) == 1
    marked = env.get("/api/export/invoices.csv", params={"document_id": [str(uuid.uuid4())]})
    assert len(list(csv.reader(io.StringIO(marked.content.decode("utf-8-sig"))))) == 1  # header
    [doc] = env.get("/api/documents").json()["items"]
    mine = env.get("/api/export/invoices.csv", params={"document_id": [doc["id"]]})
    assert len(list(csv.reader(io.StringIO(mine.content.decode("utf-8-sig"))))) == 2


def test_stats_report_outcomes_tokens_and_cost(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    env.login()
    names = ["digital_classic_0.pdf", "encrypted.pdf"]
    env.fake.replies = reader_for_truths([env.truth("digital_classic_0.pdf")])
    env.upload(*names)
    env.work()
    s = env.get("/api/stats").json()
    assert s["documents"] == {"completed": 1, "failed": 1}
    assert (s["success_rate"], s["failure_rate"]) == (0.5, 0.5)
    assert s["invoices"] and s["processing_seconds_mean"] is not None
    # The fake model answers 100 input and 20 output tokens per call.
    text = s["by_model"]["text-model"]
    assert (text["calls"], text["input_tokens"], text["output_tokens"]) == (1, 100, 20)
    assert text["cost_usd"] is None and s["cost_usd"] is None  # no listed price: no guess
    monkeypatch.setitem(PRICES_USD_PER_M, "text-model", (1.0, 2.0))
    monkeypatch.setitem(PRICES_USD_PER_M, "embed-model", (1.0, 0.0))
    s = env.get("/api/stats").json()
    embed = s["by_model"]["embed-model"]
    expected = (100 * 1.0 + 20 * 2.0 + embed["input_tokens"] * 1.0) / 1_000_000
    assert s["cost_usd"] == pytest.approx(expected)
    assert s["cost_per_completed_document_usd"] == pytest.approx(expected)


def test_original_file_and_delete(env: Env, db: Session) -> None:
    env.login()
    env.fake.replies = reader_for_truths([env.truth("digital_classic_0.pdf")])
    body = env.upload("digital_classic_0.pdf", "register.csv")
    pdf_id, csv_id = (d["document_id"] for d in body["documents"])
    assert env.delete(f"/api/documents/{pdf_id}").status_code == 409  # still queued
    env.work()

    assert env.client.get(f"/api/documents/{pdf_id}/file").status_code == 401
    pdf = env.get(f"/api/documents/{pdf_id}/file")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].startswith("inline")
    assert pdf.content == (env.dir / "digital_classic_0.pdf").read_bytes()
    sheet = env.get(f"/api/documents/{csv_id}/file")
    assert sheet.headers["content-disposition"].startswith("attachment")  # never shown inline

    doc = db.get(Document, uuid.UUID(pdf_id))
    assert doc is not None and doc.storage_path
    stored = env.storage.root / doc.storage_path
    assert stored.exists()
    assert env.delete(f"/api/documents/{pdf_id}").status_code == 204
    db.expire_all()
    assert not stored.exists()
    assert env.get(f"/api/documents/{pdf_id}").status_code == 404
    assert db.scalars(select(Invoice).where(Invoice.document_id == uuid.UUID(pdf_id))).all() == []
    assert env.get(f"/api/documents/{csv_id}").status_code == 200  # the other file stays


def test_pages_of_the_original_as_images(env: Env) -> None:
    """The web app shows the original as page images, never as an embedded PDF (D83)."""
    env.login()
    body = env.upload(
        "digital_classic_0.pdf", "scan_two_pages.tiff", "photo_upside_down.jpg", "register.csv"
    )
    pdf_id, tiff_id, photo_id, csv_id = (d["document_id"] for d in body["documents"])

    assert env.client.get(f"/api/documents/{pdf_id}/pages/1/image").status_code == 401
    page = env.get(f"/api/documents/{pdf_id}/pages/1/image")
    assert page.status_code == 200 and page.headers["content-type"] == "image/jpeg"
    assert page.content[:3] == b"\xff\xd8\xff"  # a JPEG
    with Image.open(io.BytesIO(page.content)) as img:
        assert img.mode == "RGB" and max(img.size) <= 1800

    second = env.get(f"/api/documents/{tiff_id}/pages/2/image")
    assert second.status_code == 200 and second.content[:3] == b"\xff\xd8\xff"
    assert env.get(f"/api/documents/{photo_id}/pages/1/image").status_code == 200

    assert env.get(f"/api/documents/{pdf_id}/pages/99/image").status_code == 404
    assert env.get(f"/api/documents/{tiff_id}/pages/3/image").status_code == 404
    assert env.get(f"/api/documents/{pdf_id}/pages/0/image").status_code == 422
    assert env.get(f"/api/documents/{csv_id}/pages/1/image").status_code == 404  # no pages


def test_replace_the_file_and_process_it_again(env: Env, db: Session) -> None:
    """A photo too blurred to read is retaken: same document, new file, processed again (D85)."""
    env.login()
    env.fake.replies = reader_for_truths([env.truth("digital_classic_0.pdf")])
    [first] = env.upload("digital_classic_0.pdf")["documents"]
    doc_id = first["document_id"]

    def send(name: str):  # type: ignore[no-untyped-def]
        data = (env.dir / name).read_bytes()
        return env.post(f"/api/documents/{doc_id}/replace", files={"file": (name, data)})

    assert send("register.csv").status_code == 409  # still queued
    env.work()
    doc = db.get(Document, uuid.UUID(doc_id))
    assert doc is not None and doc.storage_path
    old_file = env.storage.root / doc.storage_path
    assert old_file.exists()

    bad = send("note_renamed.pdf")  # a text file named .pdf: refused at upload
    assert bad.status_code == 422 and bad.json()["detail"].startswith("UNSUPPORTED_TYPE")
    db.expire_all()
    assert db.get(Document, uuid.UUID(doc_id)).mime_type == "application/pdf"  # unchanged

    r = send("register.csv")
    assert r.status_code == 202 and r.json()["status"] == "queued"
    db.expire_all()
    doc = db.get(Document, uuid.UUID(doc_id))
    assert doc is not None
    assert (doc.filename, doc.mime_type, doc.status.value) == ("register.csv", "text/csv", "queued")
    assert not old_file.exists()  # a different type: the old file is removed
    gone = env.get(f"/api/documents/{doc_id}/results").json()
    assert gone["invoices"] == []  # the old file's invoices leave at once
    env.work()
    detail = env.get(f"/api/documents/{doc_id}").json()
    assert detail["status"] == "completed"
    assert {"uploaded", "file_replaced"} <= {e["event"] for e in detail["history"]}
    results = env.get(f"/api/documents/{doc_id}/results").json()
    assert results["invoices"] and all(i["row_start"] for i in results["invoices"])


def test_cancel_a_queued_or_running_document(env: Env, db: Session) -> None:
    """A stuck file could not be stopped on live (D86)."""
    env.login()
    [queued] = env.upload("register.csv")["documents"]
    r = env.post(f"/api/documents/{queued['document_id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "failed"
    assert r.json()["error_code"] == "CANCELLED"
    assert env.post(f"/api/documents/{queued['document_id']}/cancel").status_code == 409
    env.work()  # nothing left to run for it
    assert env.get(f"/api/documents/{queued['document_id']}").json()["status"] == "failed"

    # Running: the person cancels while the model is reading; nothing is kept.
    [running] = env.upload("digital_classic_0.pdf")["documents"]
    reader = reader_for_truths([env.truth("digital_classic_0.pdf")])

    def cancel_midway(call: FakeCall):  # type: ignore[no-untyped-def]
        assert env.post(f"/api/documents/{running['document_id']}/cancel").status_code == 200
        return reader(call)

    env.fake.replies = cancel_midway
    env.work()
    detail = env.get(f"/api/documents/{running['document_id']}").json()
    assert (detail["status"], detail["error_code"]) == ("failed", "CANCELLED")
    assert "job_cancelled" in {e["event"] for e in detail["history"]}
    assert env.get(f"/api/documents/{running['document_id']}/results").json()["invoices"] == []
    # It can be processed again afterwards.
    env.fake.replies = reader_for_truths([env.truth("digital_classic_0.pdf")])
    assert env.post(f"/api/documents/{running['document_id']}/reprocess").status_code == 202
    env.work()
    assert env.get(f"/api/documents/{running['document_id']}").json()["status"] == "completed"
