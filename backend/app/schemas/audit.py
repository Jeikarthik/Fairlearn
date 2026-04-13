from typing import Any, Literal

from pydantic import BaseModel, Field


class AuditRunRequest(BaseModel):
    job_id: str


class AuditRunResponse(BaseModel):
    job_id: str
    status: Literal["complete"]
    estimated_seconds: int = 0


class AuditMetric(BaseModel):
    value: float | None = None
    ci_lower: float | None = None
    ci_upper: float | None = None
    threshold: float | None = None
    passed: bool | None = None
    conclusive: bool = True
    error: str | None = None


class AuditAttributeResult(BaseModel):
    metrics: dict[str, AuditMetric]
    group_stats: dict[str, dict[str, Any]]
    overall_passed: bool
    failed_count: int


class AuditResultsResponse(BaseModel):
    status: Literal["complete"]
    results: dict[str, AuditAttributeResult]
    intersectional: dict[str, Any] = Field(default_factory=dict)
    proxy_features: list[dict[str, Any]] = Field(default_factory=list)
    root_cause_analysis: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    mode: str
