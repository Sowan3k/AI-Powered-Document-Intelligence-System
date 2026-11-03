# STATUS.md

Current state of DocIntel. Update this file at the end of every session. Newest entry at the top of the log.

## Now

**Phase:** 0 (Setup and a deployed skeleton). Code done. Waiting on the manual account steps and the first deploy.
**Deadline:** 8 November 2026, 03:39 Dhaka. Target submission 7 November 2026, 22:00 Dhaka.

**Done:** Backend skeleton (FastAPI, config, health endpoints, worker loop), all ten tables with the first Alembic migration, backend and frontend Dockerfiles, `docker-compose.yml`, Next.js health page, CI workflow, `render.yaml` blueprint.

**Supabase (set up by Sowan):** project created, `vector` and `pg_trgm` enabled in the `extensions` schema (on the search_path), private bucket `documents` with a 50 MB limit, Data API disabled. The backend uses SQLAlchemy over the pooler for the database and the Storage API only for files (D17). Code never creates buckets.

**Gemini models (confirmed by Sowan, 4 Nov):** `gemini-3.5-flash-lite` for text, `gemini-3.8-flash` for vision, `gemini-embedding-2` with `output_dimensionality=768`. The embedding model has no `task_type`: queries use the prefix `task: search result | query: ` and documents use `title: {title} | text: ` (D31). Phase 2 and Phase 4 must follow this.

**Next:**

1. Sowan merges branch `ccr-406a2a1e-uip46r` into `main`. Render and Vercel deploy from `main`.
2. Sowan does the manual steps below, then runs the Phase 0 exit test.
3. Claude Code starts Phase 1 (document ingestion).

**Manual steps for Sowan (phone, in this order):**

1. Supabase: done, except one step. Connect > Session pooler: copy the string and change `postgresql://` to `postgresql+psycopg://`. That is the `DATABASE_URL` for Render.
2. Render: New > Blueprint > this repo. Paste the values it asks for (the model names are already filled in). Set `CORS_ORIGINS` to `http://localhost:3000` for now. Wait for the deploy, then copy the service URL.
3. Vercel: import the repo with Root Directory `frontend`. Add `NEXT_PUBLIC_API_BASE_URL` = the Render URL, no trailing slash. Deploy and copy the Vercel URL.
4. Render: set `CORS_ORIGINS` to the Vercel URL, no trailing slash. Render redeploys.
5. Exit test: open the Vercel URL. Within a minute it should say "API healthy, database connected".
6. GitHub: add the `GEMINI_API_KEY` Actions secret (needed in Phase 6).

`NEXT_PUBLIC_API_BASE_URL` is baked in at build time. After changing it on Vercel, redeploy.

**Blockers:** None in code. Waiting on accounts: Render, Vercel, Gemini key.

**Open questions:**

1. Repository access at submission: invite the reviewers, or make the repo public after a full secret scan.
2. Whether a few real public invoice samples can be added to the evaluation set.
3. Local file storage: docker-compose has no Supabase Storage. Phase 1 needs a storage interface with a local-disk backend for compose and tests, and Supabase in production.
4. Confirm in the Supabase dashboard that the project runs Postgres 17. CI and compose use 17.

## Session log

### 4 Nov 2026, Gemini model config (Claude Code)

Set the confirmed model names in `.env.example` and `render.yaml` (model names are not secrets, so Render no longer asks for them). Recorded D31: Flash-Lite for text extraction, Flash for the vision fallback, `gemini-embedding-2` at 768 dimensions, and the exact query and document prefixes. Tested: unit tests pass, including the check that `.env.example` parses and documents every setting.

### 4 Nov 2026, Supabase rules and pg_trgm (Claude Code)

Recorded Sowan's Supabase setup. Added D17: the Data API is disabled, the backend reaches Postgres only through SQLAlchemy and files only through the Storage API, never `supabase-js` or the table client. The earlier D17 to D28 moved to D18 to D29, and all references in code and docs moved with them. Added D30: `pg_trgm` for fuzzy supplier matching. Migration `0001` (never applied to Supabase yet, since `main` does not contain it) now also runs `CREATE EXTENSION IF NOT EXISTS pg_trgm` and adds a GIN trigram index on `invoices.supplier_norm`. A new unit test fails CI if any Supabase client package appears in the backend or frontend dependencies.

Tested: ruff clean, 40 tests pass (26 unit, 14 integration), including a trigram similarity query and a run where both extensions already exist. Also ran the migration on a local copy of the Supabase layout (extensions in an `extensions` schema on the search_path): it ran, left the extensions where they were, and `alembic check` found no drift.

### 4 Nov 2026, Phase 0 build (Claude Code)

Built the Phase 0 code. Backend: FastAPI app factory, settings from environment (secrets as `SecretStr`), `/api/health/live` and `/api/health`, worker loop with clean shutdown, SQLAlchemy models for all ten tables, hand-written migration `0001`. `start.sh` runs migrations, then the API and the worker, and exits if either dies. Frontend: Next.js 16 page that calls `/api/health` and shows healthy, degraded, unreachable and cold-start states. Added Dockerfiles, `docker-compose.yml`, `render.yaml` and the CI workflow (ruff, migrations, pytest, frontend build, gitleaks, Docker compose smoke test). Added decisions D18 to D29.

Tested in the sandbox:

1. Ruff lint and format: clean.
2. Pytest: 36 passed (24 unit, 12 integration on Postgres with pgvector). Coverage 94%.
3. Migration: upgrade, `alembic check` (no drift from the models), downgrade, upgrade again.
4. Backend container: health OK, clean stop exits 0, a killed worker stops the container, a bad database URL fails the start.
5. Full compose stack (Postgres 17, pgvector 0.8.7): migrations ran, worker started, and Chromium at phone width showed "API healthy, database connected".
6. Frontend: lint, typecheck and production build pass. Degraded and unreachable states checked in Chromium.

Not tested in the sandbox: the Tesseract install step (the sandbox blocks the Debian mirror) and gitleaks (the sandbox blocked downloading the binary). CI covers both.

CI run 1 on commit `0b3bdb3`: all four jobs passed. Backend (ruff, migrations, `alembic check`, 36 tests), frontend (lint, typecheck, build), gitleaks over the full history, and the Docker job (both images built, Tesseract present, compose stack healthy, worker started, web app answering). The seven Claude Code items in the Phase 0 checklist are ticked. The six manual items and the exit test remain.

Fixed during testing: ORM relationships lacked `cascade="all, delete-orphan"`, so deleting a document failed when its invoices were loaded. A test caught it.

### 4 Nov 2026, planning (Claude chat)

Read the brief. Chose the stack and recorded the reasons in `DECISIONS.md` (D01 to D16). Wrote the phase plan. No code yet.
