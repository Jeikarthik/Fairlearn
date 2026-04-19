"""Background audit task execution — runs audits outside the HTTP thread.

Supports two backends:
  1. FastAPI BackgroundTasks (default, no extra infra)
  2. Celery + Redis (production, set CELERY_BROKER_URL)

Both backends share the same `_execute_audit` core function.

Celery beat schedules (active when CELERY_BROKER_URL is set):
  - cleanup_old_files  — daily at 02:00 UTC, removes uploads older than
                         FAIRLENS_FILE_RETENTION_DAYS (default 30)
  - scheduled_audits   — hourly, re-runs any jobs flagged for scheduling
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.core.database import SessionLocal
from app.core.events import event_bus
from app.core.json_utils import safe_json_dumps
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
    job = None
    try:
        job = db.get(AuditJob, job_id)
        if job is None:
            logger.error("Job %s not found — cannot run audit.", job_id)
            return

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

        job.results_json = safe_json_dumps(results)
        job.status = JobStatus.COMPLETE.value
        db.commit()

        # Persist to normalized tables (idempotent)
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


def _cleanup_old_files() -> None:
    """Delete uploaded files and completed jobs older than the retention window."""
    import os
    from datetime import datetime, timedelta
    from pathlib import Path

    from app.models.job import AuditJob
    from sqlalchemy import select

    retention_days: int = int(os.getenv("FAIRLENS_FILE_RETENTION_DAYS", "30"))
    cutoff = datetime.utcnow() - timedelta(days=retention_days)

    db = SessionLocal()
    try:
        stmt = select(AuditJob).where(
            AuditJob.status.in_(["complete", "reported", "archived"]),
            AuditJob.completed_at < cutoff,
            AuditJob.file_path.isnot(None),
        )
        jobs = db.execute(stmt).scalars().all()
        removed = 0
        for job in jobs:
            if job.file_path:
                path = Path(job.file_path)
                if path.exists():
                    try:
                        path.unlink()
                        removed += 1
                    except OSError as exc:
                        logger.warning("Could not remove upload %s: %s", path, exc)
            # Null out the path so re-runs fail clearly rather than silently
            job.file_path = None
        db.commit()
        logger.info("cleanup.completed: removed %d files older than %d days", removed, retention_days)
    except Exception:
        logger.exception("cleanup task failed")
    finally:
        db.close()


def _run_scheduled_audits() -> None:
    """Re-run any jobs that have been flagged for scheduled re-auditing.

    A job is scheduled for re-audit when its config_json contains:
      {"scheduled_reaudit": true, "reaudit_interval_hours": N}
    and `completed_at` is more than N hours ago.
    """
    from datetime import datetime, timedelta

    from app.models.job import AuditJob
    from sqlalchemy import select

    db = SessionLocal()
    try:
        stmt = select(AuditJob).where(AuditJob.status == "complete")
        jobs = db.execute(stmt).scalars().all()
        for job in jobs:
            try:
                config = json.loads(job.config_json or "{}")
                if not config.get("scheduled_reaudit"):
                    continue
                interval_hours = int(config.get("reaudit_interval_hours", 24))
                if job.completed_at and job.completed_at < datetime.utcnow() - timedelta(hours=interval_hours):
                    logger.info("Triggering scheduled re-audit for job %s", job.id)
                    if celery_app is not None:
                        run_audit_celery.delay(job.id)
                    else:
                        _execute_audit(job.id)
            except Exception:  # noqa: BLE001
                logger.exception("Scheduled re-audit failed for job %s", job.id)
    except Exception:
        logger.exception("scheduled_audits task failed")
    finally:
        db.close()


# ── Celery backend (used if CELERY_BROKER_URL is set) ─────────────

try:
    import os

    broker_url = os.getenv("CELERY_BROKER_URL") or os.getenv("FAIRLENS_CELERY_BROKER_URL")
    if broker_url:
        from celery import Celery
        from celery.schedules import crontab

        celery_app = Celery("fairlens", broker=broker_url, backend=broker_url)
        celery_app.conf.update(
            task_serializer="json",
            result_serializer="json",
            accept_content=["json"],
            task_soft_time_limit=300,   # 5 min soft kill
            task_time_limit=360,         # 6 min hard kill
            worker_prefetch_multiplier=1,  # fair dispatch — don't pre-fetch
            task_acks_late=True,           # re-queue on worker crash
        )

        # ── Celery beat periodic tasks ──────────────────────────
        celery_app.conf.beat_schedule = {
            "cleanup-old-uploads": {
                "task": "app.core.tasks.cleanup_old_files_task",
                "schedule": crontab(hour=2, minute=0),  # daily at 02:00 UTC
            },
            "scheduled-reaudits": {
                "task": "app.core.tasks.scheduled_audits_task",
                "schedule": crontab(minute=0),  # every hour on the hour
            },
        }
        celery_app.conf.timezone = "UTC"

        @celery_app.task(bind=True, max_retries=2, name="run_audit_task")
        def run_audit_celery(self: Any, job_id: str) -> None:
            try:
                _execute_audit(job_id)
            except Exception as exc:
                raise self.retry(exc=exc, countdown=30)

        @celery_app.task(name="app.core.tasks.cleanup_old_files_task")
        def cleanup_old_files_task() -> None:
            _cleanup_old_files()

        @celery_app.task(name="app.core.tasks.scheduled_audits_task")
        def scheduled_audits_task() -> None:
            _run_scheduled_audits()

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

    # Fallback: synchronous (tests only)
    _execute_audit(job_id)
    return "synchronous"
