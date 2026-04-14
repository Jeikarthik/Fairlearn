# FairLens

FairLens is a full-stack fairness audit platform built to support "technical setup once, accessible insight afterward." A technical owner can connect datasets, APIs, and monitoring hooks, while later users interact with plain-language results, reports, and alerts.

## Documentation

The main project documentation is here:

- [Project Documentation](docs/PROJECT_DOCUMENTATION.md)

That document covers:

- architecture
- workflows and modes
- API surface
- frontend structure
- local setup
- environment variables
- testing
- limitations and future scope

## Quick start

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Local URLs:

- frontend: `http://127.0.0.1:5173`
- backend API: `http://127.0.0.1:8000`
- backend docs: `http://127.0.0.1:8000/docs`

## Current implementation status

Implemented:

- dataset and aggregate fairness audits
- report generation and PDF export
- mitigation CSV downloads
- history and comparison
- Mode 5 API probing
- Mode 6 adversarial language probing
- Mode 7 continuous monitoring
- React frontend connected to the FastAPI backend

Still intentionally outside the completed scope:

- deployment and production hardening
- document and screenshot upload
