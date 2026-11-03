# STATUS.md

Current state of DocIntel. Update this file at the end of every session. Newest entry at the top of the log.

## Now

**Phase:** 0 (Setup and a deployed skeleton). Code done. Waiting on the manual account steps and the first deploy.
**Deadline:** 8 November 2026, 03:39 Dhaka. Target submission 7 November 2026, 22:00 Dhaka.

**Done:** Backend skeleton (FastAPI, config, health endpoints, worker loop), all ten tables with the first Alembic migration, backend and frontend Dockerfiles, `docker-compose.yml`, Next.js health page, CI workflow, `render.yaml` blueprint.

**Next:**

1. Sowan merges branch `ccr-406a2a1e-uip46r` into `main`. Render and Vercel deploy from `main`.
2. Sowan does the manual steps below, then runs the Phase 0 exit test.
3. Claude Code starts Phase 1 (document ingestion).

**Manual steps for Sowan (phone, in this order):**

1. Supabase: create the project in Singapore. Database > Extensions: enable `vector`. Storage: create a private bucket `documents`. Connect > Session pooler: copy the string and change `postgresql://` to `postgresql+psycopg://`.
2. Render: New > Blueprint > this repo. Paste the values it asks for. Set `CORS_ORIGINS` to `http://localhost:3000` for now. Wait for the deploy, then copy the service URL.
3. Vercel: import the repo with Root Directory `frontend`. Add `NEXT_PUBLIC_API_BASE_URL` = the Render URL, no trailing slash. Deploy and copy the Vercel URL.
4. Render: set `CORS_ORIGINS` to the Vercel URL, no trailing slash. Render redeploys.
5. Exit test: open the Vercel URL. Within a minute it should say "API healthy, database connected".
6. GitHub: add the `GEMINI_API_KEY` Actions secret (needed in Phase 6).

`NEXT_PUBLIC_API_BASE_URL` is baked in at build time. After changing it on Vercel, redeploy.

**Blockers:** None in code. Waiting on accounts: Supabase, Render, Vercel, Gemini key.

**Open questions:**

1. Repository access at submission: invite the reviewers, or make the repo public after a full secret scan.
2. Whether a few real public invoice samples can be added to the evaluation set.
3. Local file storage: docker-compose has no Supabase Storage. Phase 1 needs a storage interface with a local-disk backend for compose and tests, and Supabase in production.
4. Confirm in the Supabase dashboard that the project runs Postgres 17. CI and compose use 17.

## Session log

### 4 Nov 2026, Phase 0 build (Claude Code)

Built the Phase 0 code. Backend: FastAPI app factory, settings from environment (secrets as `SecretStr`), `/api/health/live` and `/api/health`, worker loop with clean shutdown, SQLAlchemy models for all ten tables, hand-written migration `0001`. `start.sh` runs migrations, then the API and the worker, and exits if either dies. Frontend: Next.js 16 page that calls `/api/health` and shows healthy, degraded, unreachable and cold-start states. Added Dockerfiles, `docker-compose.yml`, `render.yaml` and the CI workflow (ruff, migrations, pytest, frontend build, gitleaks, Docker compose smoke test). Added decisions D17 to D28.

Tested in the sandbox:

1. Ruff lint and format: clean.
2. Pytest: 36 passed (24 unit, 12 integration on Postgres with pgvector). Coverage 94%.
3. Migration: upgrade, `alembic check` (no drift from the models), downgrade, upgrade again.
4. Backend container: health OK, clean stop exits 0, a killed worker stops the container, a bad database URL fails the start.
5. Full compose stack (Postgres 17, pgvector 0.8.7): migrations ran, worker started, and Chromium at phone width showed "API healthy, database connected".
6. Frontend: lint, typecheck and production build pass. Degraded and unreachable states checked in Chromium.

Not tested in the sandbox: the Tesseract install step (the sandbox blocks the Debian mirror) and gitleaks (the sandbox blocked downloading the binary). CI covers both. CI result: pending first run.

Fixed during testing: ORM relationships lacked `cascade="all, delete-orphan"`, so deleting a document failed when its invoices were loaded. A test caught it.

### 4 Nov 2026, planning (Claude chat)

Read the brief. Chose the stack and recorded the reasons in `DECISIONS.md` (D01 to D16). Wrote the phase plan. No code yet.
