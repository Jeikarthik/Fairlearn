from typing import Any, Literal

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    null_count: int
    unique_count: int
    sample_values: list[Any] = Field(default_factory=list)


class ProtectedAttributeSuggestion(BaseModel):
    column: str
    reason: str
    confidence: Literal["high", "medium", "low"]


class UploadResponse(BaseModel):
    job_id: str
    mode: str
    row_count: int
    preview: list[dict[str, Any]]
    columns: list[ColumnProfile]
    suggested_protected_attributes: list[ProtectedAttributeSuggestion] = Field(default_factory=list)
