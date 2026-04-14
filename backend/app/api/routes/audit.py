from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.schemas.api_probe import ApiProbeRunRequest, ApiProbeRunResponse, ApiProbeSetupRequest, ApiProbeSetupResponse
from app.core.config import get_settings
from app.core.database import get_db
from app.models.job import AuditJob
from app.schemas.aggregate import AggregateRequest, AggregateResponse
from app.schemas.audit import AuditResultsResponse, AuditRunRequest, AuditRunResponse
from app.schemas.configure import ConfigureRequest, ConfigureResponse
from app.schemas.history import CompareHistoryResponse
from app.schemas.model_artifact import ModelUploadResponse
from app.schemas.monitoring import (
    MonitoringSetupRequest,
    MonitoringSetupResponse,
    MonitoringStatusResponse,
    MonitoringWebhookRequest,
)
from app.schemas.nlp_probe import (
    AdversarialProbeRunRequest,
    AdversarialProbeRunResponse,
    AdversarialProbeSetupRequest,
    AdversarialProbeSetupResponse,
)
from app.schemas.quality import QualityCheckRequest, QualityCheckResponse
from app.schemas.report import ReportResponse
from app.schemas.sample import SamplesResponse
from app.schemas.upload import UploadResponse
from app.services.api_prober import build_api_probe_pairs, run_api_probe
from app.services.audit_engine import run_aggregate_audit, run_audit
from app.services.dataset_mitigator import build_mitigated_csv
from app.services.file_parser import build_upload_summary, read_tabular_file, save_binary_upload, save_upload
from app.services.gemini_service import generate_validated_report
from app.services.job_service import (
    create_upload_job,
    get_job,
    parse_json_field,
    save_quality_report,
    update_job_config,
    update_job_results,
)
from app.services.monitoring import create_monitor_state, ingest_monitoring_records, summarize_monitor_state
from app.services.nlp_probe import build_probe_pairs, run_probe
from app.services.quality_gate import run_quality_gate
from app.services.reporting import build_pdf_bytes, build_report
from app.services.samples import ensure_sample_datasets

router = APIRouter()
settings = get_settings()


def _extract_audit_payload(results: dict[str, object]) -> dict[str, object]:
    if "audit" in results:
        return results["audit"]  # type: ignore[return-value]
    return results


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


@router.post("/aggregate", response_model=AggregateResponse)
def aggregate_input(request: AggregateRequest, db: Session = Depends(get_db)) -> AggregateResponse:
    summary = {"aggregate_input": request.model_dump()}
    job = create_upload_job(
        db,
        mode="aggregate",
        filename=None,
        file_path=None,
        upload_summary=summary,
    )
    update_job_config(
        db,
        job,
        {
            "org_name": request.org_name,
            "model_name": request.model_name,
            "domain": request.domain,
            "attribute_name": request.attribute_name,
            "groups": [group.model_dump() for group in request.groups],
            "mode": "aggregate",
        },
    )
    return AggregateResponse(job_id=job.id, mode="aggregate")


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
        raise HTTPException(
            status_code=400,
            detail=f"Columns not present in uploaded data: {', '.join(missing)}",
        )

    update_job_config(db, job, request.model_dump())
    return ConfigureResponse(status="configured", job_id=job.id)


@router.post("/model/upload", response_model=ModelUploadResponse)
def upload_model_artifact(
    job_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ModelUploadResponse:
    job = get_job(db, job_id)
    model_path = save_binary_upload(
        file,
        allowed_suffixes={".pkl", ".pickle", ".joblib"},
        target_dir=settings.upload_dir / "models",
    )
    config = parse_json_field(job.config_json)
    config["model_artifact_path"] = str(model_path)
    update_job_config(db, job, config)
    return ModelUploadResponse(job_id=job.id, filename=file.filename or model_path.name, status="uploaded")


@router.post("/quality-check", response_model=QualityCheckResponse)
def quality_check(request: QualityCheckRequest, db: Session = Depends(get_db)) -> QualityCheckResponse:
    job = get_job(db, request.job_id)
    config = parse_json_field(job.config_json)
    dataframe = read_tabular_file(Path(job.file_path))
    report = run_quality_gate(dataframe, config)
    save_quality_report(db, job, report)
    return QualityCheckResponse(**report)


@router.post("/audit/run", response_model=AuditRunResponse)
def run_audit_job(request: AuditRunRequest, db: Session = Depends(get_db)) -> AuditRunResponse:
    job = get_job(db, request.job_id)
    config = parse_json_field(job.config_json)
    if job.mode == "aggregate":
        results = run_aggregate_audit(config)
    else:
        if not job.file_path:
            raise HTTPException(status_code=400, detail="This job does not have an uploaded dataset.")
        dataframe = read_tabular_file(Path(job.file_path))
        results = run_audit(dataframe, config, model_path=config.get("model_artifact_path"))
    update_job_results(db, job, results, status="complete")
    return AuditRunResponse(job_id=job.id, status="complete", estimated_seconds=0)


@router.get("/audit/{job_id}", response_model=AuditResultsResponse)
def get_audit_results(job_id: str, db: Session = Depends(get_db)) -> AuditResultsResponse:
    job = get_job(db, job_id)
    results = _extract_audit_payload(parse_json_field(job.results_json))
    if not results:
        raise HTTPException(status_code=404, detail="Audit results not found for this job.")
    return AuditResultsResponse(**results)


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
        "results": parse_json_field(job.results_json),
    }


@router.get("/history")
def list_history(db: Session = Depends(get_db)) -> dict[str, object]:
    jobs = db.execute(select(AuditJob).order_by(AuditJob.created_at.desc())).scalars().all()
    audits = []
    for job in jobs:
        results = _extract_audit_payload(parse_json_field(job.results_json))
        overall_passed = None
        if results.get("results"):
            overall_passed = all(item.get("overall_passed", False) for item in results["results"].values())
        audits.append(
            {
                "id": job.id,
                "mode": job.mode,
                "status": job.status,
                "filename": job.filename,
                "overall_passed": overall_passed,
                "created_at": job.created_at.isoformat(),
            }
        )
    return {"audits": audits}


@router.get("/history/compare", response_model=CompareHistoryResponse)
def compare_history(job_id_old: str = Query(...), job_id_new: str = Query(...), db: Session = Depends(get_db)) -> CompareHistoryResponse:
    old_job = get_job(db, job_id_old)
    new_job = get_job(db, job_id_new)
    old_results = _extract_audit_payload(parse_json_field(old_job.results_json))
    new_results = _extract_audit_payload(parse_json_field(new_job.results_json))
    comparisons = []
    for attribute, new_payload in new_results.get("results", {}).items():
        old_payload = old_results.get("results", {}).get(attribute)
        if not old_payload:
            continue
        for metric, new_metric in new_payload.get("metrics", {}).items():
            old_metric = old_payload.get("metrics", {}).get(metric)
            if not old_metric:
                continue
            old_value = old_metric.get("value")
            new_value = new_metric.get("value")
            if old_value is None or new_value is None:
                continue
            delta = round(new_value - old_value, 4)
            comparisons.append(
                {
                    "attribute": attribute,
                    "metric": metric,
                    "old_value": old_value,
                    "new_value": new_value,
                    "direction": "improved" if delta > 0 else "worsened" if delta < 0 else "unchanged",
                    "delta": delta,
                    "old_status": "pass" if old_metric.get("passed") else "fail",
                    "new_status": "pass" if new_metric.get("passed") else "fail",
                }
            )
    return CompareHistoryResponse(comparisons=comparisons)


@router.get("/samples", response_model=SamplesResponse)
def get_samples() -> SamplesResponse:
    datasets = ensure_sample_datasets(Path("sample_data"))
    return SamplesResponse(datasets=datasets)


@router.get("/samples/{sample_id}/download")
def download_sample(sample_id: str) -> Response:
    datasets = ensure_sample_datasets(Path("sample_data"))
    match = next((item for item in datasets if item["id"] == sample_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Sample dataset not found.")
    sample_path = Path(str(match["path"]))
    filename = f"{sample_id}.csv"
    return Response(
        content=sample_path.read_text(encoding="utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/probe/configure", response_model=ApiProbeSetupResponse)
def configure_api_probe(request: ApiProbeSetupRequest, db: Session = Depends(get_db)) -> ApiProbeSetupResponse:
    config = request.model_dump()
    preview_cases = build_api_probe_pairs(config)
    job = create_upload_job(
        db,
        mode="api_probe",
        filename=None,
        file_path=None,
        upload_summary={"preview_cases": preview_cases[:3]},
    )
    config["job_id"] = job.id
    update_job_config(db, job, config)
    return ApiProbeSetupResponse(
        job_id=job.id,
        mode="api_probe",
        setup_status="configured",
        preview_cases=preview_cases[:3],
        operator_note="Technical setup is stored. Later users can review plain-language probe findings without touching API configuration.",
    )


@router.post("/probe/run", response_model=ApiProbeRunResponse)
def execute_api_probe(request: ApiProbeRunRequest, db: Session = Depends(get_db)) -> ApiProbeRunResponse:
    job = get_job(db, request.job_id)
    config = parse_json_field(job.config_json)
    config["job_id"] = job.id
    results = run_api_probe(config, mock_outcomes=[item.model_dump() for item in (request.mock_outcomes or [])])
    update_job_results(db, job, results, status=results["status"])
    return ApiProbeRunResponse(**results)


@router.get("/probe/{job_id}", response_model=ApiProbeRunResponse)
def get_api_probe(job_id: str, db: Session = Depends(get_db)) -> ApiProbeRunResponse:
    job = get_job(db, job_id)
    results = parse_json_field(job.results_json)
    return ApiProbeRunResponse(**results)


@router.post("/report/generate", response_model=ReportResponse)
def generate_report(request: AuditRunRequest, db: Session = Depends(get_db)) -> ReportResponse:
    job = get_job(db, request.job_id)
    config = parse_json_field(job.config_json)
    config["job_file_path"] = job.file_path
    config["mode"] = job.mode
    current_results = parse_json_field(job.results_json)
    results = _extract_audit_payload(current_results)
    if not results:
        raise HTTPException(status_code=404, detail="Run the audit before generating a report.")
    report = generate_validated_report(config, results)
    merged = {"audit": results, "report": report}
    update_job_results(db, job, merged, status=job.status)
    return ReportResponse(**report)


@router.get("/report/{job_id}/pdf")
def download_report_pdf(job_id: str, db: Session = Depends(get_db)) -> Response:
    job = get_job(db, job_id)
    results = parse_json_field(job.results_json)
    report = results.get("report")
    audit_payload = _extract_audit_payload(results)
    if not report:
        if not audit_payload:
            raise HTTPException(status_code=404, detail="No audit or report found for this job.")
        config = parse_json_field(job.config_json)
        config["job_file_path"] = job.file_path
        config["mode"] = job.mode
        report = build_report(config, audit_payload)
    pdf_bytes = build_pdf_bytes(report, title="FairLens Audit Report")
    filename = f"FairLens_Audit_{job_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/mitigate/{job_id}/download")
def download_mitigated_dataset(job_id: str, method: str = Query(...), db: Session = Depends(get_db)) -> Response:
    job = get_job(db, job_id)
    if not job.file_path:
        raise HTTPException(status_code=400, detail="Mitigation downloads are only available for file-based jobs.")
    dataframe = read_tabular_file(Path(job.file_path))
    config = parse_json_field(job.config_json)
    try:
        csv_content = build_mitigated_csv(dataframe, config, method)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"FairLens_Mitigated_{method}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/nlp-probe/setup", response_model=AdversarialProbeSetupResponse)
def setup_nlp_probe(request: AdversarialProbeSetupRequest, db: Session = Depends(get_db)) -> AdversarialProbeSetupResponse:
    config = request.model_dump()
    preview_pairs = build_probe_pairs(config)
    job = create_upload_job(
        db,
        mode="adversarial_nlp_probe",
        filename=None,
        file_path=None,
        upload_summary={"preview_pairs": preview_pairs[:3]},
    )
    config["job_id"] = job.id
    update_job_config(db, job, config)
    return AdversarialProbeSetupResponse(
        job_id=job.id,
        mode="adversarial_nlp_probe",
        setup_status="configured",
        preview_pairs=preview_pairs[:3],
        operator_note=(
            "Technical setup is complete. Non-technical reviewers will later see plain-language findings instead of raw "
            "prompt payloads."
        ),
    )


@router.post("/nlp-probe/run", response_model=AdversarialProbeRunResponse)
def execute_nlp_probe(request: AdversarialProbeRunRequest, db: Session = Depends(get_db)) -> AdversarialProbeRunResponse:
    job = get_job(db, request.job_id)
    config = parse_json_field(job.config_json)
    config["job_id"] = job.id
    results = run_probe(config, mock_outcomes=[item.model_dump() for item in (request.mock_outcomes or [])])
    update_job_results(db, job, results, status=results["status"])
    return AdversarialProbeRunResponse(**results)


@router.get("/nlp-probe/{job_id}", response_model=AdversarialProbeRunResponse)
def get_nlp_probe(job_id: str, db: Session = Depends(get_db)) -> AdversarialProbeRunResponse:
    job = get_job(db, job_id)
    results = parse_json_field(job.results_json)
    return AdversarialProbeRunResponse(**results)


@router.post("/monitor/setup", response_model=MonitoringSetupResponse)
def setup_monitoring(request: MonitoringSetupRequest, db: Session = Depends(get_db)) -> MonitoringSetupResponse:
    config = request.model_dump()
    job = create_upload_job(
        db,
        mode="continuous_monitoring",
        filename=None,
        file_path=None,
        upload_summary={"monitoring_scope": request.protected_attributes},
    )
    update_job_config(db, job, config)
    state = create_monitor_state(config)
    update_job_results(db, job, state, status="configured")
    return MonitoringSetupResponse(
        job_id=job.id,
        mode="continuous_monitoring",
        setup_status="configured",
        operator_note=(
            "A technical owner only needs to connect the webhook once. After that, FairLens can keep translating fairness "
            "drift into plain-language updates."
        ),
        webhook_path=f"/api/webhook/predict/{job.id}",
    )


@router.post("/webhook/predict/{job_id}", response_model=MonitoringStatusResponse)
def ingest_monitor_event(
    job_id: str,
    request: MonitoringWebhookRequest,
    db: Session = Depends(get_db),
) -> MonitoringStatusResponse:
    job = get_job(db, job_id)
    config = parse_json_field(job.config_json)
    state = parse_json_field(job.results_json)
    new_state = ingest_monitoring_records(
        config,
        state,
        [record.values for record in request.records],
    )
    update_job_results(db, job, new_state, status=new_state["latest_status"])
    summary = summarize_monitor_state(job.id, config, new_state)
    return MonitoringStatusResponse(**summary)


@router.get("/monitor/{job_id}", response_model=MonitoringStatusResponse)
def get_monitoring_status(job_id: str, db: Session = Depends(get_db)) -> MonitoringStatusResponse:
    job = get_job(db, job_id)
    config = parse_json_field(job.config_json)
    state = parse_json_field(job.results_json)
    summary = summarize_monitor_state(job.id, config, state)
    return MonitoringStatusResponse(**summary)
