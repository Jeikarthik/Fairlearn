"""Job lifecycle service — state-machine-enforced transitions + result persistence.

Every status change goes through the state machine. Every result
write fans out to normalized tables.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.state_machine import JobStatus, transition
from app.models.job import AuditJob

logger = logging.getLogger("fairlens")


def create_upload_job(
    db: Session,
    *,
    mode: str,
    filename: str | None,
    file_path: str | None,
    upload_summary: dict[str, object],
    org_id: str | None = None,
    user_id: str | None = None,
) -> AuditJob:
    job = AuditJob(
        id=str(uuid4()),
        mode=mode,
        filename=filename,
        file_path=file_path,
        status=JobStatus.CREATED.value,
        org_id=org_id,
        user_id=user_id,
        upload_summary_json=json.dumps(upload_summary),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Immediately transition to uploaded (file received)
    _transition(db, job, JobStatus.UPLOADED)
    logger.info("job.created", extra={"job_id": job.id, "mode": mode})
    return job


def get_job(db: Session, job_id: str) -> AuditJob:
    job = db.get(AuditJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    return job


def update_job_config(db: Session, job: AuditJob, config: dict[str, object]) -> AuditJob:
    job.config_json = json.dumps(config)
    _transition(db, job, JobStatus.CONFIGURED)
    return job


def save_quality_report(db: Session, job: AuditJob, report: dict[str, object]) -> AuditJob:
    existing = json.loads(job.upload_summary_json or "{}")
    existing["quality_report"] = report
    job.upload_summary_json = json.dumps(existing)
    _transition(db, job, JobStatus.VALIDATED)
    return job


def mark_job_queued(db: Session, job: AuditJob) -> AuditJob:
    """Mark job as queued for background execution."""
    _transition(db, job, JobStatus.QUEUED)
    return job


def mark_job_running(db: Session, job: AuditJob) -> AuditJob:
    job.started_at = datetime.utcnow()
    _transition(db, job, JobStatus.RUNNING)
    return job


def update_job_results(
    db: Session,
    job: AuditJob,
    results: dict[str, object],
    *,
    status: str | None = None,
) -> AuditJob:
    job.results_json = json.dumps(results)
    job.completed_at = datetime.utcnow()
    try:
        target = JobStatus(status) if status else JobStatus.COMPLETE
        _transition(db, job, target)
    except (ValueError, KeyError):
        # Domain-specific status ("alerting", "monitoring") or invalid transition —
        # store directly without going through the state machine.
        job.status = status or JobStatus.COMPLETE.value
        db.add(job)
        db.commit()
        db.refresh(job)

    # Fan out to normalized tables
    try:
        from app.services.result_persistence import persist_audit_results
        persist_audit_results(db, job.id, results)
    except Exception as exc:  # noqa: BLE001
        logger.warning("result_persistence failed for job %s: %s", job.id, exc)

    return job


def mark_job_failed(db: Session, job: AuditJob, error: str) -> AuditJob:
    job.error_message = error
    job.completed_at = datetime.utcnow()
    _transition(db, job, JobStatus.FAILED)
    return job


def parse_json_field(field: str | None) -> dict[str, object]:
    if not field:
        return {}
    return json.loads(field)


def _transition(db: Session, job: AuditJob, target: JobStatus) -> None:
    """Run the state machine transition and persist."""
    current = JobStatus(job.status)
    new_status = transition(current, target)
    job.status = new_status.value
    db.add(job)
    db.commit()
    db.refresh(job)
