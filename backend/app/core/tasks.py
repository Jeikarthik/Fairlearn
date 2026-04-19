"""Background audit task execution — runs audits outside the HTTP thread.

Supports two backends:
  1. FastAPI BackgroundTasks (default, no extra infra)
  2. Celery + Redis (production, set CELERY_BROKER_URL)

Both backends share the same `_execute_audit` core function.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.core.database import SessionLocal
from app.core.events import event_bus
from app.core.state_machine import JobStatus

logger = logging.getLogger(__name__)


def _execute_audit(job_id: str) -> None:
    """Core audit execution — called by any task backend."""
    from pathlib import Path

    from app.models.job import AuditJob
    from app.services.audit_engine import run_audit
    from app.services.file_parser import read_tabular_file
    from app.services.result_persistence import persist_audit_results

    db = SessionLocal()
    try:
        job = db.get(AuditJob, job_id)
        if job is None:
            logger.error("Job %s not found — cannot run audit.", job_id)
            return

        # Mark as running
        job.status = JobStatus.RUNNING.value
        db.commit()

        logger.info("audit.started", extra={"job_id": job_id, "mode": job.mode})
        start = time.monotonic()

        config = json.loads(job.config_json or "{}")

        if job.mode == "aggregate":
            from app.services.audit_engine import run_aggregate_audit

            results = run_aggregate_audit(config)
        else:
            if not job.file_path:
                raise ValueError("Job has no uploaded dataset.")
            dataframe = read_tabular_file(Path(job.file_path))
            results = run_audit(dataframe, config, model_path=config.get("model_artifact_path"))

        # Store results in JSON (backward compat) AND normalized tables
        job.results_json = json.dumps(results)
        job.status = JobStatus.COMPLETE.value
        db.commit()

        # Persist to normalized tables
        persist_audit_results(db, job_id, results)

        elapsed = round(time.monotonic() - start, 2)
        logger.info("audit.completed", extra={"job_id": job_id, "duration_seconds": elapsed})

        event_bus.emit("audit.completed", job_id=job_id)

    except Exception as exc:
        logger.exception("audit.failed for job %s", job_id)
        if job:
            job.status = JobStatus.FAILED.value
            job.results_json = json.dumps({"error": str(exc)})
            db.commit()
        event_bus.emit("audit.failed", job_id=job_id, error=str(exc))
    finally:
        db.close()


# ── Celery backend (used if CELERY_BROKER_URL is set) ─────────

try:
    import os

    broker_url = os.getenv("CELERY_BROKER_URL")
    if broker_url:
        from celery import Celery

        celery_app = Celery("fairlens", broker=broker_url, backend=broker_url)
        celery_app.conf.task_serializer = "json"
        celery_app.conf.result_serializer = "json"
        celery_app.conf.task_soft_time_limit = 300  # 5 min
        celery_app.conf.task_time_limit = 360  # 6 min hard kill

        @celery_app.task(bind=True, max_retries=2, name="run_audit_task")
        def run_audit_celery(self: Any, job_id: str) -> None:
            try:
                _execute_audit(job_id)
            except Exception as exc:
                raise self.retry(exc=exc, countdown=30)

    else:
        celery_app = None
except ImportError:
    celery_app = None


def submit_audit(job_id: str, background_tasks: Any | None = None) -> str:
    """Submit an audit for background execution.

    Returns the execution backend used: 'celery' or 'background_task'.
    """
    if celery_app is not None:
        run_audit_celery.delay(job_id)
        return "celery"

    if background_tasks is not None:
        background_tasks.add_task(_execute_audit, job_id)
        return "background_task"

    # Fallback: synchronous (should only happen in tests)
    _execute_audit(job_id)
    return "synchronous"
