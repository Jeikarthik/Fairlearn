# FairLens

FairLens is an AI bias audit platform for running fairness checks on uploaded datasets, configuring protected attributes, and generating compliance-ready analysis. The product direction is now "technical setup once, accessible insight afterward": an engineer can connect uploads, probes, and monitoring hooks, while later users mainly consume plain-language fairness updates.

## Current status

- `backend/` contains a FastAPI service with:
  - `POST /api/upload` for CSV and Excel ingestion
  - `POST /api/configure` for saving audit configuration
  - `POST /api/model/upload` for optional model artifact attachment and root-cause hints
  - `POST /api/quality-check` for pre-audit validation
  - `POST /api/probe/configure` and `POST /api/probe/run` for Mode 5 API probing
  - `POST /api/nlp-probe/setup` and `POST /api/nlp-probe/run` for adversarial NLP probing
  - `POST /api/monitor/setup` and `POST /api/webhook/predict/{job_id}` for continuous monitoring
  - `POST /api/audit/run`, `GET /api/audit/{job_id}`, `POST /api/report/generate`, `GET /api/report/{job_id}/pdf`
  - `GET /api/samples`, `GET /api/history`, `GET /api/history/compare`, and `GET /api/mitigate/{job_id}/download`
  - `GET /api/health` and `GET /api/jobs/{job_id}` helper endpoints
- Auto-suggested protected attributes based on column names, value patterns, and low-cardinality categorical data
- Core backend audit engine for dataset mode and aggregate mode, plus mitigation export and PDF report generation
- Optional model-based root-cause analysis included in audit results, with SHAP preferred when a compatible artifact is uploaded
- Fairlearn-backed mitigation tradeoff options are included in mitigation cards when the uploaded data supports simulation
- Plain-language findings for Mode 6 adversarial NLP probing and Mode 7 fairness drift monitoring
- `frontend/` contains a React + Vite application with:
  - an overview dashboard and API connection status
  - a complete audit studio for dataset and aggregate workflows
  - Mode 5 API probing, Mode 6 language probing, and Mode 7 monitoring screens
  - audit history and comparison views
  - sample dataset download actions, report PDF download, and mitigation CSV download
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

In a second terminal:

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

The frontend will start on `http://127.0.0.1:5173`.

By default the backend uses an in-memory SQLite database so it can run without extra setup. Set `DATABASE_URL` from `.env.example` if you want persistent local storage or PostgreSQL-backed jobs.
If `GEMINI_API_KEY` is set, report generation will try a Gemini-backed plain-language narrative and cache the response locally; otherwise it falls back to the built-in report generator.

## Test

```bash
cd backend
pytest
```

## Next build targets

- deployment and production hardening
- keep document/screenshot upload in future scope only
