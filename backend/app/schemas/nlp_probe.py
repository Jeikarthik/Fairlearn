from typing import Any, Literal

from pydantic import BaseModel, Field


class NLPTargetConfig(BaseModel):
    endpoint: str | None = None
    method: Literal["POST", "PUT"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    prompt_field: str = "prompt"
    response_field: str | None = None
    positive_values: list[str] = Field(default_factory=lambda: ["safe", "approve", "allowed", "positive"])
    negative_values: list[str] = Field(default_factory=lambda: ["unsafe", "deny", "blocked", "negative"])


class AdversarialProbeSetupRequest(BaseModel):
    org_name: str
    system_name: str
    domain: str
    protected_attribute: str
    group_values: list[str]
    scenario_templates: list[str] = Field(default_factory=list)
    target: NLPTargetConfig
    sample_size: int = 12


class ProbePairPreview(BaseModel):
    pair_id: str
    scenario: str
    prompts: dict[str, str]


class AdversarialProbeSetupResponse(BaseModel):
    job_id: str
    mode: Literal["adversarial_nlp_probe"]
    setup_status: Literal["configured"]
    preview_pairs: list[ProbePairPreview]
    operator_note: str


class MockProbeOutcome(BaseModel):
    pair_id: str
    group: str
    response: Any


class ProbeFinding(BaseModel):
    title: str
    summary: str
    evidence: str
    severity: Literal["info", "warning", "critical"]


class AdversarialProbeRunRequest(BaseModel):
    job_id: str
    mock_outcomes: list[MockProbeOutcome] | None = None


class AdversarialProbeRunResponse(BaseModel):
    job_id: str
    status: Literal["complete", "partial", "failed"]
    setup_summary: str
    insight_headline: str
    insight_summary: str
    recommended_action: str
    discrepancy_rate: float
    findings: list[ProbeFinding]
    pair_results: list[dict[str, Any]]
