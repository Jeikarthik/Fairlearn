from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class BinningStrategy(BaseModel):
    method: Literal["quartile", "custom"] | None = None
    edges: list[float] | None = None

    @field_validator("edges")
    @classmethod
    def validate_edges(cls, value: list[float] | None) -> list[float] | None:
        if value is not None and len(value) < 2:
            raise ValueError("Custom bin edges must include at least two boundaries")
        return value


class ConfigureRequest(BaseModel):
    job_id: str
    outcome_column: str
    prediction_column: str | None = None
    favorable_outcome: Any
    protected_attributes: list[str]
    continuous_binning: dict[str, BinningStrategy] = Field(default_factory=dict)
    reference_groups: dict[str, str] = Field(default_factory=dict)
    org_name: str
    model_name: str
    domain: str
    mode: str | None = None


class ConfigureResponse(BaseModel):
    status: Literal["configured"]
    job_id: str
