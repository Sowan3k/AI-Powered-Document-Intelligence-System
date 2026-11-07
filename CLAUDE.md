# CLAUDE.md

This file tells Claude Code how to work in this repository. Read it at the start of every session.

## Purpose

DocIntel is an AI-powered document intelligence system. It accepts invoices, receipts, scanned PDFs, images, Excel files and CSV files. It extracts structured invoice data, validates the numbers, cross-checks documents against each other, and makes everything searchable through a REST API and a web interface.

The project is a take-home assessment for an AI Engineer role. The brief is in `docs/BRIEF.md`. Submission is due by 8 November 2026, 03:39 Dhaka time. The target is to submit on 7 November 2026 by 22:00 Dhaka time.

## How the builder works

The builder, Sowan, works from a phone only. There is no local machine. All code is written and tested in Claude Code cloud sessions, pushed to GitHub, and deployed to Render (backend) and Vercel (frontend). Keep this in mind:

1. Every session starts from a fresh clone. Anything not committed is lost. Commit at the end of every working step.
2. The cloud sandbox may block outbound calls to Gemini, Supabase and other services. Do not try to work around a blocked network call. Unit tests use mocks. Real calls run in GitHub Actions and on Render.
3. Sowan reviews from a phone screen. Keep commit messages, STATUS.md entries and summaries short and specific.

## Session routine

1. Read `CLAUDE.md`, then `PROJECT_MEMORY.md`, then `STATUS.md`, then the current phase in `PHASES.md`, then `DECISIONS.md`.
2. Work on one phase, or one clearly named part of a phase, per session.
3. Before ending, update `STATUS.md`: what was done, what was tested, what is next, any blocker.
4. Record every new design choice in `DECISIONS.md` using the existing format. Sowan must be able to defend each choice in an interview, so write the reason, the alternatives and the trade-off in plain words.
5. Log the main prompts and AI-assisted work of the session in `docs/AI_USAGE.md`.
6. Never mark a checklist item done unless its tests pass.

## Stack

| Layer | Choice |
|---|---|
| Backend API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic |
| Job queue | PostgreSQL job table with `SELECT ... FOR UPDATE SKIP LOCKED` (no Redis) |
| Worker | Separate Python process in the same container, started by `start.sh` |
| PDF text | PyMuPDF |
| OCR | Tesseract (pytesseract) after OpenCV cleanup; Gemini vision fallback for low-confidence pages |
| Spreadsheets | pandas, openpyxl (.xlsx), xlrd (.xls) |
| LLM | Gemini via the official Python SDK, structured JSON output validated by Pydantic |
| Database | Supabase PostgreSQL with pgvector, full-text search through `tsvector` |
| File storage | Supabase Storage, private bucket `documents` |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS |
| Hosting | Render web service (Docker, Singapore region), Vercel (frontend) |
| CI | GitHub Actions: ruff, pytest with a pgvector Postgres service container, gitleaks |
| Packaging | Dockerfile for the backend, `docker-compose.yml` for reviewers who run locally |

Model names are configuration, not code. Read them from `GEMINI_MODEL`, `GEMINI_VISION_MODEL` and `GEMINI_EMBED_MODEL`. Confirm the current names in Google AI Studio during setup. Read the embedding dimension from config and set the pgvector column to match it.

## Repository layout

```
backend/
  app/
    api/            FastAPI routers
    core/           config, security, logging
    db/             models, session, migrations (Alembic)
    ingest/         file type detection, PDF, OCR, spreadsheet readers
    extract/        LLM client, prompts, schemas, segmentation
    validate/       validation rules, duplicate checks, reconciliation
    search/         keyword and semantic search
    worker/         job queue, worker loop, recovery
  tests/
    unit/           no network, no database
    integration/    needs Postgres (runs in CI)
    fixtures/       small sample files, including broken ones
  start.sh
  Dockerfile
frontend/           Next.js app
eval/
  generate/         synthetic dataset generator
  data/             labelled dataset (ground truth JSON beside each file)
  run_eval.py
  reports/
docs/
  BRIEF.md  ARCHITECTURE.md  SCHEMA.md  EVALUATION.md  AI_USAGE.md  SECURITY.md
.github/workflows/
docker-compose.yml
.env.example
```

## Data model (draft, refine in Phase 0)

| Table | Holds |
|---|---|
| `documents` | file name, MIME type, SHA-256, size, storage path, page count, source kind, status, timestamps |
| `pages` | document id, page number, text, method (`digital`, `ocr`, `vision`), OCR confidence |
| `sheets` | document id, sheet name, header row, column mapping, row count |
| `invoices` | document id, page range or sheet rows, the nine extracted fields, per-field confidence and evidence (JSONB), review status, `tsvector`, embedding |
| `line_items` | invoice id, description, quantity, unit price, amount |
| `validation_issues` | invoice id, rule code, severity, message, resolved flag |
| `corrections` | invoice id, field, old value, new value, user, timestamp |
| `jobs` | document id, job type, status, attempts, max attempts, run after, locked at, heartbeat, last error |
| `processing_events` | document id, job id, event, detail, timestamp (the processing history) |
| `reconciliations` | source document A, source document B, result JSON, timestamp |

Store money as `NUMERIC(14,2)` in the database and `Decimal` in Python. Never use floats for money.

## Rules for the AI parts

1. The LLM only reads and extracts. It never does arithmetic that the system relies on. All sums, tax checks, duplicate checks and reconciliation run in plain Python with `Decimal`.
2. The LLM must return `null` when a value is missing or unclear. It must never guess. Every field carries a confidence score and a short evidence snippet from the source text.
3. After extraction, code checks that the evidence for the invoice number and total actually appears in the source text. If it does not, the field is flagged for review.
4. Every LLM response is validated against a Pydantic schema. Invalid output is retried once with the validation error, then marked failed.
5. All LLM calls go through one client module that handles rate limiting (a semaphore), retries with backoff on 429 and 5xx errors, timeouts, and token logging per call.
6. Document text is untrusted input. Wrap it in clear delimiters in the prompt, tell the model to treat it as data, and give the model no tools.
7. Keep every prompt in `backend/app/extract/prompts.py` so the prompts are easy to show in the AI disclosure.

## Security rules (non-negotiable)

1. Never write a real secret into any file, commit, log, test, or chat message. Secrets live only in Render, Vercel and GitHub Actions environment settings.
2. `.env` is in `.gitignore`. `.env.example` holds placeholder names only.
3. If a secret is ever committed, stop and tell Sowan to rotate it. Deleting the file does not remove it from Git history.
4. The Supabase service role key is used only by the backend. The frontend never talks to Supabase directly. The storage bucket is private.
5. Validate uploads by magic bytes, not by extension. Enforce size and page limits from config. Store files under UUID keys, never under user-supplied names.
6. Use ORM parameters for all SQL. No string-built queries.
7. Restrict CORS to the frontend origin. Rate-limit login and upload endpoints.
8. Logs record IDs, statuses and timings. They never record raw document text or extracted personal data.
9. Pin dependency versions. Run gitleaks in CI.

## Coding rules

1. Type hints everywhere. Pydantic models at every boundary.
2. Each file type reader returns the same internal structure, so later stages do not care where the text came from.
3. Fail one file, not the batch. A broken file gets status `failed` with a clear error code and the rest of the batch continues.
4. Process large PDFs page by page in batches. Never hold a full 1,000-page document in memory. The Render free instance has 512 MB RAM.
5. Unit tests never call the network. Use the fake LLM client in `tests/conftest.py`.
6. Write docs in plain language: short sentences, active voice, no em dashes.

## Definition of done for a phase

The phase checklist in `PHASES.md` is complete, its tests pass in CI, `STATUS.md` is updated, new decisions are in `DECISIONS.md`, and the work is committed and pushed.
