# FairLens

FairLens is an AI bias audit platform for running fairness checks on uploaded datasets, configuring protected attributes, and generating compliance-ready analysis. The repository started as a spec-only plan; the current implementation now includes the backend foundation for file upload, protected-attribute suggestions, job persistence, and a pre-audit data quality gate.

## Current status

- `backend/` contains a FastAPI service with:
  - `POST /api/upload` for CSV and Excel ingestion
  - `POST /api/configure` for saving audit configuration
  - `POST /api/quality-check` for pre-audit validation
  - `GET /api/health` and `GET /api/jobs/{job_id}` helper endpoints
- Auto-suggested protected attributes based on column names, value patterns, and low-cardinality categorical data
- Categorical normalization and data quality checks for:
  - minimum dataset size
  - missing values
  - single-value columns
  - continuous protected attributes
  - ground-truth reliability warnings
  - outcome imbalance
  - configuration conflicts

## Run locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

The API will start on `http://127.0.0.1:8000` and the interactive docs will be available at `/docs`.

By default the backend uses an in-memory SQLite database so it can run without extra setup. Set `DATABASE_URL` from `.env.example` if you want persistent local storage or PostgreSQL-backed jobs.

## Test

```bash
cd backend
pytest
```

## Next build targets

- implement the fairness metric engine and audit execution endpoints
- add aggregate-mode and mitigation downloads
- add Gemini-backed narrative reporting with post-validation
- build the React frontend described in the implementation plan
