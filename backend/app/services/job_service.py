from __future__ import annotations

import json
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.job import AuditJob


def create_upload_job(
    db: Session,
    *,
    mode: str,
    filename: str | None,
    file_path: str | None,
    upload_summary: dict[str, object],
) -> AuditJob:
    job = AuditJob(
        id=str(uuid4()),
        mode=mode,
        filename=filename,
        file_path=file_path,
        status="uploaded",
        upload_summary_json=json.dumps(upload_summary),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> AuditJob:
    job = db.get(AuditJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    return job


def update_job_config(db: Session, job: AuditJob, config: dict[str, object]) -> AuditJob:
    job.config_json = json.dumps(config)
    job.status = "configured"
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def save_quality_report(db: Session, job: AuditJob, report: dict[str, object]) -> AuditJob:
    existing = json.loads(job.upload_summary_json or "{}")
    existing["quality_report"] = report
    job.upload_summary_json = json.dumps(existing)
    job.status = "quality_checked"
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_job_results(db: Session, job: AuditJob, results: dict[str, object], *, status: str | None = None) -> AuditJob:
    job.results_json = json.dumps(results)
    if status:
        job.status = status
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def parse_json_field(field: str | None) -> dict[str, object]:
    if not field:
        return {}
    return json.loads(field)
