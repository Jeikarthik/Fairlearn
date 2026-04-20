# FairLens — Project Documentation

## 1. Overview

FairLens is a full-stack AI bias audit and mitigation platform. It allows organizations to audit decision systems — whether powered by machine learning models, rules engines, or third-party APIs — for fairness across protected demographic attributes.

Its core product principle is **"technical setup once, accessible insight afterward"**:

1. A technical owner performs the initial integration — uploading data, connecting APIs, or wiring monitoring hooks.
2. Every subsequent user — compliance officers, HR reviewers, product managers — interacts with plain-language findings, ranked alerts, downloadable reports, and actionable next steps.

The platform currently ships as a FastAPI backend + React/Vite frontend, containerized via Docker Compose, with optional Celery + Redis for background task execution.

---

## 2. Product Goals

FairLens is designed to help teams answer:

- Are approvals, selections, or model outputs materially different across protected groups?
- Which attributes or proxy features may be contributing to uneven outcomes?
- If the system is a live API or language model, does it behave differently when only demographic information changes?
- Is fairness drifting after deployment?
- What should the team do next, in simple, decision-oriented language?

The UI avoids heavy statistical wording for non-technical users, while the backend preserves the full statistical evidence for deeper review.

---

## 3. Implemented Scope

### 3.1 Core Audit Workflow

- Upload CSV or Excel datasets
- Profile columns, preview data, and auto-suggest likely protected attributes
- Configure outcome column, prediction column, favorable value, and reference groups
- Continuous binning for numeric protected attributes (quartile, decile, custom)
- Run pre-audit data quality checks with pass/warn/fail gates
- Run fairness audits on row-level datasets
- Run fairness audits from aggregate group counts (no raw data required)
- Generate plain-language reports via Gemini AI with deterministic fallback
- Download PDF audit reports
- Download mitigated CSV variants (reweighing, threshold-shifting)

### 3.2 Analysis Depth

- **Demographic parity difference** — approval rate gap between groups
- **Disparate impact ratio** — 4/5ths rule assessment
- **Equal opportunity difference** — true positive rate gap
- **Predictive parity difference** — positive predictive value gap
- **Accuracy equity** — accuracy gap between groups
- **False negative rate disparity** — missed-positive gap
- **Wilson confidence intervals** — statistical uncertainty on metric estimates
- **Intersectional analysis** — combined attribute interactions
- **Proxy feature detection** — columns correlated with protected attributes
- **Causal analysis** — causal pathway estimation for bias attribution
- **Counterfactual fairness** — outcome sensitivity to attribute changes
- **Calibration fairness** — predicted probability calibration across groups
- **Individual fairness** — consistency of similar individuals
- **SHAP root-cause analysis** — feature importance when model artifact is available
- **Fairlearn cross-check** — independent verification via Fairlearn library
- **Fairlearn mitigation tradeoffs** — simulated reweighing/threshold impact

### 3.3 Specialist Modes

#### Mode 5: API Probe

Tests whether a decision API changes outcomes when only a protected attribute changes. The technical owner defines the API endpoint and payload schema; FairLens generates matched counterfactual request pairs and surfaces discrepancy findings.

#### Mode 6: Adversarial Language Probe

Tests matched prompts across demographic variants and surfaces plain-language findings about differential treatment in language model outputs.

#### Mode 7: Continuous Monitoring

Accepts webhook-style decision records in real-time, computes rolling-window fairness metrics, tracks drift, and raises readable alerts when fairness thresholds are breached.

### 3.4 Production Infrastructure

- **Authentication & RBAC** — JWT-based auth with roles (admin, auditor, viewer) and fine-grained permissions
- **PII scrubbing** — automatic regex-based detection and redaction of emails, phones, SSNs, credit cards, and IP addresses before any data is stored
- **Background task execution** — Celery + Redis for production, FastAPI BackgroundTasks for dev
- **Job state machine** — enforced status transitions (created → uploaded → configured → validated → queued → running → complete → reported → archived)
- **Rate limiting** — in-memory token bucket limiter protecting all endpoints
- **Event bus** — decoupled post-action workflows (e.g., audit.completed, audit.failed)
- **Structured logging** — JSON-formatted log output for production observability

### 3.5 Frontend Coverage

- **Overview dashboard** — product overview with quick-start actions
- **Audit studio** — full dataset and aggregate audit workflow
- **API probe page** — Mode 5 configuration and results
- **Language probe page** — Mode 6 setup and analysis
- **Live monitoring page** — Mode 7 real-time drift tracking
- **History & comparison page** — past audits with side-by-side metric comparison
- **Login / registration page** — glassmorphic auth UI with sign-in and registration modes
- **Live job polling** — real-time status updates during background audit execution
- **User identity pill** — authenticated user info and logout in sidebar
- **Regulatory compliance exports** — one-click JSON downloads for RBI (India), EU AI Act, NYC LL144, ECOA

### 3.6 Python SDK & Jupyter Tutorial

- **Python SDK** (`sdk/fairlens_client.py`) — programmatic access to all audit, report, and monitoring functionality
- **Jupyter Notebook** (`notebooks/SDK_Tutorial.ipynb`) — end-to-end tutorial using an Indian NBFC lending dataset, demonstrating bias audits, regulatory report generation, and CI/CD fairness gates

---

## 4. High-Level Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│                        React / Vite Frontend                     │
│  ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌─────────┐ │
│  │Dashboard │ │ Audit   │ │API Probe │ │Language │ │Monitor  │ │
│  │  Page    │ │ Studio  │ │  Page    │ │ Probe   │ │  Page   │ │
│  └──────────┘ └─────────┘ └──────────┘ └─────────┘ └─────────┘ │
│  ┌──────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Login    │ │ AuthContext · useJobPoller · API Client          ││
│  │  Page    │ │ (JWT tokens, polling, auth headers)              ││
│  └──────────┘ └─────────────────────────────────────────────────┘│
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTP / JSON
┌───────────────────────────┴──────────────────────────────────────┐
│                    FastAPI Backend (app/)                         │
│  ┌────────────┐ ┌──────────────┐ ┌──────────┐ ┌───────────────┐ │
│  │ Auth Routes│ │ Audit Routes │ │Rate Limit│ │ CORS + Logging│ │
│  │ (JWT,RBAC) │ │ (all modes)  │ │Middleware│ │  Middleware    │ │
│  └────────────┘ └──────────────┘ └──────────┘ └───────────────┘ │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                     Services Layer                           ││
│  │  audit_engine · pii_scrubber · gemini_service · reporting    ││
│  │  quality_gate · explainability · causal_analysis             ││
│  │  api_prober · nlp_probe · monitoring · samples               ││
│  │  calibration_fairness · counterfactual · individual_fairness ││
│  └──────────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  Core Layer                                                  ││
│  │  config · database · security · auth · state_machine         ││
│  │  tasks (Celery/BG) · events · rate_limit · json_utils        ││
│  └──────────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  Persistence                                                 ││
│  │  SQLAlchemy models: AuditJob · AuditResult · User · Org      ││
│  │  SQLite (dev) / PostgreSQL (production)                       ││
│  └──────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
         │ (optional)
┌────────┴───────────┐
│  Celery + Redis    │
│  (background jobs) │
└────────────────────┘
```

---

## 5. End-to-End Workflows

### 5.1 Dataset Audit

1. User uploads a CSV or Excel file.
2. **PII scrubber** automatically scans and redacts personal data (emails, phones, SSNs, credit cards, IPs) before any storage or processing.
3. Backend profiles columns and suggests likely protected attributes.
4. User configures outcome column, prediction column (optional), favorable outcome, and protected attributes.
5. Optional: user uploads a model artifact (`.pkl`, `.joblib`) for SHAP root-cause analysis.
6. Quality gate runs pre-audit checks (class imbalance, small groups, missing data).
7. Audit is submitted to background execution (Celery if available, else BackgroundTasks).
8. Frontend polls job status with live indicator until completion.
9. Frontend renders metrics, group stats, proxy warnings, intersectional findings, and root-cause hints.
10. Plain-language report is generated via Gemini AI (with deterministic fallback).
11. User downloads PDF report or mitigated CSV.

### 5.2 Aggregate Audit

1. User enters group names, total counts, and favorable counts.
2. Backend creates an aggregate-mode job and runs the audit immediately.
3. Frontend shows results and allows report generation.

### 5.3 Mode 5 — API Probe

1. Technical owner defines the API endpoint, payload schema, and protected attribute field.
2. Backend generates matched counterfactual request pairs.
3. Probe runs against live API responses or mock outcomes.
4. Frontend shows discrepancy rate, per-case findings, and recommended next actions.

### 5.4 Mode 6 — Adversarial Language Probe

1. Technical owner defines protected attribute groups and scenario templates.
2. Backend generates matched prompt pairs.
3. Probe runs against live endpoint responses or mock outcomes.
4. Frontend presents plain-language insight alongside raw evidence.

### 5.5 Mode 7 — Continuous Monitoring

1. Technical owner configures protected attributes, prediction field, favorable outcome, and alert thresholds.
2. Backend returns a webhook path tied to the monitoring job.
3. Decision records are sent to the webhook continuously.
4. Backend computes rolling-window fairness metrics and detects drift.
5. Frontend displays real-time alerts, status traffic lights, and the latest fairness snapshot.

### 5.6 Authentication Flow

1. User visits the app; the frontend probes `GET /api/v1/auth/me`.
2. If the backend returns 401, the login page is shown.
3. User registers (auto-creates org + admin role) or signs in.
4. JWT access + refresh tokens are stored in `localStorage`.
5. All subsequent API calls include the `Authorization: Bearer <token>` header.
6. On 401 responses, the auth context auto-clears and redirects to login.
7. When `FAIRLENS_AUTH_DISABLED=true` (default dev mode), authentication is bypassed entirely.

---

## 6. Repository Structure

```text
Fairlearn/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── audit.py            # All audit, probe, monitoring, and PII routes
│   │   │       └── auth_routes.py      # Register, login, refresh, profile
│   │   ├── core/
│   │   │   ├── auth.py                 # RBAC, get_current_user, require_permission
│   │   │   ├── config.py              # Pydantic settings with env prefix
│   │   │   ├── database.py            # SQLAlchemy engine + session factory
│   │   │   ├── events.py              # In-process event bus
│   │   │   ├── json_utils.py          # Safe JSON serialization
│   │   │   ├── rate_limit.py          # Token bucket rate limiter
│   │   │   ├── security.py            # bcrypt hashing, JWT encode/decode
│   │   │   ├── state_machine.py       # Job status transitions
│   │   │   └── tasks.py              # Celery / BackgroundTasks execution
│   │   ├── models/
│   │   │   ├── audit_results.py       # Normalized audit results tables
│   │   │   ├── job.py                 # AuditJob model
│   │   │   └── user.py               # User + Organization models
│   │   ├── schemas/                   # Pydantic request/response models
│   │   │   ├── auth.py               # RegisterRequest, TokenResponse, etc.
│   │   │   ├── audit.py              # AuditRunRequest, AuditResultsResponse
│   │   │   ├── configure.py          # ConfigureRequest
│   │   │   ├── upload.py             # UploadResponse
│   │   │   ├── api_probe.py          # API probe schemas
│   │   │   ├── nlp_probe.py          # Language probe schemas
│   │   │   ├── monitoring.py         # Monitoring schemas
│   │   │   ├── report.py             # ReportResponse
│   │   │   └── ...                   # quality, history, sample, etc.
│   │   ├── services/
│   │   │   ├── audit_engine.py        # Core fairness calculations
│   │   │   ├── pii_scrubber.py        # Abstract + regex PII scrubbing
│   │   │   ├── gemini_service.py      # Gemini AI report generation
│   │   │   ├── reporting.py           # PDF report builder
│   │   │   ├── quality_gate.py        # Pre-audit data checks
│   │   │   ├── explainability.py      # SHAP + heuristic root-cause
│   │   │   ├── causal_analysis.py     # Causal pathway estimation
│   │   │   ├── counterfactual_fairness.py
│   │   │   ├── calibration_fairness.py
│   │   │   ├── individual_fairness.py
│   │   │   ├── advanced_statistics.py
│   │   │   ├── api_prober.py          # Mode 5 logic
│   │   │   ├── nlp_probe.py           # Mode 6 logic
│   │   │   ├── monitoring.py          # Mode 7 logic
│   │   │   ├── fairlearn_mitigation.py
│   │   │   ├── fairlearn_crosscheck.py
│   │   │   ├── dataset_mitigator.py
│   │   │   ├── result_persistence.py  # Normalized audit storage
│   │   │   └── ...
│   │   └── main.py                   # Application factory
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── client.js             # All HTTP calls + auth headers
│   │   ├── components/
│   │   │   ├── Layout.jsx            # Sidebar, nav, user pill
│   │   │   ├── audit/                # DatasetAuditWorkflow, AggregateAuditWorkflow, etc.
│   │   │   └── ...
│   │   ├── context/
│   │   │   └── AuthContext.jsx       # JWT auth state + login/register/logout
│   │   ├── hooks/
│   │   │   └── useJobPoller.js       # Background job polling hook
│   │   ├── pages/
│   │   │   ├── DashboardPage.jsx
│   │   │   ├── AuditStudioPage.jsx
│   │   │   ├── ApiProbePage.jsx
│   │   │   ├── NlpProbePage.jsx
│   │   │   ├── MonitoringPage.jsx
│   │   │   ├── HistoryPage.jsx
│   │   │   └── LoginPage.jsx         # Glassmorphic login/register
│   │   ├── styles.css                # Design system + all component styles
│   │   └── App.jsx                   # Root routing + AuthProvider
│   ├── package.json
│   └── .env.example
├── docs/
│   └── PROJECT_DOCUMENTATION.md
├── uploads/                          # Uploaded datasets
├── reports/                          # Generated report files
├── docker-compose.yml
└── README.md
```

---

## 7. Backend Design Details

### 7.1 Authentication & Authorization

| Module | Responsibility |
|--------|---------------|
| `core/security.py` | bcrypt password hashing, JWT encode/decode (HS256) |
| `core/auth.py` | `get_current_user` dependency, RBAC with `require_permission()` |
| `routes/auth_routes.py` | HTTP routes: register, login, refresh, profile |
| `models/user.py` | `User` and `Organization` SQLAlchemy models |
| `schemas/auth.py` | Request/response Pydantic schemas |

**Roles:**

| Role | Permissions |
|------|------------|
| `admin` | All operations (`admin:*`) |
| `auditor` | Create, read, execute audits; generate reports; run probes; setup monitoring |
| `viewer` | Read audits; download reports |

**Auth disabled mode:** When `FAIRLENS_AUTH_DISABLED=true` (default), `get_current_user()` returns a synthetic admin user, so the API works without tokens.

### 7.2 PII Scrubbing Service

Architecture uses the **Strategy Pattern** for easy backend swapping:

```text
BasePIIScrubber (abstract)  ←  RegexPIIScrubber (current, lightweight)
                             ←  PresidioPIIScrubber (future, NLP-grade)
```

The `RegexPIIScrubber` detects and redacts:
- Email addresses → `[EMAIL_REDACTED]`
- Phone numbers → `[PHONE_REDACTED]`
- SSN patterns → `[SSN_REDACTED]`
- Credit card numbers → `[CC_REDACTED]`
- IPv4 addresses → `[IP_REDACTED]`
- Aadhaar numbers (India) → `[AADHAAR_REDACTED]`
- PAN card numbers (India) → `[PAN_REDACTED]`

PII scrubbing runs automatically on every CSV upload, before any data is stored. The scan report is persisted with the job so the frontend can display what was redacted.

To upgrade to Microsoft Presidio, implement `PresidioPIIScrubber(BasePIIScrubber)` and change `get_scrubber()` — no routing or audit logic changes needed.

### 7.3 Regulatory Compliance Reports

The platform generates structured compliance JSON reports for regulatory submission:

| Template | Framework | Target Audience |
|----------|-----------|----------------|
| `rbi_fair_lending` | RBI Digital Lending Guidelines + DPDP Act 2023 | Indian NBFCs and fintechs |
| `eu_ai_act` | EU AI Act Article 13 | High-risk AI systems in Europe |
| `nyc_ll144` | NYC Local Law 144 | Automated employment tools in NYC |
| `ecoa_adverse_action` | ECOA / Regulation B | US credit denial notices |

The **RBI Fair Lending** report specifically:
- Assesses discrimination across Indian-relevant attributes (caste, religion, gender, region, income bracket)
- Flags proxy features that may enable indirect caste/religion discrimination
- References DPDP Act data minimisation requirements
- Includes RBI Integrated Ombudsman grievance redressal information

These templates are available via `GET /api/v1/report/{job_id}/regulatory/{report_type}` and as one-click downloads from the frontend Report Panel.

### 7.3 Job State Machine

All status changes go through `state_machine.transition()` — no raw string assignment allowed.

```text
created → uploaded → configured → validated → queued → running → complete → reported → archived
                                       ↓                  ↓         ↑
                                    queued ←─────── failed ─────────┘
                                       ↑                            (retry)
                                  complete ─────────────────────────┘
                                                                  (re-run)
```

### 7.4 Background Task Execution

The `tasks.py` module supports two backends:

| Backend | When Used | Configuration |
|---------|-----------|--------------|
| **Celery + Redis** | Production | Set `CELERY_BROKER_URL` env var |
| **FastAPI BackgroundTasks** | Development | Default (no extra infra) |
| **Synchronous** | Tests | Fallback when no task runner available |

Celery configuration includes:
- 5-minute soft time limit
- 6-minute hard kill
- 2 automatic retries with 30s backoff

### 7.5 Event Bus

The `events.py` module provides a lightweight in-process event bus for decoupled workflows:

```python
from app.core.events import event_bus

@event_bus.on("audit.completed")
def send_notification(job_id: str, **kwargs):
    ...

event_bus.emit("audit.completed", job_id="abc-123")
```

Listeners run synchronously. Exceptions are logged but never propagated — an observer can never break the emitter.

Current events emitted:
- `audit.completed` — after a successful audit
- `audit.failed` — after an audit failure

### 7.6 Rate Limiting

In-memory token bucket limiter, configured via environment variables:

| Setting | Default | Scope |
|---------|---------|-------|
| `FAIRLENS_RATE_LIMIT_DEFAULT` | `100/minute` | All endpoints |
| `FAIRLENS_RATE_LIMIT_PROBE` | `10/minute` | Probe execution |
| `FAIRLENS_RATE_LIMIT_WEBHOOK` | `1000/minute` | Monitoring webhooks |

Rate limiting keys by `{client_ip}:{path}` for per-endpoint granularity.

### 7.7 Core Services

| Service | Responsibility |
|---------|---------------|
| `audit_engine.py` | Fairness metrics, intersectional analysis, proxy scanning |
| `pii_scrubber.py` | PII detection and redaction |
| `gemini_service.py` | Gemini AI narrative generation with deterministic fallback |
| `reporting.py` | Report construction and PDF generation (ReportLab) |
| `quality_gate.py` | Pre-audit data quality checks |
| `explainability.py` | SHAP-first root-cause analysis with heuristic fallback |
| `causal_analysis.py` | Causal pathway estimation |
| `counterfactual_fairness.py` | Counterfactual outcome sensitivity |
| `calibration_fairness.py` | Probability calibration across groups |
| `individual_fairness.py` | Consistency scoring for similar individuals |
| `advanced_statistics.py` | Wilson intervals, bootstrap, statistical depth |
| `fairlearn_crosscheck.py` | Independent verification via Fairlearn library |
| `fairlearn_mitigation.py` | Simulated mitigation tradeoffs |
| `api_prober.py` | Mode 5 counterfactual API testing |
| `nlp_probe.py` | Mode 6 adversarial language testing |
| `monitoring.py` | Mode 7 rolling-window drift detection |
| `normalization.py` | Data preprocessing and encoding |
| `outcome_analysis.py` | Outcome distribution analysis |
| `data_diagnostics.py` | Extended data health diagnostics |
| `result_persistence.py` | Normalized audit result storage |
| `samples.py` | Built-in sample dataset generation |
| `file_parser.py` | File save, read, and column profiling |
| `dataset_mitigator.py` | Mitigated CSV generation |

### 7.8 Complete API Reference

#### Authentication

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/register` | Register user + auto-create org |
| `POST` | `/api/v1/auth/login` | OAuth2-compatible login → tokens |
| `POST` | `/api/v1/auth/refresh` | Exchange refresh token for new pair |
| `GET` | `/api/v1/auth/me` | Current user profile |

#### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Basic health check |
| `GET` | `/api/v1/health/ready` | Readiness probe (DB, Redis, Gemini) |

#### Core Audit

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/upload` | Upload dataset (auto PII scrub) |
| `POST` | `/api/v1/aggregate` | Submit aggregate counts |
| `POST` | `/api/v1/configure` | Configure audit parameters |
| `POST` | `/api/v1/model/upload` | Upload model artifact |
| `POST` | `/api/v1/quality-check` | Run pre-audit quality gate |
| `POST` | `/api/v1/audit/run` | Submit audit to background execution |
| `GET` | `/api/v1/audit/{job_id}` | Get audit results |
| `GET` | `/api/v1/jobs/{job_id}` | Get full job details |
| `GET` | `/api/v1/jobs/{job_id}/status` | Lightweight status for polling |
| `GET` | `/api/v1/pii/scan/{job_id}` | Get PII scan report |

#### Reporting & Downloads

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/report/generate` | Generate plain-language report |
| `GET` | `/api/v1/report/{job_id}/pdf` | Download PDF report |
| `GET` | `/api/v1/mitigate/{job_id}/download` | Download mitigated CSV |
| `GET` | `/api/v1/samples` | List built-in sample datasets |
| `GET` | `/api/v1/samples/{id}/download` | Download sample dataset |

#### History

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/history` | List all past audits |
| `GET` | `/api/v1/history/compare` | Compare two audit runs |

#### API Probe (Mode 5)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/probe/configure` | Configure API probe |
| `POST` | `/api/v1/probe/run` | Execute probe |
| `GET` | `/api/v1/probe/{job_id}` | Get probe results |

#### Language Probe (Mode 6)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/nlp-probe/setup` | Configure language probe |
| `POST` | `/api/v1/nlp-probe/run` | Execute probe |
| `GET` | `/api/v1/nlp-probe/{job_id}` | Get probe results |

#### Continuous Monitoring (Mode 7)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/monitor/setup` | Configure monitoring job |
| `POST` | `/api/v1/webhook/predict/{job_id}` | Ingest decision records |
| `GET` | `/api/v1/monitor/{job_id}` | Get monitoring status |

---

## 8. Frontend Design Details

### 8.1 Main Pages

| Page | Purpose |
|------|---------|
| `DashboardPage` | Product overview, quick-start actions, system health |
| `AuditStudioPage` | Full audit workspace (dataset + aggregate modes) |
| `ApiProbePage` | Mode 5 API probe setup and results |
| `NlpProbePage` | Mode 6 language probe setup and analysis |
| `MonitoringPage` | Mode 7 real-time drift and alerts |
| `HistoryPage` | Past audits with side-by-side comparison |
| `LoginPage` | Glassmorphic login and registration |

### 8.2 Auth Integration

The `AuthContext` provides:
- Token storage in `localStorage` (access + refresh)
- `login()`, `register()`, `logout()` methods
- Automatic auth probing on mount via `GET /auth/me`
- `useAuth()` hook exposing `{ token, user, isAuthenticated, authRequired, loading }`

The `client.js` API layer:
- Injects `Authorization: Bearer <token>` on every request when a token exists
- Auto-handles 401 responses by calling `onUnauthorized()` to clear auth state

### 8.3 Job Polling

The `useJobPoller(api, jobId)` custom hook:
- Polls `GET /jobs/{job_id}/status` every 3 seconds while status is `queued` or `running`
- Auto-stops on terminal states (`complete`, `failed`, `reported`, `archived`)
- Returns `{ status, startedAt, isRunning, isComplete, isFailed }`
- Integrated into `AuditStudioPage` with a pulsing live indicator and auto-load on completion

### 8.4 Design System

The CSS design system uses a warm, premium aesthetic:
- **Font**: Space Grotesk
- **Color palette**: warm paper backgrounds, teal accent (`--sea`), burnt orange brand (`--brand`)
- **Glass effects**: backdrop-filter blur on sidebar, auth card, and panels
- **Animations**: auth-rise entrance, pulse-ring polling dot, shake on errors, fade-in for user pill
- **Layout**: CSS Grid sidebar + main content area, responsive down to mobile

### 8.5 UI Principles

- Plain-language wording for non-technical users
- Visual grouping by workflow stage
- Backend state visible but not overwhelming
- Readable summaries shown before raw evidence
- Progressive disclosure of technical details

---

## 9. Environment Variables

### 9.1 Backend (prefixed with `FAIRLENS_`)

| Variable | Default | Description |
|----------|---------|-------------|
| `FAIRLENS_APP_ENV` | `development` | Environment mode |
| `FAIRLENS_DATABASE_URL` | `sqlite+pysqlite:///./fairlens.db` | Database connection string |
| `FAIRLENS_UPLOAD_DIR` | `../uploads` | Upload storage path |
| `FAIRLENS_REPORTS_DIR` | `../reports` | Report storage path |
| `FAIRLENS_GEMINI_API_KEY` | — | Google Gemini API key |
| `FAIRLENS_GEMINI_MODEL` | `gemini-1.5-flash` | Gemini model name |
| `FAIRLENS_MAX_UPLOAD_SIZE_MB` | `50` | Maximum upload file size |
| `FAIRLENS_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins |
| `FAIRLENS_JWT_SECRET_KEY` | `CHANGE-ME-in-production` | JWT signing secret |
| `FAIRLENS_AUTH_DISABLED` | `true` | Bypass authentication in dev |
| `FAIRLENS_CELERY_BROKER_URL` | — | Redis URL for Celery (optional) |
| `FAIRLENS_RATE_LIMIT_DEFAULT` | `100/minute` | Default rate limit |
| `FAIRLENS_RATE_LIMIT_PROBE` | `10/minute` | Probe endpoint rate limit |
| `FAIRLENS_RATE_LIMIT_WEBHOOK` | `1000/minute` | Webhook rate limit |

### 9.2 Frontend

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api` | Backend API base URL |

---

## 10. Local Development Setup

### 10.1 Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -e .[dev]
uvicorn app.main:app --reload
```

Backend URLs:
- API: `http://127.0.0.1:8000`
- Swagger docs: `http://127.0.0.1:8000/api/docs`
- ReDoc: `http://127.0.0.1:8000/api/redoc`

### 10.2 Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Frontend URL: `http://127.0.0.1:5173`

### 10.3 Docker Compose (Full Stack)

```bash
docker-compose up --build
```

This starts: backend, frontend, PostgreSQL, and optionally Redis + Celery worker.

### 10.4 Enabling Authentication

By default, auth is disabled for development. To enable:

```bash
# In .env or environment
FAIRLENS_AUTH_DISABLED=false
FAIRLENS_JWT_SECRET_KEY=<your-secret-key>  # Use: openssl rand -hex 32
```

Then register via the frontend login page or `POST /api/v1/auth/register`.

---

## 11. Testing and Verification

### 11.1 Backend Tests

Backend tests cover:
- Attribute detection
- Quality gate behavior
- Audit pipeline (dataset + aggregate)
- Mode 5 API probe
- Mode 6 language probe
- Mode 7 monitoring
- PII scrubbing
- Auth routes

```bash
cd backend
python -m pytest
```

### 11.2 Frontend Verification

```bash
cd frontend
npm run build    # Production build compiles successfully
```

---

## 12. Known Limitations

- No end-to-end browser automation test suite
- Gemini-backed report enrichment depends on external API key configuration
- Some explainability paths fall back to heuristic analysis when SHAP cannot be used on the provided model artifact
- Monitoring is rolling-window based, not a full production observability platform
- Rate limiting is in-memory (resets on restart); production should use Redis-backed limiting
- PII scrubbing is regex-based; does not detect names, addresses, or contextual PII

---

## 13. Future Scope

These items are intentionally outside the current implementation scope:

- Document and screenshot upload analysis
- Microsoft Presidio integration for NLP-grade PII detection
- Redis-backed rate limiting for multi-worker deployments
- End-to-end browser automation tests
- SSO / OAuth2 provider integration
- Multi-tenant data isolation with row-level security
- Kubernetes deployment manifests
- Automated CI/CD pipeline

---

## 14. Troubleshooting

### 14.1 Frontend cannot reach backend

- Verify backend is running on `127.0.0.1:8000`
- Check `VITE_API_BASE_URL` in frontend `.env`
- Verify `FAIRLENS_CORS_ORIGINS` includes the frontend origin

### 14.2 Authentication errors

- If auth is supposed to be disabled, ensure `FAIRLENS_AUTH_DISABLED=true`
- If auth is enabled, ensure `FAIRLENS_JWT_SECRET_KEY` is set to a strong secret
- Check that the token has not expired (access tokens last 60 minutes)

### 14.3 Audit fails after upload

- Ensure configuration step has been completed
- Verify chosen columns exist in the uploaded data
- Review quality gate warnings or failures

### 14.4 PII scrubbing not running

- PII scrubbing runs automatically on CSV upload — no manual step required
- Check the PII scan report via `GET /api/v1/pii/scan/{job_id}`

### 14.5 Background tasks not executing

- In dev mode, tasks run via `BackgroundTasks` — they execute in the same process
- For Celery, ensure `CELERY_BROKER_URL` is set and the Redis server is reachable
- Start the Celery worker: `celery -A app.core.tasks.celery_app worker --loglevel=info`

### 14.6 Frontend build fails

- Ensure `npm install` completed successfully
- Verify `node_modules` exists under `frontend/`
- Use a supported recent Node.js version (18+)
