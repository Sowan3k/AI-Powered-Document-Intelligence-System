# DECISIONS.md

Every design choice in DocIntel, with the reason behind it. Each entry follows the same format: the decision, the alternatives considered, why this choice, what it costs, and a one-line answer for an interview. Add new entries at the end. Do not delete old ones; mark them `Superseded by Dxx` if they change.

---

## D01: Python with FastAPI for the backend, not Node.js with NestJS

**Alternatives:** NestJS (suggested in the brief), Django.

**Why:** Every heavy part of the task lives in Python: PyMuPDF for PDFs, Tesseract bindings, OpenCV, pandas, openpyxl and the Gemini SDK. A Node.js API would still need a Python service for processing, which means two languages, two deployments and a network hop between them. FastAPI uses Pydantic, so the same models validate API input and LLM output. It also generates interactive API documentation, which reviewers can use directly. I built BahasaBot on FastAPI, so the five days went into the problem, not into learning a framework.

**Trade-off:** The brief lists NestJS and BullMQ. A reviewer who expects Node.js needs this explanation.

**In one sentence:** The processing ecosystem is Python, so one Python service is simpler and has fewer failure points than a Node.js API calling a Python worker.

---

## D02: A PostgreSQL job table as the queue, not Redis with BullMQ or Celery

**Alternatives:** Redis with Celery or RQ, BullMQ (Node.js only), a managed cloud queue.

**Why:** The free Render instance can restart at any time. A job that lives in the same database as the document survives a restart, and its state is always consistent with the data it changes. Workers claim jobs with `SELECT ... FOR UPDATE SKIP LOCKED`, so two workers never take the same job. A heartbeat column lets a new worker detect and re-queue jobs left behind by a crashed one. That same mechanism gives the brief's "failed-job reprocessing" requirement directly. It also removes one service to host, secure and monitor.

**Trade-off:** Postgres queues handle far less throughput than Redis. At thousands of documents per hour with many workers, the polling load on the database would grow. Production at that scale would move to a dedicated queue with separate worker machines. The job interface is isolated in `backend/app/worker/` so that swap stays small.

**In one sentence:** For this scale and free hosting, a durable queue in the same transactional database is more reliable than an extra in-memory service, and the design leaves a clear path to Redis when volume demands it.

---

## D03: The worker runs as a separate process in the same container

**Alternatives:** A Render background worker service (not available on the free plan), a background thread inside the API process.

**Why:** OCR is CPU-heavy. Inside the API process it would block request handling. A separate process keeps the API responsive. Render's free plan offers web services but not background workers, so `start.sh` launches both processes in one container.

**Trade-off:** API and worker share 512 MB RAM and a small CPU share, so processing is slow under load. Production would run workers on their own instances and scale them independently.

**In one sentence:** Separate processes keep the API responsive, and one container keeps it free; production would split them onto separate machines.

---

## D04: Supabase for the database and file storage

**Alternatives:** Render's free Postgres, MongoDB Atlas, Neon.

**Why:** Supabase gives PostgreSQL with pgvector and private file storage in one project. File storage matters because Render's free web services have no persistent disk, so uploaded files saved locally would vanish on restart, and failed jobs could not be reprocessed. Render's free Postgres expires after 30 days, which could fall inside the review period.

**Trade-off:** One more external provider and one more set of credentials to protect. Supabase free projects pause after a period of inactivity.

**In one sentence:** Supabase solves three needs (relational data, vectors and durable file storage) in one place, which free Render alone cannot.

---

## D05: pgvector inside PostgreSQL, not a separate vector database

**Alternatives:** Pinecone, Qdrant, Chroma.

**Why:** Semantic search here runs over thousands of invoices, not hundreds of millions of vectors. Keeping embeddings next to the invoice rows means one query can combine meaning with exact filters (supplier, date range, amount, status). It also means one backup, one access control model and no sync job between two stores.

**Trade-off:** A dedicated vector database scales further and offers more tuning. That becomes worth the extra system only at a much larger corpus.

**In one sentence:** At this scale, vectors beside the relational data give simpler filtering and consistency than a second database.

---

## D06: PostgreSQL rather than MongoDB

**Alternatives:** MongoDB (listed in the brief).

**Why:** The data is relational: a document holds invoices, an invoice holds line items, issues and corrections. Money needs exact decimal types. Duplicate detection needs unique constraints. Full-text search is built in. Flexible per-field metadata (confidence, evidence) fits in JSONB columns, so the schema stays strict where it must be and flexible where it helps.

**Trade-off:** Schema changes need migrations. Alembic handles that.

**In one sentence:** Financial data needs exact numbers, relations and constraints, which PostgreSQL provides natively.

---

## D07: Hybrid OCR: Tesseract first, Gemini vision only for low-confidence pages

**Alternatives:** Tesseract only, PaddleOCR, a vision LLM for every image.

**Why:** Tesseract is free, runs inside the container and handles clean scans well. It reports a confidence score per word, so the system knows when it struggled. Only those pages go to Gemini vision, which reads poor scans far better. PaddleOCR is more accurate than Tesseract but too heavy for a 512 MB instance.

**Trade-off:** Two OCR paths to test. Pages sent to Gemini leave the server and cost API calls. The evaluation report shows how many pages took each path.

**In one sentence:** Cheap local OCR handles most pages, and the expensive model is used only where measured confidence says it is needed.

---

## D08: Gemini as the LLM

**Alternatives:** OpenAI, Anthropic, a local model through Ollama.

**Why:** Gemini supports structured JSON output against a schema, reads images for the OCR fallback, and provides embeddings, so one provider covers extraction, vision and search. Its free tier makes development possible without a budget. I used Gemini in BahasaBot, including quota handling and token logging.

**Trade-off:** Free-tier rate limits slow the evaluation run. Documents are sent to an external provider. The client module isolates the provider, so switching models is a configuration change.

**In one sentence:** One provider covers structured extraction, vision and embeddings, behind a client module that keeps it replaceable.

---

## D09: The LLM extracts; code calculates

**Alternatives:** Ask the LLM to check the totals itself.

**Why:** Language models make arithmetic mistakes and give different answers to the same input. Financial checks must be exact and repeatable. So the model only reads values, and every sum, tax check, duplicate check and reconciliation runs in Python with `Decimal`.

**Trade-off:** More code to write than one clever prompt.

**In one sentence:** The model reads; deterministic code decides whether the numbers are right.

---

## D10: Null with confidence and evidence instead of guessed values

**Alternatives:** Let the model fill every field.

**Why:** In finance a confident wrong number does more damage than a blank. The model returns `null` when unsure, plus a confidence score and the text snippet it used. Code then checks that the invoice number and total really appear in the source text. A value without evidence is flagged for review instead of being trusted.

**Trade-off:** More invoices go to manual review. That is the intended behaviour.

**In one sentence:** Every extracted value must show where it came from, and anything unproven goes to a human.

---

## D11: Large PDFs in page batches, with windowed invoice segmentation

**Alternatives:** Load the whole PDF and send it to the model at once.

**Why:** A 1,000-page PDF does not fit in 512 MB of memory as rendered images, and it does not fit in one model call. PyMuPDF reads pages in batches. Segmentation sends overlapping windows of pages to the model, which returns invoices with page ranges. Invoices that cross a window edge are merged. Progress is reported as pages done out of the total.

**Trade-off:** Window edges need careful merge logic and tests.

**In one sentence:** Streaming pages in batches keeps memory flat, and overlapping windows keep invoices whole.

---

## D12: Spreadsheets mapped by rules first, LLM once per sheet

**Alternatives:** Send every row to the LLM.

**Why:** A spreadsheet is already structured. The only hard part is knowing which column means "total" or "supplier". Known header names are matched by rule. When a column is unclear, the LLM sees only the header row and a few sample rows, once per sheet. pandas then converts every row. A 10,000-row sheet costs one model call, not 10,000.

**Trade-off:** Unusual layouts, such as one invoice spread across several rows, need special handling.

**In one sentence:** Use the model to understand the layout once, then let pandas do the rows.

---

## D13: A synthetic labelled dataset as the core of evaluation

**Alternatives:** Public datasets only, or hand-labelling real invoices.

**Why:** A generated invoice comes with exact ground truth. It also lets me plant specific errors (wrong totals, duplicates, missing fields) to measure whether validation catches them, and to build a long multi-invoice PDF for timing. Degraded image copies test OCR on known content.

**Trade-off:** Synthetic layouts are cleaner than real ones, so results may be optimistic. The report states this, and adds real public samples where licensing and access allow.

**In one sentence:** Synthetic data gives exact answers and controlled errors; the report is honest about its limits.

---

## D14: JWT login for the web interface; the browser calls the API directly

**Alternatives:** No authentication, an API key in the frontend, routing uploads through Next.js server functions.

**Why:** Financial documents need access control even in a demo. A single demo account, configured by environment variables, issues a short-lived JWT. The browser sends files straight to the API, because serverless platforms limit request body size and would block large uploads. CORS allows only the frontend origin.

**Trade-off:** One demo account is not real user management. Production would use the company's single sign-on and per-user roles.

**In one sentence:** Real authentication at demo scale, with a clear path to single sign-on.

---

## D15: Free-tier hosting with stated limits

**Alternatives:** Paid instances.

**Why:** The project has no budget, and the free tiers are enough to show a working system.

**Trade-off:** The Render service sleeps after a period without traffic, so the first request can take close to a minute. It can also restart at any time, which D02 and D04 are designed to survive. The README and the submission email state this.

**In one sentence:** Free hosting is enough to prove the design, and the design already handles its restarts.

---

## D16: Cross-verification added beyond the seven tasks

**Alternatives:** Build only what the task list requires.

**Why:** The scenario names PDF-to-PDF and PDF-to-Excel cross-verification as daily manual work, but none of the seven tasks asks for it. A reconciliation endpoint matches invoices across two documents by invoice number, then by supplier, date and total, and reports matches, mismatched fields and missing records.

**Trade-off:** Time taken from other phases. It is scheduled after validation, so it can be cut if earlier phases run late.

**In one sentence:** It addresses a pain the company described, not only the checklist it wrote.

---

## D17: Supabase Data API disabled; the backend reaches Postgres only through SQLAlchemy

**Alternatives:** `supabase-js` in the frontend with row level security, or the Supabase table client (PostgREST) in the backend.

**Why:** Least privilege. The frontend never talks to Supabase directly (D14), so nothing needs Supabase's auto-generated REST API over the tables. With the Data API turned off, no table can be reached through Supabase's public API, even if a key leaks or a row level security policy is wrong. The backend reaches the database only with SQLAlchemy over the Session pooler string, so every query goes through the same models, transactions and ORM parameters (security rule 6). Files go through the Supabase Storage API, called only by the backend with the service role key. The private bucket `documents` (50 MB file limit) was created in the dashboard; code never creates or changes buckets. A unit test fails CI if `supabase-js`, any `@supabase/` package, or the Python `supabase` or `postgrest` packages appear in the dependencies.

**Trade-off:** No Supabase realtime, auto-generated REST endpoints or browser-side queries. Every new data need is a FastAPI endpoint, and the frontend polls the backend for progress.

**In one sentence:** One door into the database, owned by the backend; Supabase's public Data API stays closed.

---

## D18: Synchronous SQLAlchemy sessions, not async

**Alternatives:** Async SQLAlchemy with `asyncpg` or async psycopg.

**Why:** The API and the worker share the same models and database code. The worker is CPU-bound (OCR, PDF parsing), so async gives it nothing. FastAPI runs plain `def` endpoints in a thread pool, which is enough for a demo-scale API. One session style means one set of helpers and simpler tests.

**Trade-off:** Each in-flight request holds a thread. Under thousands of concurrent requests an async stack would use less memory. That load is far beyond this deployment.

**In one sentence:** The slow work is CPU-bound, so async would add complexity without adding speed.

---

## D19: Embedding size fixed by `EMBED_DIM` when the migration runs

**Alternatives:** Hard-code the dimension in the migration, or use an untyped vector column.

**Why:** Model names and their output sizes are configuration (CLAUDE.md). The first migration reads `EMBED_DIM` and creates `vector(EMBED_DIM)`. It also creates an HNSW index with cosine distance, but only when the size is 2,000 or less, because pgvector cannot index larger `vector` columns with HNSW. Gemini embedding models can return a reduced size, so 768 keeps the index possible and the rows small.

**Trade-off:** Changing `EMBED_DIM` after the first deploy needs a new migration and fresh embeddings. Stored vectors from different models cannot be mixed anyway.

**In one sentence:** The vector size follows configuration, and the index exists whenever pgvector can build it.

---

## D20: Status columns as VARCHAR with CHECK constraints, not native Postgres enums

**Alternatives:** Native `CREATE TYPE ... AS ENUM`, or free text with no constraint.

**Why:** A CHECK constraint still stops bad values at the database. Changing the allowed values is a plain constraint swap in a migration. A native enum needs `ALTER TYPE`, which has transaction limits and cannot remove a value. The Python side uses `StrEnum`, so code gets type safety too.

**Trade-off:** Slightly more storage than a native enum. Irrelevant at this scale.

**In one sentence:** Same protection as an enum, with migrations that stay simple.

---

## D21: UUID keys for rows the API exposes, BIGINT keys for child rows

**Alternatives:** UUIDs everywhere, or integers everywhere.

**Why:** Documents, invoices, jobs and reconciliations appear in URLs. Random UUIDs cannot be guessed or counted. Pages, line items, validation issues, corrections and events are always reached through a parent. A 1,000-page PDF creates 1,000 page rows, and BIGINT identity keys keep those rows and their indexes small.

**Trade-off:** Two key types to remember. The rule is short: if it has its own URL, it gets a UUID.

**In one sentence:** Unguessable IDs where users see them, compact IDs where they do not.

---

## D22: Quantity and unit price keep four decimals; amounts keep two

**Alternatives:** Two decimals for every money-like column, as the general rule in CLAUDE.md says.

**Why:** Real invoices quote unit prices like 0.125 per item or 3.3333 per hour. Rounding them to two decimals would make rule R04 (quantity times unit price equals amount) fail on correct invoices. So `quantity` and `unit_price` are `NUMERIC(14,4)`. Every amount that is actually charged (`subtotal`, `tax`, `total`, line `amount`) stays `NUMERIC(14,2)`. No column uses floats.

**Trade-off:** One exception to remember. It refines the money rule; it does not break it.

**In one sentence:** Charged amounts are exact to the cent, and rates keep the precision the supplier printed.

---

## D23: The full-text `search_vector` is filled by application code

**Alternatives:** A generated column (`GENERATED ALWAYS AS (to_tsvector(...)) STORED`), or a database trigger.

**Why:** The searchable text should include line item descriptions, which live in another table. A generated column can only read its own row. A manual correction must also refresh the search text. Doing it in Python, in the same place that saves the invoice, keeps the logic visible and testable. A GIN index makes the search fast.

**Trade-off:** Every code path that changes an invoice must refresh the vector. Phase 4 puts that in one function and tests it.

**In one sentence:** The search text spans two tables, so the code that writes them also builds it.

---

## D24: Two health endpoints: liveness without the database, readiness with it

**Alternatives:** One endpoint that always checks the database.

**Why:** Render calls the health check during every deploy. If that check needed the database, a paused Supabase project would block deploys of a working API. So `/api/health/live` only proves the process is up, and Render uses it. `/api/health` also runs `SELECT 1` and returns 503 when the database is down. The frontend calls that one to show "API healthy, database connected". Errors are logged by type only, because driver messages can contain host names.

**Trade-off:** Render can route traffic to an instance whose database is down. The frontend shows that state clearly instead of hiding it.

**In one sentence:** The platform checks that the process lives; people check that the whole system works.

---

## D25: Migrations run in `start.sh`, and the container stops if either process dies

**Alternatives:** Render's pre-deploy command (paid plans only), or running migrations by hand.

**Why:** The free plan has no pre-deploy step. `start.sh` runs `alembic upgrade head` before it starts the API and the worker, so the schema always matches the code. The script then waits on both processes. If one exits, it stops the other and exits with an error, so Render restarts the whole container instead of leaving a half-working service. A normal stop signal exits cleanly. `docker-compose.yml` uses the same script with `api` and `worker` modes.

**Trade-off:** With several instances starting together, two could race to migrate. This deployment has one instance. At scale, migrations would move to a release step.

**In one sentence:** One instance can safely migrate at start, and a half-dead container restarts as a whole.

---

## D26: Supabase Session pooler, with psycopg prepared statements turned off

**Alternatives:** Supabase's direct connection, or the transaction pooler with default driver settings.

**Why:** The direct connection uses IPv6, which Render's free services cannot reach. The Session pooler works over IPv4. psycopg 3 prepares statements after a few runs, and the transaction pooler rejects that, so the engine sets `prepare_threshold=None`. That keeps both pooler modes working. Each process keeps a small pool (three plus two overflow) to stay inside Supabase's free connection limit.

**Trade-off:** Prepared statements would save a little parsing time per query. The gain is negligible here.

**In one sentence:** Use the connection path Render can actually reach, and keep the driver compatible with any Supabase pooler mode.

---

## D27: Exact dependency pins compiled with `uv`

**Alternatives:** Loose ranges in `requirements.txt`, Poetry, or `uv` with `pyproject.toml` and a lock file.

**Why:** `requirements.in` lists the direct dependencies. `uv pip compile` turns it into `requirements.txt` with every transitive package pinned. Docker, CI and reviewers all install the same versions with plain `pip`, which every reviewer already has. The frontend pins exact versions in `package.json` and commits `package-lock.json`. The backend image is pinned to `python:3.12.16-slim-trixie`, and the database image to `pgvector/pgvector:0.8.7-pg17`.

**Trade-off:** Updates are manual. That is the point: nothing changes between the test run and the deploy.

**In one sentence:** Every environment installs exactly what CI tested.

---

## D28: CI builds the Docker images and runs the whole stack

**Alternatives:** Test only the Python and TypeScript code, and trust the Dockerfiles.

**Why:** The builder has no local machine, and the cloud sandbox blocks the Debian package mirror, so a full image build cannot run there. CI fills that gap. A `docker` job builds both images, checks that Tesseract is installed, starts `docker compose`, and confirms that the API reports a connected database, the worker started and the web app answers. If the Dockerfile breaks, CI fails before Render does. CI and compose use Postgres 17 with pgvector, to stay close to Supabase.

**Trade-off:** The CI run takes a few minutes longer.

**In one sentence:** What reviewers will run locally is tested on every push.

---

## D29: A Render Blueprint (`render.yaml`) describes the backend service

**Alternatives:** Create the service by hand in the Render dashboard.

**Why:** The builder works from a phone. The blueprint sets the Docker paths, the Singapore region, the free plan, the liveness health check and every environment variable name. Render asks for the secret values in its own dashboard, and it generates `JWT_SECRET` itself, so no secret passes through chat or Git. A build filter skips backend deploys for frontend-only changes.

**Trade-off:** Blueprint changes need a sync in Render. Manual setup still works; the file then serves as the written record of the settings.

**In one sentence:** The service settings live in Git, and the secrets never do.

---

## D30: pg_trgm for fuzzy supplier matching

**Alternatives:** Exact match on the normalised supplier name only, fuzzy matching in Python (for example rapidfuzz) over every stored invoice, or embedding similarity on supplier names.

**Why:** The same supplier appears as "Acme Traders Ltd", "ACME TRADERS LIMITED" or "Acme Tradres Ltd" (an OCR slip) on different invoices. Exact matching misses those duplicates (rules R06 and R07) and reconciliation pairs. `pg_trgm` scores how many three-letter chunks two names share. A GIN trigram index on `invoices.supplier_norm` lets the database find close names fast, without loading every invoice into Python. Embeddings measure meaning, not spelling, and cost an API call per name. The database only proposes candidates; Python with `Decimal` still decides whether numbers, dates and totals match (D09). Supabase already has the extension enabled in its `extensions` schema. The migration runs `CREATE EXTENSION IF NOT EXISTS pg_trgm`, which is a no-op there and creates it in CI and docker-compose.

**Trade-off:** The similarity threshold needs tuning on the evaluation set. Trigrams are weak on very short names, so Phase 3 normalises names (case, punctuation, suffixes like "Ltd") before comparing. Fuzzy matching becomes tied to PostgreSQL.

**In one sentence:** The database finds suppliers that look alike, and code decides whether the invoices really match.

---

## D31: Gemini models: Flash-Lite for text, Flash for vision, gemini-embedding-2 at 768 dimensions

**Alternatives:** One model for every call, a larger model for text extraction, or the embedding model's full output size.

**Why:** Sowan confirmed the names against Google's model list on 4 November 2026. They live in environment variables (`GEMINI_MODEL`, `GEMINI_VISION_MODEL`, `GEMINI_EMBED_MODEL`), never in code.

`gemini-3.5-flash-lite` does text extraction. It is the highest-volume call, one or more per page window, so it uses the cheapest and fastest tier, which matters most under free-tier rate limits. The job is reading values that are already in the text, and code checks every value afterwards (D09, D10), so a smaller model's mistakes get caught instead of trusted.

`gemini-3.8-flash` reads page images, but only when Tesseract confidence is below the threshold (D07). Those pages are few and the hardest to read, so a stronger model is worth its cost there.

`gemini-embedding-2` creates the search embeddings, called with `output_dimensionality=768` to match `EMBED_DIM` and the `vector(768)` column (D19). 768 keeps the HNSW index possible and the rows small. The index uses cosine distance, which ignores vector length, so the shortened vectors need no extra normalisation step.

This embedding model has no `task_type` parameter. The text itself says what it is, with these exact prefixes:

```
query:     task: search result | query: {query}
document:  title: {title} | text: {text}
```

Search queries and stored invoices must both use them, or the similarity scores lose meaning. The templates go in `backend/app/extract/prompts.py` with the other prompts (CLAUDE.md, AI rule 7). Phase 4 decides what the title and text of each invoice contain, and tests the format.

**Trade-off:** Flash-Lite may miss values on messy layouts. The Phase 6 evaluation reports accuracy per field. If it falls short, moving `GEMINI_MODEL` up a tier is a configuration change, not a code change. Changing the embedding model or `EMBED_DIM` means re-embedding every invoice, plus a migration for a new size (D19). The prefix format belongs to this model, so a new embedding model means checking its format first.

**In one sentence:** The cheap model does the bulk reading, the strong model handles only the hard pages, and the embeddings stay small enough to index.

