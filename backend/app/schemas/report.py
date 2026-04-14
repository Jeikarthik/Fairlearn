from typing import Literal

from pydantic import BaseModel, Field


class TradeoffOption(BaseModel):
    label: str
    projected_accuracy: float | None = None
    projected_disparate_impact: float | None = None
    projected_demographic_parity_gap: float | None = None
    summary: str


class MitigationCard(BaseModel):
    title: str
    severity: Literal["critical", "warning", "info"]
    triggered_by: str
    attribute: str | None = None
    action: str
    tradeoff: str | None = None
    tradeoff_options: list[TradeoffOption] = Field(default_factory=list)


class ReportResponse(BaseModel):
    executive_summary: str
    attribute_breakdowns: list[dict[str, str]]
    intersectional_findings: str
    proxy_warnings: str
    priority_action: str
    mitigation_cards: list[MitigationCard] = Field(default_factory=list)
