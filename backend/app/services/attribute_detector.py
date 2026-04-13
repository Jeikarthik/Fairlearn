from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.schemas.upload import ProtectedAttributeSuggestion
from app.services.normalization import normalize_categorical_series


KEYWORDS = {
    "gender",
    "sex",
    "age",
    "region",
    "district",
    "income",
    "religion",
    "caste",
    "ethnicity",
    "race",
    "location",
}

VALUE_PATTERNS = {
    "gender": {"Male", "Female", "Non-binary"},
    "region": {"Urban", "Rural", "Semi-urban"},
    "caste": {"Sc", "St", "Obc", "General"},
}

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


@dataclass(slots=True)
class DetectionCandidate:
    column: str
    reason: str
    confidence: str


def detect_protected_attributes(df: pd.DataFrame) -> list[ProtectedAttributeSuggestion]:
    suggestions: dict[str, DetectionCandidate] = {}

    for column in df.columns:
        candidate = _detect_for_column(df[column], column)
        if candidate is None:
            continue
        current = suggestions.get(column)
        if current is None or CONFIDENCE_ORDER[candidate.confidence] > CONFIDENCE_ORDER[current.confidence]:
            suggestions[column] = candidate

    return [
        ProtectedAttributeSuggestion(
            column=item.column,
            reason=item.reason,
            confidence=item.confidence,  # type: ignore[arg-type]
        )
        for item in suggestions.values()
    ]


def _detect_for_column(series: pd.Series, column_name: str) -> DetectionCandidate | None:
    lowered_name = column_name.lower().replace("_", " ")
    if any(keyword in lowered_name for keyword in KEYWORDS):
        return DetectionCandidate(
            column=column_name,
            reason=f"Column name matches demographic keyword in '{column_name}'",
            confidence="high",
        )

    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        normalized = normalize_categorical_series(series).dropna()
        unique_values = {str(value) for value in normalized.unique()[:10]}
        for label, expected_values in VALUE_PATTERNS.items():
            if unique_values and unique_values.issubset(expected_values):
                return DetectionCandidate(
                    column=column_name,
                    reason=f"Contains values that resemble {label}: {', '.join(sorted(unique_values))}",
                    confidence="high",
                )

        unique_count = normalized.nunique(dropna=True)
        if 2 <= unique_count <= 10:
            return DetectionCandidate(
                column=column_name,
                reason=f"Low-cardinality categorical column with {unique_count} distinct values",
                confidence="low",
            )

    return None
