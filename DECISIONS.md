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
