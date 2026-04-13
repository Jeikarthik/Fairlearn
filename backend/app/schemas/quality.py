from typing import Any, Literal

from pydantic import BaseModel, Field


class QualityCheckItem(BaseModel):
    check: str
    status: Literal["pass", "warning", "fail", "info"]
    message: str
    attribute: str | None = None
    column: str | None = None
    group: str | None = None
    value: Any | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class QualityCheckRequest(BaseModel):
    job_id: str


class QualityCheckResponse(BaseModel):
    overall_status: Literal["pass", "pass_with_warnings", "fail"]
    checks: list[QualityCheckItem]
