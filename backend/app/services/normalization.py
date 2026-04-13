from __future__ import annotations

import math

import pandas as pd


VALUE_ALIASES = {
    "gender": {
        "m": "Male",
        "male": "Male",
        "man": "Male",
        "f": "Female",
        "female": "Female",
        "woman": "Female",
        "non binary": "Non-binary",
        "non-binary": "Non-binary",
        "nonbinary": "Non-binary",
    },
    "region": {
        "urban": "Urban",
        "rural": "Rural",
        "semi urban": "Semi-urban",
        "semi-urban": "Semi-urban",
    },
}


def normalize_scalar(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if not isinstance(value, str):
        return value

    cleaned = " ".join(value.strip().split())
    return cleaned.title()


def normalize_categorical_series(series: pd.Series, semantic_hint: str | None = None) -> pd.Series:
    normalized = series.map(normalize_scalar)
    if semantic_hint and semantic_hint in VALUE_ALIASES:
        alias_map = VALUE_ALIASES[semantic_hint]
        normalized = normalized.map(
            lambda value: alias_map.get(str(value).strip().lower(), value) if isinstance(value, str) else value
        )
    return normalized


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for column in normalized.columns:
        if pd.api.types.is_object_dtype(normalized[column]) or pd.api.types.is_string_dtype(normalized[column]):
            hint = infer_semantic_hint(column)
            normalized[column] = normalize_categorical_series(normalized[column], semantic_hint=hint)
    return normalized


def infer_semantic_hint(column_name: str) -> str | None:
    lowered = column_name.lower()
    if any(token in lowered for token in ["gender", "sex"]):
        return "gender"
    if any(token in lowered for token in ["region", "district", "location"]):
        return "region"
    return None
