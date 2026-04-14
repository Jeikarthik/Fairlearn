# FairLens Project Documentation

## 1. Overview

FairLens is a full-stack fairness audit platform for AI and rules-based decision systems.

Its product direction is:

- a technical owner performs the initial setup
- later users interact with plain-language findings, reports, alerts, and recommended actions

The project currently includes:

- a FastAPI backend
- a React + Vite frontend
- dataset and aggregate fairness audits
- report generation and PDF export
- mitigation CSV downloads
- history and run comparison
- Mode 5 API probing
- Mode 6 adversarial language probing
- Mode 7 continuous monitoring

Document and screenshot upload were intentionally left out of implementation and remain future scope.

## 2. Product Goals

FairLens is designed to help teams answer questions like:

- Are approvals, selections, or model outputs materially different across protected groups?
- Which attributes or proxy features may be contributing to uneven outcomes?
- If the system is a live API or language model, does it behave differently when only demographic information changes?
- Is fairness drifting after deployment?
- What should the team do next, in simple, decision-oriented language?

The UI intentionally avoids heavy technical wording for non-technical users, while the backend still preserves the evidence needed for deeper review.

## 3. Implemented Scope

### 3.1 Core audit workflow

- Upload CSV or Excel datasets
- Profile columns and preview uploaded data
- Auto-suggest likely protected attributes
- Configure outcome, prediction, favorable value, and reference groups
- Run pre-audit data quality checks
- Run fairness audits on row-level datasets
- Run fairness audits from aggregate group counts
- Generate plain-language reports
- Download PDF reports
- Download mitigated CSV variants

### 3.2 Analysis depth

- Demographic parity difference
- Disparate impact ratio
- Equal opportunity difference
- Predictive parity difference
- Accuracy equity
- False negative rate disparity
- Wilson confidence intervals on metric estimates
- Intersectional analysis
- Proxy feature detection
- Root-cause hints with SHAP preferred when a compatible model artifact is provided
- Fairlearn-backed mitigation tradeoff simulations where the data supports them

### 3.3 Specialist modes

#### Mode 5: API Probe

Tests whether a decision API changes outcomes when only a protected attribute changes.

#### Mode 6: Language Probe

Tests matched prompts across demographic variants and surfaces plain-language findings.

#### Mode 7: Continuous Monitoring

Accepts webhook-style decision records, tracks recent fairness drift, and raises readable alerts.

### 3.4 Frontend coverage

The frontend currently includes:

- overview dashboard
- audit studio
- API probe page
- language probe page
- monitoring page
- history and comparison page

## 4. High-Level Architecture

## 4.1 Frontend

Technology:

- React 19
- React Router
- Vite

Responsibilities:

- collect setup input
- call backend APIs
- present fairness results and reports
- translate backend outputs into a guided operator workflow

Main frontend layers:

- `src/App.jsx`: app routing and backend connection state
- `src/api/client.js`: all frontend HTTP calls
- `src/components/`: reusable layout and audit UI building blocks
- `src/pages/`: mode-specific screens

## 4.2 Backend

Technology:

- FastAPI
- SQLAlchemy
- Pandas
- scikit-learn
- Fairlearn
- SHAP
- ReportLab

Responsibilities:

- receive files and structured inputs
- persist job metadata and results
- run fairness calculations
- generate reports
- support probing and monitoring workflows

Main backend layers:

- `app/api/routes/audit.py`: API routes
- `app/services/`: business logic
- `app/schemas/`: request and response models
- `app/models/`: persistence models
- `app/core/`: settings and database wiring

## 4.3 Persistence model

The backend stores work as jobs.

Each job may include:

- mode
- filename
- file path
- upload summary
- saved configuration
- run results
- status

This keeps all workflows consistent whether the job originated from:

- uploaded tabular data
- aggregate counts
- API probe setup
- language probe setup
- monitoring setup

## 5. End-to-End Workflow

## 5.1 Dataset audit

1. User uploads a CSV or Excel file.
2. Backend profiles columns and suggests likely protected attributes.
3. User configures outcome column, prediction column if available, favorable outcome, and protected attributes.
4. Optional model artifact is uploaded for root-cause analysis.
5. Quality gate runs.
6. Audit runs.
7. Frontend shows metrics, group stats, proxy warnings, intersectional findings, and root-cause hints.
8. Plain-language report is generated.
9. User may download a PDF report or mitigation CSV.

## 5.2 Aggregate audit

1. User enters group names, total counts, and favorable counts.
2. Backend creates an aggregate-mode job.
3. Audit runs immediately.
4. Frontend shows results and allows report generation.

## 5.3 Mode 5 API probe

1. Technical owner defines the API endpoint and payload schema.
2. Backend creates matched counterfactual request pairs.
3. Probe runs against live API responses or mock outcomes.
4. Frontend shows discrepancy rate, findings, and next actions.

## 5.4 Mode 6 language probe

1. Technical owner defines protected attribute groups and scenario templates.
2. Backend generates matched prompts.
3. Probe runs against live endpoint responses or mock outcomes.
4. Frontend presents plain-language insight and evidence.

## 5.5 Mode 7 monitoring

1. Technical owner configures protected attributes, prediction field, favorable outcome, and thresholds.
2. Backend returns a webhook path tied to the monitoring job.
3. Records are sent to the webhook.
4. Backend computes rolling-window fairness status.
5. Frontend shows alerts, status, and latest snapshot.

## 6. Repository Structure

```text
Fairlearn/
+-- backend/
|   +-- app/
|   |   +-- api/
|   |   +-- core/
|   |   +-- models/
|   |   +-- schemas/
|   |   `-- services/
|   +-- tests/
|   +-- pyproject.toml
|   `-- README.md
+-- frontend/
|   +-- src/
|   |   +-- api/
|   |   +-- components/
|   |   +-- pages/
|   |   `-- utils/
|   +-- package.json
|   `-- .env.example
+-- docs/
|   `-- PROJECT_DOCUMENTATION.md
+-- uploads/
+-- reports/
+-- README.md
`-- docker-compose.yml
```

## 7. Backend Design Details

## 7.1 Core services

Important backend services include:

- `file_parser.py`: file save and read helpers
- `attribute_detector.py`: protected attribute suggestion
- `quality_gate.py`: pre-audit checks
- `audit_engine.py`: fairness metrics, intersectional analysis, proxy scanning
- `explainability.py`: root-cause analysis, SHAP-first where possible
- `fairlearn_mitigation.py`: mitigation tradeoff simulations
- `reporting.py`: report and PDF generation
- `gemini_service.py`: optional Gemini-backed narrative generation with fallback
- `api_prober.py`: Mode 5 logic
- `nlp_probe.py`: Mode 6 logic
- `monitoring.py`: Mode 7 logic

## 7.2 Key API routes

### Core audit routes

- `GET /api/health`
- `POST /api/upload`
- `POST /api/aggregate`
- `POST /api/configure`
- `POST /api/model/upload`
- `POST /api/quality-check`
- `POST /api/audit/run`
- `GET /api/audit/{job_id}`
- `GET /api/jobs/{job_id}`

### Reporting and downloads

- `POST /api/report/generate`
- `GET /api/report/{job_id}/pdf`
- `GET /api/mitigate/{job_id}/download`
- `GET /api/samples`
- `GET /api/samples/{sample_id}/download`

### History

- `GET /api/history`
- `GET /api/history/compare`

### Specialist modes

- `POST /api/probe/configure`
- `POST /api/probe/run`
- `GET /api/probe/{job_id}`
- `POST /api/nlp-probe/setup`
- `POST /api/nlp-probe/run`
- `GET /api/nlp-probe/{job_id}`
- `POST /api/monitor/setup`
- `POST /api/webhook/predict/{job_id}`
- `GET /api/monitor/{job_id}`

## 7.3 Supported file types

Currently supported for upload:

- `.csv`
- `.xlsx`
- `.xls`

Currently supported for optional model upload:

- `.pkl`
- `.pickle`
- `.joblib`

## 8. Frontend Design Details

The frontend is organized around workflows rather than technical subsystems.

## 8.1 Main pages

- `DashboardPage`: product overview and navigation
- `AuditStudioPage`: main audit workspace
- `ApiProbePage`: Mode 5
- `NlpProbePage`: Mode 6
- `MonitoringPage`: Mode 7
- `HistoryPage`: history and comparisons

## 8.2 Audit UI composition

The audit workflow is split into dedicated components:

- `DatasetAuditWorkflow`
- `AggregateAuditWorkflow`
- `AuditResultsPanel`
- `ReportPanel`

This keeps the UI modular and makes the main audit page easier to maintain.

## 8.3 UI principles

- plain-language wording for non-technical users
- visual grouping by workflow
- backend state visible but not overwhelming
- readable summaries before raw evidence

## 9. Environment and Configuration

## 9.1 Backend environment variables

Key backend variables:

- `DATABASE_URL`
- `MAX_UPLOAD_SIZE_MB`
- `UPLOAD_DIR`
- `REPORTS_DIR`
- `CORS_ORIGINS`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`

Default backend behavior:

- in-memory SQLite by default
- local uploads and reports directories
- frontend allowed from `http://localhost:5173`

## 9.2 Frontend environment variables

Frontend variables:

- `VITE_API_BASE_URL`

Default:

- `http://127.0.0.1:8000/api`

## 10. Local Development Setup

## 10.1 Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Backend URLs:

- API: `http://127.0.0.1:8000`
- Swagger docs: `http://127.0.0.1:8000/docs`

## 10.2 Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Frontend URL:

- `http://127.0.0.1:5173`

## 10.3 Production build

```bash
cd frontend
npm run build
```

The generated frontend build is written to:

- `frontend/dist/`

## 11. Testing and Verification

## 11.1 Backend tests

Current backend tests cover:

- attribute detection
- quality gate behavior
- audit pipeline
- Mode 5 API probe
- Mode 6 language probe
- Mode 7 monitoring

Run:

```bash
cd backend
pytest
```

## 11.2 Frontend verification

Current frontend verification:

- production build compilation via Vite

Run:

```bash
cd frontend
npm run build
```

## 11.3 Latest verified state

At the latest working checkpoint:

- backend tests passed
- frontend build succeeded

## 12. Known Limitations

- No deployment automation or production hardening yet
- No user authentication or authorization layer
- No full browser automation or end-to-end UI test suite yet
- Gemini-backed report enrichment depends on external configuration
- Some explainability behavior falls back heuristically when SHAP cannot be used on the provided artifact
- Monitoring is rolling-window based and not a full production observability platform

## 13. Future Scope

These items are intentionally not part of the implemented scope right now:

- document upload
- screenshot upload
- deployment pipeline and production rollout hardening

## 14. Troubleshooting

## 14.1 Frontend cannot reach backend

Check:

- backend is running on `127.0.0.1:8000`
- frontend `.env` contains the correct `VITE_API_BASE_URL`
- backend `CORS_ORIGINS` allows the frontend origin

## 14.2 Sample downloads or report downloads fail

Check:

- backend is running
- the job exists and has completed the required earlier step
- uploaded files still exist in the expected local folders

## 14.3 Audit fails after upload

Check:

- configuration has been saved
- chosen columns exist in the uploaded data
- the quality gate warnings or failures are understood and addressed

## 14.4 Frontend build fails

Check:

- `npm install` completed successfully
- `node_modules` exists under `frontend/`
- the machine is using a supported recent Node version

## 15. Recommended Next Steps

If development continues, the highest-value next items are:

1. Add deployment and production hardening.
2. Add end-to-end UI tests.
3. Add authentication and role-based access.
4. Improve report branding and operational exports.
5. Expand monitoring and observability depth.
