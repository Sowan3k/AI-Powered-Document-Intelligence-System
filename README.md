# DocIntel

DocIntel reads invoices and receipts in any of the forms a finance team receives them: digital PDFs, scanned PDFs, phone photos, multi-page TIFFs, Excel workbooks and CSV exports. It extracts the invoice fields with Gemini, checks every number in plain Python, flags what a person must review, cross-checks two documents against each other, and makes everything searchable by keyword and by meaning.

**Live:** web app https://docintel-tan-two.vercel.app · API docs https://docintel-api-y25b.onrender.com/api/docs
The backend runs on a free Render instance that sleeps when idle; the first request can take up to a minute. The demo login is in the submission email.

## What it does

1. **Upload** several files at once. Each is checked by its bytes (never its name), stored privately under a random key, and queued. A bad file fails alone with a clear code (`ENCRYPTED_PDF`, `CORRUPTED_FILE`, `EMPTY_FILE`, `UNSUPPORTED_TYPE`, `TOO_LARGE`, `TOO_MANY_PAGES`); the rest of the batch goes on.
2. **Read** each file in a background worker. Digital PDF pages give their text directly. Scanned pages and images are cleaned with OpenCV and read by Tesseract, which reports a confidence per page; weak pages go to Gemini vision. Spreadsheets are read sheet by sheet, with header detection, merged cells and CSV encoding and delimiter detection.
3. **Extract** invoice number, date, supplier, customer, subtotal, tax, total, currency and line items. Gemini copies each value as printed, with a confidence and the text it came from. Code then parses dates and money and checks that the evidence really appears in the source. Missing values stay empty; nothing is guessed.
4. **Validate** with eleven rules in exact decimal arithmetic: missing fields, line sums, quantity times price, subtotal plus tax, duplicates (with fuzzy supplier names), dates, low confidence, unproven values, mixed currencies. Any error sends the invoice to the review queue.
5. **Correct** a field in the web app. The change is recorded with who made it, the rules run again, and search updates.
6. **Search** by keyword (invoice numbers, names, line items, with filters) or by meaning ("printer supplies bought in spring").
7. **Reconcile** two documents, for example a supplier statement PDF against an Excel export: matched, mismatched with the differing fields, and invoices found on one side only.

Every document keeps its processing history, and failed jobs can be retried from the web app or the API.

## Architecture

```mermaid
flowchart LR
    web[Next.js on Vercel] -- "HTTPS + JWT" --> api[FastAPI API]
    subgraph Render["Render, one container"]
        api
        worker[Worker]
    end
    api --> db[(Supabase Postgres<br/>pgvector, pg_trgm, job queue)]
    worker --> db
    api --> files[(Private storage bucket)]
    worker --> files
    worker --> gemini[Gemini: text, vision, embeddings]
```

The API never waits on slow work: it stores and queues, and the worker claims jobs from a PostgreSQL table with `FOR UPDATE SKIP LOCKED`, with heartbeats, retries with backoff and recovery of jobs left by a stopped worker. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/SCHEMA.md](docs/SCHEMA.md), [docs/SECURITY.md](docs/SECURITY.md).

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic |
| Reading | PyMuPDF, OpenCV, Tesseract, openpyxl, xlrd |
| Model | Gemini (`gemini-3.5-flash-lite` for text, `gemini-3.8-flash` for vision, `gemini-embedding-2` at 768 dimensions) |
| Data | PostgreSQL with pgvector and pg_trgm on Supabase; Supabase Storage |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Hosting and CI | Render (Docker), Vercel, GitHub Actions |

## Evaluation

The first full evaluation run with the real Gemini API is in progress; its numbers go here.

Full method and results, including the weak spots: [docs/EVALUATION.md](docs/EVALUATION.md).

## Run it locally

You need Docker with Compose v2.

```bash
docker compose up --build
```

Open http://localhost:3000 and sign in as `reviewer` with password `docintel-demo` (local only). Spreadsheets and CSV files work with no keys at all. PDFs and images need Gemini: copy `.env.example` to `.env`, fill in `GEMINI_API_KEY`, and keep the model names. Never commit `.env`. The API docs are at http://localhost:8000/api/docs.

## Environment variables

Every setting is listed with a comment in [.env.example](.env.example). The ones that matter:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection (Supabase Session pooler string on Render) |
| `STORAGE_BACKEND` | `supabase` in production, `local` for compose and tests |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Storage API; the key is a `sb_secret_` key, backend only |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_VISION_MODEL`, `GEMINI_EMBED_MODEL`, `EMBED_DIM` | The model and its configuration |
| `JWT_SECRET`, `DEMO_USERNAME`, `DEMO_PASSWORD` | The demo login |
| `CORS_ORIGINS` | The web app's origin |
| `MAX_FILE_MB`, `MAX_FILES_PER_BATCH`, `MAX_PDF_PAGES` | Upload limits |
| `OCR_CONFIDENCE_THRESHOLD`, `FIELD_CONFIDENCE_THRESHOLD`, `MONEY_TOLERANCE` | When OCR goes to vision, when a field needs review, and the arithmetic tolerance |

## Tests and evaluation

```bash
cd backend
pip install -r requirements-dev.txt
ruff check . ../eval && ruff format --check . ../eval
pytest
```

Integration tests need a throwaway Postgres with pgvector whose database name contains `test`; without it they skip:

```bash
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/docintel_test pytest
```

The frontend:

```bash
cd frontend
npm ci
npm run lint && npm run typecheck && npm run build
```

The evaluation needs a throwaway database and a Gemini key (or `--fake` to check the scoring without one):

```bash
cd backend
PYTHONPATH=.:../eval/generate python ../eval/run_eval.py --scale 2
```

CI runs ruff, 337 tests on Postgres with Tesseract, the frontend build, a gitleaks scan, and a Docker Compose test that uploads a file and finds it by search ([docs/TEST_REPORT.md](docs/TEST_REPORT.md)). Two workflows use the real Gemini key: "Gemini smoke test" and "Evaluation".

## Design decisions

All 51 decisions, each with the alternatives, the reason and the cost, are in [DECISIONS.md](DECISIONS.md). The ones that shape the system:

1. **One Python service, not a Node.js API plus a Python worker** (D01). Every heavy library is Python; one language means one deployment and no network hop.
2. **The queue is a PostgreSQL table** (D02, D45). Jobs survive a restart of the free instance, live in the same transaction as the data they change, and need no extra service.
3. **The model reads; code calculates** (D09, D36). Gemini copies printed values with evidence; Python parses them and does every sum with `Decimal`.
4. **Nothing is guessed** (D10). Missing values stay empty, and a value whose evidence is not in the source text goes to a person.
5. **Cheap OCR first, the vision model only where confidence is low** (D07, D44), with a fallback chain so a busy model never fails a document.
6. **Long PDFs in overlapping windows** (D11, D39), so invoices that cross a page edge stay whole and memory stays flat.
7. **Spreadsheets mapped by rule, the model once per sheet at most** (D12, D37).
8. **Errors block, warnings inform** (D41), so reviewers see only what makes the numbers untrustworthy.
9. **Search in one database** (D05, D47): full text and vectors beside the relational data, with one set of filters.
10. **A synthetic labelled dataset** (D13, D35, D51) gives exact ground truth and planted errors, and the same generator builds the test fixtures.

## Known limitations

- Synthetic invoices are cleaner than real ones, so the accuracy figures are likely optimistic. No real invoices were added to the dataset.
- The free Render instance sleeps and has 512 MB of memory shared by the API and the worker; large scanned files process slowly.
- `gemini-3.8-flash` (vision) was overloaded during testing; weak scans then go to the text model, which still reads them, after a delay.
- Uploading the same invoices twice on purpose, for reconciliation, triggers the duplicate rule (D50).
- One demo account, in-memory rate limits, and tokens that cannot be revoked before they expire (D46). [docs/SECURITY.md](docs/SECURITY.md) lists what production would add.
- Line items are not reconciled, only invoice-level fields (D43).

## Repository

| Path | Holds |
|---|---|
| `backend/app/ingest` | File detection, PDF, OCR, image and spreadsheet readers, upload handling |
| `backend/app/extract` | Gemini client, prompts (all in `prompts.py`), schemas, segmentation, parsing, evidence checks |
| `backend/app/validate` | Rules R01 to R11, duplicates, reconciliation |
| `backend/app/search` | Full-text and vector indexing and search |
| `backend/app/worker` | Job queue, pipeline, worker process |
| `backend/app/api` | REST API |
| `frontend/` | Next.js web app |
| `eval/` | Dataset generator, evaluation runner, Gemini smoke test |
| `docs/` | Brief, architecture, schema, security, evaluation, test report, AI usage |

How AI tools were used to build this, with the prompts: [docs/AI_USAGE.md](docs/AI_USAGE.md).
