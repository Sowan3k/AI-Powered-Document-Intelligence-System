# Test report

From CI run 84 on 5 November 2026 (commit `3c78986`, after D71 to D82), [GitHub Actions run 42113562037](https://github.com/Sowan3k/AI-Powered-Document-Intelligence-System/actions/runs/42113562037). Every push runs the same four jobs. The JUnit XML and coverage XML of each run are kept as the `backend-test-reports` artifact for 30 days.

## Result

| Job | Result | What it checks |
|---|---|---|
| Backend | passed | ruff lint and format, Alembic migrations, `alembic check` (models match the migration), 428 pytest tests on Postgres 17 with pgvector, Tesseract required |
| Frontend | passed | ESLint, TypeScript, Next.js production build |
| Secret scan | passed | gitleaks over the full Git history |
| Docker | passed | Both images build, Tesseract and the ingestion libraries load in the backend image, the compose stack starts, the API reports a connected database, a CSV uploaded through the API is processed by the worker and found by search, the web app answers |

**428 tests passed in 82 s, 0 failed, 0 skipped. Line coverage 96%** (4,011 statements, 175 not run; measured on the same code).

## Coverage by area

| Area | Coverage | Tested through |
|---|---|---|
| `app/api` | 85 to 100% per module | Every endpoint, auth failures, rate limits, upload limits, the CSV export (BOM, formula-injection guard, Bengali text) and the stats endpoint (rates, tokens, priced and unpriced models) |
| `app/ingest` | 84 to 100% | Every reader, every failure code, the 41-file manifest, damaged and repaired PDFs |
| `app/extract` | 95 to 100% | Fake model: valid and invalid replies, windows at several sizes over a 37-page statement, parallel windows merged in page order, the fallback model, evidence, parsing (including lakh grouping, Bengali digits and "/-"), discounts and charges, sheets that are not invoices, vision fallback, phone photos always sent to vision and turned upright first (D82), thinking tokens; the real SDK on a fake transport for embeddings |
| `app/validate` | 93 to 100% | Every rule with planted errors, duplicates with pg_trgm, reconciliation |
| `app/search` | 100% | Full text in two forms, filters, semantic order |
| `app/worker` | 76 to 100% | Queue with SKIP LOCKED, backoff, stale recovery; the worker's process entry point (`main()`) is covered by the Docker job, not by pytest |
| `app/storage` | 92 to 100% | Local disk, and Supabase over a fake transport |

## What the tests cannot cover

- The live Gemini API. The "Gemini smoke test" and "Evaluation" workflows cover it with the real key; evaluation runs 5 to 8 are in `docs/EVALUATION.md`.
- The live Supabase Storage API (tested against a fake transport).
- Render and Vercel themselves; those are checked by the exit tests after each deploy.

The errors in the Postgres service log of a passing run (a status check constraint, a duplicate page number) come from tests that check the database refuses bad data.
