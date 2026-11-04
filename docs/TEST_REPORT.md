# Test report

From CI run 21 on 4 November 2026 (commit `9a203f2`, Phase 5), [GitHub Actions run 41830875332](https://github.com/Sowan3k/AI-Powered-Document-Intelligence-System/actions/runs/41830875332). Every push runs the same four jobs. The JUnit XML and coverage XML of each run are kept as the `backend-test-reports` artifact for 30 days.

## Result

| Job | Result | What it checks |
|---|---|---|
| Backend | passed | ruff lint and format, Alembic migrations, `alembic check` (models match the migration), 337 pytest tests on Postgres 17 with pgvector, Tesseract required |
| Frontend | passed | ESLint, TypeScript, Next.js production build |
| Secret scan | passed | gitleaks over the full Git history |
| Docker | passed | Both images build, Tesseract and the ingestion libraries load in the backend image, the compose stack starts, the API reports a connected database, a CSV uploaded through the API is processed by the worker and found by search, the web app answers |

**337 tests passed, 0 failed, 0 skipped, in 38 seconds. Line coverage 95%** (3,351 statements, 154 not run).

## Coverage by area

| Area | Coverage | Tested through |
|---|---|---|
| `app/api` | 85 to 100% per module | Every endpoint, auth failures, rate limits, upload limits |
| `app/ingest` | 84 to 100% | Every reader, every failure code, the 32-file manifest |
| `app/extract` | 96 to 100% | Fake model: valid and invalid replies, windows, evidence, parsing, vision fallback |
| `app/validate` | 93 to 98% | Every rule with planted errors, duplicates with pg_trgm, reconciliation |
| `app/search` | 100% | Full text in two forms, filters, semantic order |
| `app/worker` | 75 to 100% | Queue with SKIP LOCKED, backoff, stale recovery; the worker's process entry point (`main()`) is covered by the Docker job, not by pytest |
| `app/storage` | 92 to 100% | Local disk, and Supabase over a fake transport |

## What the tests cannot cover

- The live Gemini API. The manual "Gemini smoke test" and "Evaluation" workflows cover it with the real key. Smoke run 2 got 48 of 48 fields right.
- The live Supabase Storage API (tested against a fake transport).
- Render and Vercel themselves; those are checked by the exit tests after each deploy.

The errors in the Postgres service log of a passing run (a status check constraint, a duplicate page number) come from tests that check the database refuses bad data.
