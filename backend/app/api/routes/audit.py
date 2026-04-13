from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.configure import ConfigureRequest, ConfigureResponse
from app.schemas.quality import QualityCheckRequest, QualityCheckResponse
from app.schemas.upload import UploadResponse
from app.services.file_parser import build_upload_summary, read_tabular_file, save_upload
from app.services.job_service import create_upload_job, get_job, parse_json_field, save_quality_report, update_job_config
from app.services.quality_gate import run_quality_gate

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/upload", response_model=UploadResponse)
def upload_dataset(
    mode: str = Form(default="prediction"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadResponse:
    saved_path = save_upload(file)
    dataframe = read_tabular_file(saved_path)
    summary = build_upload_summary(dataframe)
    job = create_upload_job(
        db,
        mode=mode,
        filename=file.filename,
        file_path=str(saved_path),
        upload_summary=summary,
    )
    return UploadResponse(job_id=job.id, mode=mode, **summary)


@router.post("/configure", response_model=ConfigureResponse)
def configure_job(request: ConfigureRequest, db: Session = Depends(get_db)) -> ConfigureResponse:
    job = get_job(db, request.job_id)
    summary = parse_json_field(job.upload_summary_json)
    column_names = {column["name"] for column in summary.get("columns", [])}

    required_columns = {request.outcome_column, *request.protected_attributes}
    if request.prediction_column:
        required_columns.add(request.prediction_column)

    missing = sorted(required_columns - column_names)
    if missing:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Columns not present in uploaded data: {', '.join(missing)}",
        )

    update_job_config(db, job, request.model_dump())
    return ConfigureResponse(status="configured", job_id=job.id)


@router.post("/quality-check", response_model=QualityCheckResponse)
def quality_check(request: QualityCheckRequest, db: Session = Depends(get_db)) -> QualityCheckResponse:
    job = get_job(db, request.job_id)
    config = parse_json_field(job.config_json)
    dataframe = read_tabular_file(Path(job.file_path))
    report = run_quality_gate(dataframe, config)
    save_quality_report(db, job, report)
    return QualityCheckResponse(**report)


@router.get("/jobs/{job_id}")
def get_job_details(job_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    job = get_job(db, job_id)
    return {
        "id": job.id,
        "mode": job.mode,
        "status": job.status,
        "filename": job.filename,
        "upload_summary": parse_json_field(job.upload_summary_json),
        "config": parse_json_field(job.config_json),
    }
