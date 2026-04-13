from typing import Any, Literal

from pydantic import BaseModel, Field


class ProbeAuthConfig(BaseModel):
    type: Literal["none", "bearer", "api_key_header", "api_key_query", "basic"] = "none"
    key_name: str | None = None
    key_value: str | None = None
    username: str | None = None
    password: str | None = None


class ApiProbeSetupRequest(BaseModel):
    org_name: str
    system_name: str
    domain: str
    api_endpoint: str | None = None
    method: Literal["POST", "PUT"] = "POST"
    input_schema: dict[str, str]
    protected_attribute: str
    group_values: list[str]
    decision_field: str | None = None
    positive_values: list[str] = Field(default_factory=lambda: ["approve", "allow", "accept", "positive", "1"])
    negative_values: list[str] = Field(default_factory=lambda: ["deny", "reject", "block", "negative", "0"])
    auth: ProbeAuthConfig = Field(default_factory=ProbeAuthConfig)
    num_test_pairs: int = 12


class ApiProbeSetupResponse(BaseModel):
    job_id: str
    mode: Literal["api_probe"]
    setup_status: Literal["configured"]
    preview_cases: list[dict[str, Any]]
    operator_note: str


class ApiProbeMockOutcome(BaseModel):
    pair_id: str
    group: str
    response: Any


class ApiProbeRunRequest(BaseModel):
    job_id: str
    mock_outcomes: list[ApiProbeMockOutcome] | None = None


class ApiProbeRunResponse(BaseModel):
    job_id: str
    status: Literal["complete", "partial", "failed"]
    insight_headline: str
    insight_summary: str
    recommended_action: str
    discrepancy_rate: float
    findings: list[dict[str, Any]]
    pair_results: list[dict[str, Any]]
