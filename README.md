# DocIntel

DocIntel reads invoices and receipts in any of the forms a finance team receives them: digital PDFs, scanned PDFs, phone photos, multi-page TIFFs, Excel workbooks and CSV exports. It extracts the invoice fields with Gemini, checks every number in plain Python, flags what a person must review, cross-checks two documents against each other, and makes everything searchable by keyword and by meaning.

**Live:** web app https://docintel-tan-two.vercel.app · API docs https://docintel-api-y25b.onrender.com/api/docs
The backend runs on a free Render instance that sleeps when idle; the first request can take up to a minute. The demo login is in the submission email.

## What it does

The web app is built for the shortest path: one Home screen where you drop files, watch each one move through Upload, Read, AI extract, Check and Done, and approve or fix whatever needs a look with one tap. The live processing view follows you to every screen.

1. **Upload** several files at once. Each is checked by its bytes (never its name), stored privately under a random key, and queued. A bad file fails alone with a clear code (`ENCRYPTED_PDF`, `CORRUPTED_FILE`, `EMPTY_FILE`, `UNSUPPORTED_TYPE`, `TOO_LARGE`, `TOO_MANY_PAGES`); the rest of the batch goes on.
2. **Read** each file in a background worker. Digital PDF pages give their text directly. Scanned pages and images are cleaned with OpenCV and read by Tesseract, which reports a confidence per page; weak pages go to Gemini vision. Spreadsheets are read sheet by sheet, with header detection, merged cells and CSV encoding and delimiter detection.
3. **Extract** invoice number, date, supplier, customer, subtotal, tax, total, currency and line items, plus any discount, delivery or service charge printed before the total. Gemini copies each value as printed, with a confidence and the text it came from. Code then parses dates and money (including Bangladeshi forms such as "Tk 1,25,000/-" and Bengali digits) and checks that the evidence really appears in the source. Missing values stay empty; nothing is guessed. A file that is not an invoice, such as a letter or a staff list, gives no invoice and says "No invoice found".
4. **Validate** with eleven rules in exact decimal arithmetic: missing fields, line sums, quantity times price, subtotal plus tax plus discounts and charges, duplicates (with fuzzy supplier names), dates, low confidence, unproven values, mixed currencies. Any error sends the invoice to the review queue.
5. **Correct** a field in the web app. The change is recorded with who made it, the rules run again, and search updates.
6. **Search** by keyword (invoice numbers, names, line items, with filters) or by meaning ("printer supplies bought in spring").
7. **Reconcile** two documents, for example a supplier statement PDF against an Excel export: matched, mismatched with the differing fields, and invoices found on one side only.
8. **Export** every invoice as a CSV that opens in Excel (Bengali text included), ready to enter into an accounting system.
9. **Watch the numbers**: `GET /api/stats` (and a line on Home) gives the success and failure rate, average processing time, tokens used and what they would cost on paid Gemini.

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

From evaluation run 4 with the real Gemini models, on 36 synthetic files holding 87 labelled invoices: **all 8 fields 100% correct on 87 of 87 invoices**, line items 211 of 211, every planted validation error caught (10 of 10) with 1 false flag in 77 clean invoices, all 9 broken files rejected with the right code, and no failed documents. About 2,780 tokens per document. The data is synthetic and cleaner than real invoices, so real accuracy will be lower; the weak spots are listed in the report.

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

CI runs ruff, 351 tests on Postgres with Tesseract, the frontend build, a gitleaks scan, and a Docker Compose test that uploads a file and finds it by search ([docs/TEST_REPORT.md](docs/TEST_REPORT.md)). Two workflows use the real Gemini key: "Gemini smoke test" and "Evaluation".

## Design decisions

All 62 decisions, each with the alternatives, the reason and the cost, are in [DECISIONS.md](DECISIONS.md). The ones that shape the system:

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
11. **Fast and resilient model calls** (D53, D61, D62): page windows run in parallel under a per-minute limiter, a failed window tries a second model, and every call's tokens, thinking included, are counted and priced.
12. **Built for Bangladeshi documents** (D56, D57, D58): lakh grouping and Bengali digits parse, discounts and charges count in the total check, and files that are not invoices produce nothing.

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
