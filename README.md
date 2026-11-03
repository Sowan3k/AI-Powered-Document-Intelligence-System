# DocIntel

AI-powered document intelligence. DocIntel reads invoices, receipts, scanned PDFs, images, Excel and CSV files. It extracts structured invoice data, validates the numbers in plain Python, cross-checks documents against each other, and makes the results searchable through a REST API and a web app.

This project is under active development. The full README, with live links and the evaluation results, comes in Phase 7. The build plan is in `PHASES.md`, the current state in `STATUS.md`, and the design choices in `DECISIONS.md`.

## Run it locally

You need Docker with Compose v2.

```bash
docker compose up --build
```

Then open the web app at http://localhost:3000 and the API docs at http://localhost:8000/api/docs. The stack has four services: Postgres with pgvector, the API, the background worker and the web app. To use the Gemini features later, copy `.env.example` to `.env` and fill in the Gemini values. Never commit `.env`.

## Run the tests

Backend (Python 3.12):

```bash
cd backend
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
pytest                      # unit tests; integration tests skip without a database
```

Integration tests need a throwaway Postgres database with pgvector, whose name contains `test`:

```bash
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/docintel_test pytest
```

Frontend (Node 22):

```bash
cd frontend
npm ci
npm run lint && npm run typecheck && npm run build
```

CI runs all of the above, a gitleaks secret scan, and a Docker Compose smoke test on every push.

## Layout

| Path | Holds |
|---|---|
| `backend/` | FastAPI API, worker, SQLAlchemy models, Alembic migrations, tests |
| `frontend/` | Next.js web app |
| `docs/` | Brief, AI usage disclosure, and later the architecture, schema and evaluation reports |
| `render.yaml` | Render Blueprint for the backend service |
| `docker-compose.yml` | The full local stack |
