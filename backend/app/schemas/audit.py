"""Pydantic schemas for audit endpoints.

Updated for schema v3 with all production analysis modules.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field


class AuditRunRequest(BaseModel):
    job_id: str


class AuditRunResponse(BaseModel):
    job_id: str
    status: Literal["complete", "queued", "running", "partial", "failed"]
    estimated_seconds: int = 0


class AuditMetric(BaseModel):
    value: float | None = None
    ci_lower: float | None = None
    ci_upper: float | None = None
    threshold: float | None = None
    passed: bool | None = None
    conclusive: bool = True
    error: str | None = None
    ci_method: str | None = None
    best_group: str | None = None
    worst_group: str | None = None


class SignificanceResult(BaseModel):
    p_value: float | None = None
    significant: bool | None = None
    method: str | None = None
    corrected_p_value: float | None = None
    significant_after_correction: bool | None = None
    correction_method: str | None = None


class AuditAttributeResult(BaseModel):
    metrics: dict[str, AuditMetric]
    group_stats: dict[str, dict[str, Any]]
    overall_passed: bool
    failed_count: int
    significance: SignificanceResult | dict[str, Any] = Field(default_factory=dict)
    failing_groups: list[str] = Field(default_factory=list)


class CompletenessScore(BaseModel):
    total_modules: int = 0
    succeeded: int = 0
    failed: int = 0
    score: float = 0.0


class AuditResultsResponse(BaseModel):
    status: Literal["complete", "partial"]
    results: dict[str, AuditAttributeResult]
    intersectional: dict[str, Any] = Field(default_factory=dict)
    proxy_features: list[dict[str, Any]] = Field(default_factory=list)
    root_cause_analysis: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    mode: str

    # Production analysis modules (all optional — graceful degradation)
    individual_fairness: dict[str, Any] = Field(default_factory=dict)
    fairlearn_crosscheck: dict[str, Any] = Field(default_factory=dict)
    advanced_statistics: dict[str, Any] = Field(default_factory=dict)
    data_diagnostics: dict[str, Any] = Field(default_factory=dict)
    causal_analysis: dict[str, Any] = Field(default_factory=dict)
    calibration_fairness: dict[str, Any] = Field(default_factory=dict)
    counterfactual_fairness: dict[str, Any] = Field(default_factory=dict)
    multi_outcome: dict[str, Any] = Field(default_factory=dict)
    completeness: CompletenessScore | dict[str, Any] = Field(default_factory=dict, alias="_completeness")
    schema_version: int = Field(default=3, alias="_schema_version")

    model_config = {"populate_by_name": True}


class ReportResponse(BaseModel):
    """Extended report response with all analysis sections."""
    executive_summary: str
    attribute_breakdowns: list[dict[str, Any]]
    intersectional_findings: str
    proxy_warnings: str
    causal_findings: str = ""
    counterfactual_findings: str = ""
    data_quality_notes: str = ""
    priority_action: str
    mitigation_cards: list[dict[str, Any]] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict, alias="_validation")

    model_config = {"populate_by_name": True}
