"""Audit configuration validation — stops bad configs before they reach the engine.

Validates:
  - Required fields exist
  - outcome_column and protected_attributes are in the dataframe
  - favorable_outcome is a real value in the outcome column
  - protected_attributes count is capped (prevents combinatorial explosion)
  - continuous_binning references real columns
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# Limits to prevent resource exhaustion
MAX_PROTECTED_ATTRIBUTES = 8
MAX_CONTINUOUS_BINNING = 10


class AuditConfig(BaseModel):
    """Validated audit configuration. Reject bad configs before engine runs."""

    outcome_column: str
    favorable_outcome: Any
    protected_attributes: list[str] = Field(min_length=1, max_length=MAX_PROTECTED_ATTRIBUTES)
    prediction_column: str | None = None
    mode: str = "dataset"
    domain: str = "general"
    org_name: str = ""
    model_name: str = ""
    continuous_binning: dict[str, Any] = Field(default_factory=dict)
    model_artifact_path: str | None = None

    @field_validator("protected_attributes")
    @classmethod
    def no_duplicate_attributes(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("protected_attributes contains duplicates")
        return v

    @field_validator("continuous_binning")
    @classmethod
    def limit_binning(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(v) > MAX_CONTINUOUS_BINNING:
            raise ValueError(f"continuous_binning cannot have more than {MAX_CONTINUOUS_BINNING} entries")
        return v


def validate_config_against_dataframe(config: dict[str, Any], columns: list[str]) -> list[str]:
    """Validate config against actual DataFrame columns. Returns list of errors."""
    errors: list[str] = []

    outcome = config.get("outcome_column")
    if outcome and outcome not in columns:
        errors.append(f"outcome_column '{outcome}' not found in dataset. Available: {columns[:10]}")

    prediction = config.get("prediction_column")
    if prediction and prediction not in columns:
        errors.append(f"prediction_column '{prediction}' not found in dataset. Available: {columns[:10]}")

    for attr in config.get("protected_attributes", []):
        if attr not in columns:
            errors.append(f"protected_attribute '{attr}' not found in dataset.")

    for col in config.get("continuous_binning", {}):
        if col not in columns:
            errors.append(f"continuous_binning column '{col}' not found in dataset.")

    return errors


def validate_favorable_outcome(config: dict[str, Any], unique_values: list[Any]) -> list[str]:
    """Validate that favorable_outcome is a real value in the outcome column."""
    fav = config.get("favorable_outcome")
    if fav is None:
        return ["favorable_outcome is required"]

    # Try both string and type-coerced comparison
    str_vals = [str(v) for v in unique_values]
    if str(fav) not in str_vals and fav not in unique_values:
        return [
            f"favorable_outcome '{fav}' not found in outcome column. "
            f"Available values: {unique_values[:10]}"
        ]
    return []
