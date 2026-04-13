from typing import Any, Literal

from pydantic import BaseModel, Field


class DriftThresholds(BaseModel):
    demographic_parity_gap: float = 0.10
    disparate_impact_ratio: float = 0.80
    alert_window_size: int = 50


class MonitoringSetupRequest(BaseModel):
    org_name: str
    system_name: str
    domain: str
    protected_attributes: list[str]
    prediction_field: str
    outcome_field: str | None = None
    favorable_outcome: Any
    thresholds: DriftThresholds = Field(default_factory=DriftThresholds)


class MonitoringSetupResponse(BaseModel):
    job_id: str
    mode: Literal["continuous_monitoring"]
    setup_status: Literal["configured"]
    operator_note: str
    webhook_path: str


class MonitoringRecord(BaseModel):
    values: dict[str, Any]


class MonitoringWebhookRequest(BaseModel):
    records: list[MonitoringRecord]


class MonitoringAlert(BaseModel):
    title: str
    summary: str
    severity: Literal["info", "warning", "critical"]


class MonitoringStatusResponse(BaseModel):
    job_id: str
    status: Literal["monitoring", "alerting", "configured"]
    records_seen: int
    insight_headline: str
    insight_summary: str
    recommended_action: str
    alerts: list[MonitoringAlert]
    latest_snapshot: dict[str, Any]
