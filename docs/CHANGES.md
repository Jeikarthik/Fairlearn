# FairLens — Change Log

All architectural fixes and production-grade improvements made in this session.
Changes are grouped by layer: Infrastructure, Backend Core, Backend Services, API, Frontend, and New Additions.

---

## Infrastructure

### `docker-compose.yml`
- **Fixed:** `FAIRLENS_AUTH_DISABLED` changed from `"true"` to `"false"` on all services — authentication is now ON in production deployments.
- **Added:** `FAIRLENS_MAX_UPLOAD_SIZE_MB: "50"` and `FAIRLENS_FILE_RETENTION_DAYS: "30"` env vars on API and worker services.
- **Added:** OpenTelemetry env vars (`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`) on API and worker — set `OTEL_ENDPOINT` at deploy time to enable tracing.
- **Added:** New `beat` service running `celery beat` for scheduled periodic tasks (file cleanup daily at 02:00 UTC, hourly scheduled re-audit sweep). Resource-capped at 256 MB / 0.25 CPU.

### `backend/pyproject.toml`
- **Added:** `[observability]` optional dependency group: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`. Install with `pip install fairlens-backend[observability]`.

---

## Backend — Core

### `backend/app/main.py`
- **Fixed:** Removed duplicate router mounting — `audit_router` was previously mounted at both `/api` AND `/api/v1`, creating duplicate endpoints, broken auth scoping, and doubled OpenAPI docs. Now mounted once at `/api`; auth routes remain at `/api/v1`.
- **Added:** File-size enforcement middleware — checks `Content-Length` header on every `POST /upload` request and returns HTTP 413 before reading the body if the payload exceeds `FAIRLENS_MAX_UPLOAD_SIZE_MB`.
- **Added:** `X-Request-ID` header on every response for request correlation in logs.
- **Added:** OpenTelemetry bootstrap — calls `setup_telemetry()` at startup; silent no-op if the env var is not set or the packages are not installed.
- **Changed:** `RateLimiter(...)` replaced with `build_limiter(...)` which selects the Redis-backed limiter when `CELERY_BROKER_URL` is set.
- **Added:** `/api/health` alias so the health endpoint works at both `/api/health` and `/api/v1/health`.

### `backend/app/core/rate_limit.py` *(rewrite)*
- **Fixed:** In-process token bucket was bypassed in multi-worker deployments (each Gunicorn worker had its own bucket). Now auto-selects a Redis sliding-window limiter when `CELERY_BROKER_URL` is available. Falls back to in-memory if Redis is unreachable (fail-open, no traffic blocked).
- **Added:** `build_limiter(default_rpm, redis_url)` factory function — called by `main.py`.
- **Preserved:** `RateLimiter` alias for backward compatibility with existing imports.

### `backend/app/core/tasks.py` *(upgrade)*
- **Added:** `_cleanup_old_files()` — deletes uploaded files older than `FAIRLENS_FILE_RETENTION_DAYS` (default 30 days) from jobs in terminal states. Nulls out `file_path` so re-runs fail clearly.
- **Added:** `_run_scheduled_audits()` — re-runs jobs with `config["scheduled_reaudit"] = True` if `reaudit_interval_hours` have elapsed since `completed_at`.
- **Added:** Celery beat schedule: `cleanup-old-uploads` (daily 02:00 UTC) and `scheduled-reaudits` (hourly).
- **Changed:** Worker config updated with `worker_prefetch_multiplier=1` and `task_acks_late=True` for fairer dispatch and crash recovery.
- **Fixed:** `FAIRLENS_CELERY_BROKER_URL` env var also checked (in addition to `CELERY_BROKER_URL`) for consistent env var naming.

### `backend/app/core/alerting.py` *(new)*
- Drift alerting rules engine for the continuous monitoring mode.
- Rules stored in job `config_json["alert_rules"]` — no schema migration required.
- Supported operators: `>`, `>=`, `<`, `<=`, `==`, `!=`.
- Supported channels: `log` (structured warning log) and `webhook` (HTTP POST to any URL).
- Functions: `add_rule`, `remove_rule`, `list_rules`, `evaluate_rules`.
- `evaluate_rules()` is called on every monitoring webhook ingestion and fires matched rules.

### `backend/app/core/telemetry.py` *(new)*
- Optional OpenTelemetry instrumentation — completely transparent no-op when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset or packages missing.
- Supports OTLP/gRPC exporter (Jaeger, Grafana Tempo, Honeycomb) and console exporter.
- Auto-instruments FastAPI request spans and SQLAlchemy query spans when packages are installed.
- Provides `get_tracer(name)` for manual instrumentation with a no-op fallback.

---

## Backend — Services

### `backend/app/services/audit_engine.py`
- **Fixed:** `_safe()` inner function now explicitly re-raises `MemoryError` instead of swallowing it. A module OOM now propagates out of `ThreadPoolExecutor.result()` so the caller can respond appropriately rather than silently receiving an error dict.

### `backend/app/services/result_persistence.py`
- **Fixed:** `persist_audit_results()` is now idempotent. Previously, calling it twice (e.g. report generation after audit) created duplicate rows in `audit_metrics`, `group_stats`, and `proxy_features`. Now deletes existing rows for the job before re-inserting.

### `backend/app/services/job_service.py`
- **Fixed:** `get_job(db, job_id)` now accepts an optional `org_id` keyword argument. When provided and the job belongs to a different org, raises HTTP 403 instead of returning the job — prevents cross-tenant data leakage.
- **Fixed:** Removed unused `Any` import.

---

## Backend — API Routes

### `backend/app/api/routes/audit.py`
- **Added:** Secondary file-size guard in `POST /upload` — checks `file.size` against `settings.max_upload_size_mb` and returns HTTP 413 if exceeded (belt-and-suspenders alongside the middleware).
- **Added:** `GET /monitor/{job_id}/alerts` — list alert rules for a monitor job.
- **Added:** `POST /monitor/{job_id}/alerts` — add an alert rule to a monitor job.
- **Added:** `DELETE /monitor/{job_id}/alerts/{rule_id}` — remove an alert rule.
- **Added:** `POST /jobs/{job_id}/schedule` — enable/disable scheduled re-auditing with configurable interval.
- **Added:** `GET /report/{job_id}/regulatory/{report_type}` — generate a structured regulatory report (nyc_ll144 / eu_ai_act / ecoa_adverse_action) directly from audit results via the existing `regulatory_templates.py` module.

---

## Frontend

### `frontend/src/components/ErrorBoundary.jsx` *(new)*
- React class component implementing the Error Boundary pattern.
- Catches unhandled render and lifecycle errors in any wrapped subtree.
- Shows a recovery UI ("Try again" / "Reload page") instead of a blank white screen.
- Accepts `fallback` (custom element) and `onError` (callback for Sentry/logging) props.

### `frontend/src/App.jsx`
- **Added:** Imports `ErrorBoundary`.
- **Added:** Each page route is now individually wrapped in `<ErrorBoundary>` so a crash in one page does not destroy the entire application shell (layout, navigation).

### `frontend/src/components/audit/DatasetAuditWorkflow.jsx`
- **Fixed:** `handleRunAudit` no longer waits inline for audit completion. It now calls `api.runAudit()` (which returns immediately with `{status: "queued"}`), then calls `actions.setPollingJobId(currentJob.id)` to start the existing `useJobPoller` hook. Results load automatically when the poller detects `status === "complete"`. Previously the UI would wait with a spinner and silently succeed with a "queued" job — results never appeared.
- **Added:** Client-side file-size validation in `handleDatasetUpload` — checks `file.size` against 50 MB before the upload request is sent, providing an immediate error message instead of waiting for a server 413.

### `frontend/src/api/client.js`
- **Added:** `listAlertRules(monitorJobId)` — GET alert rules.
- **Added:** `addAlertRule(monitorJobId, rule)` — POST new alert rule.
- **Added:** `deleteAlertRule(monitorJobId, ruleId)` — DELETE alert rule.
- **Added:** `setSchedule(jobId, { enabled, intervalHours })` — configure scheduled re-audit.
- **Added:** `getRegulatoryReport(jobId, reportType)` — fetch regulatory compliance report.

---

## New Additions

### `sdk/fairlens_client.py` *(new — standalone Python SDK)*
A `pip install requests pandas`-only SDK for programmatic access without the web UI.

Key methods:
- `FairLensClient(base_url, api_token)` — constructor
- `.audit(df, outcome_column, protected_attributes, favorable_outcome, ...)` — upload DataFrame, configure, run, and wait for results in one call
- `.audit_aggregate(attribute_name, groups, domain, ...)` — count-based audit without raw data
- `.get_results(job_id)` — fetch completed audit results
- `.generate_report(job_id)` — generate plain-language report
- `.download_report_pdf(job_id)` — download PDF as bytes
- `.regulatory_report(job_id, report_type)` — NYC LL144 / EU AI Act / ECOA report
- `.list_jobs()` — history
- `.compare_jobs(old_id, new_id)` — fairness diff between runs
- `.add_alert_rule / list_alert_rules / delete_alert_rule` — alert management
- `.set_schedule(job_id, enabled, interval_hours)` — configure re-audit cadence

---

## Summary Table

| Area | Change Type | File(s) |
|------|------------|---------|
| Auth default | Security fix | `docker-compose.yml` |
| Duplicate router | Architecture fix | `main.py` |
| File size enforcement | Safety | `main.py`, `audit.py` |
| Request ID header | Observability | `main.py` |
| Redis rate limiting | Scalability | `rate_limit.py` |
| MemoryError propagation | Reliability | `audit_engine.py` |
| Idempotent persistence | Data integrity | `result_persistence.py` |
| Org isolation | Security | `job_service.py` |
| Celery beat schedule | Operations | `tasks.py`, `docker-compose.yml` |
| File cleanup task | Operations | `tasks.py` |
| Scheduled re-audit | Feature | `tasks.py`, `audit.py` |
| Alerting rules engine | Feature | `alerting.py`, `audit.py`, `client.js` |
| OpenTelemetry | Observability | `telemetry.py`, `main.py` |
| Python SDK | Adoption | `sdk/fairlens_client.py` |
| React ErrorBoundary | Resilience | `ErrorBoundary.jsx`, `App.jsx` |
| Audit polling fix | UX | `DatasetAuditWorkflow.jsx` |
| Client file size check | UX | `DatasetAuditWorkflow.jsx` |
| Regulatory report API | Feature | `audit.py`, `client.js` |
