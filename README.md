# FairLens

FairLens is a full-stack AI bias audit and mitigation platform built to support "technical setup once, accessible insight afterward." A technical owner connects datasets, APIs, and monitoring hooks, while all subsequent users interact with plain-language results, reports, and alerts.

## Documentation

The main project documentation is here:

- [Project Documentation](docs/PROJECT_DOCUMENTATION.md)

That document covers:

- architecture and system design
- all workflows and modes
- complete API reference
- authentication and RBAC
- PII scrubbing pipeline
- background task execution
- frontend design system
- local and Docker setup
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
- swagger docs: `http://127.0.0.1:8000/api/docs`

## Current implementation status

### Core Platform

- Dataset and aggregate fairness audits
- Report generation and PDF export
- Mitigation CSV downloads
- History and comparison
- Mode 5 API probing
- Mode 6 adversarial language probing
- Mode 7 continuous monitoring
- React frontend connected to the FastAPI backend

### Production Hardening

- JWT authentication with access + refresh tokens
- Role-based access control (admin, auditor, viewer)
- Automatic PII scrubbing on upload (emails, phones, SSNs, credit cards, IPs, Aadhaar, PAN cards)
- Background task execution (Celery + Redis or FastAPI BackgroundTasks)
- Job status state machine with enforced transitions
- Rate limiting (in-memory token bucket)
- In-process event bus for decoupled workflows
- Structured JSON logging
- Health and readiness probes
- Versioned API (`/api/v1/`)

### India Localization

- Aadhaar number detection and redaction (`[AADHAAR_REDACTED]`)
- PAN card detection and redaction (`[PAN_REDACTED]`)
- RBI Digital Lending Guidelines compliance report template
- DPDP Act 2023 data minimisation references
- Sample datasets with Indian demographic attributes (caste, region, income bracket)

### Regulatory Compliance Exports

- 🇮🇳 RBI Digital Lending Guidelines (for Indian NBFCs and fintechs)
- 🇪🇺 EU AI Act Article 13 (for high-risk AI in Europe)
- 🇺🇸 NYC Local Law 144 (for automated employment tools)
- 🇺🇸 ECOA Adverse Action (for US credit denial notices)
- One-click JSON download from the frontend Report Panel

### Python SDK & Jupyter Tutorial

- Full Python SDK (`sdk/fairlens_client.py`) for programmatic access
- Jupyter Notebook tutorial (`notebooks/SDK_Tutorial.ipynb`) with Indian lending dataset
- CI/CD fairness gate pattern for automated pipeline integration

### Frontend Auth & UX

- Login and registration page (glassmorphic design)
- Auth context with automatic token management
- Live job polling with animated status indicator
- User identity pill in sidebar with logout
- Responsive design (desktop → mobile)

### Intentionally out of scope

- Document and screenshot upload
- End-to-end browser test suite
- SSO / OAuth2 provider integration

