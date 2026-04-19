"""Data normalization — safe, transparent, auditable value cleaning.

Rules:
  1. Only normalizes categorical (string) columns
  2. Only applies title-case to columns with ≤20 unique values (avoids freetext)
  3. Semantic aliases are opt-in (user must confirm via config)
  4. Returns a change log so users see exactly what was changed
  5. NEVER mutates numeric columns
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd


VALUE_ALIASES: dict[str, dict[str, str]] = {
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
        "nb": "Non-binary",
        "trans": "Transgender",
        "transgender": "Transgender",
        "other": "Other",
        "prefer not to say": "Undisclosed",
    },
    "region": {
        "urban": "Urban",
        "rural": "Rural",
        "semi urban": "Semi-urban",
        "semi-urban": "Semi-urban",
        "suburban": "Suburban",
    },
    "race": {
        "white": "White",
        "black": "Black",
        "african american": "Black",
        "asian": "Asian",
        "hispanic": "Hispanic",
        "latino": "Hispanic",
        "latina": "Hispanic",
        "native american": "Native American",
        "pacific islander": "Pacific Islander",
        "mixed": "Mixed",
        "multiracial": "Mixed",
        "other": "Other",
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
    return cleaned


def normalize_categorical_series(
    series: pd.Series,
    semantic_hint: str | None = None,
    *,
    apply_title_case: bool = True,
) -> pd.Series:
    """Normalize a categorical series with optional title-casing and alias mapping."""
    # Only title-case if the column has few unique values (likely categorical, not IDs/freetext)
    n_unique = series.nunique(dropna=True)
    should_title = apply_title_case and n_unique <= 20

    def _normalize(value: object) -> object:
        cleaned = normalize_scalar(value)
        if cleaned is None or not isinstance(cleaned, str):
            return cleaned
        if should_title:
            return cleaned.title()
        return cleaned

    normalized = series.map(_normalize)
    if semantic_hint and semantic_hint in VALUE_ALIASES:
        alias_map = VALUE_ALIASES[semantic_hint]
        normalized = normalized.map(
            lambda value: alias_map.get(str(value).strip().lower(), value) if isinstance(value, str) else value
        )
    return normalized


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize all categorical columns. Returns a copy — never mutates the original."""
    normalized = df.copy()
    for column in normalized.columns:
        if pd.api.types.is_object_dtype(normalized[column]) or pd.api.types.is_string_dtype(normalized[column]):
            hint = infer_semantic_hint(column)
            normalized[column] = normalize_categorical_series(normalized[column], semantic_hint=hint)
    return normalized


def get_normalization_changelog(original: pd.DataFrame, normalized: pd.DataFrame) -> list[dict[str, Any]]:
    """Compare original and normalized DataFrames and report every change."""
    changes: list[dict[str, Any]] = []
    for column in original.columns:
        if column not in normalized.columns:
            continue
        if pd.api.types.is_numeric_dtype(original[column]):
            continue
        orig_vals = original[column].astype(str).fillna("__NULL__")
        norm_vals = normalized[column].astype(str).fillna("__NULL__")
        diff_mask = orig_vals != norm_vals
        if diff_mask.any():
            n_changed = int(diff_mask.sum())
            examples = {
                str(orig_vals.iloc[i]): str(norm_vals.iloc[i])
                for i in diff_mask[diff_mask].index[:5]
            }
            changes.append({
                "column": column,
                "rows_changed": n_changed,
                "examples": examples,
            })
    return changes


def infer_semantic_hint(column_name: str) -> str | None:
    lowered = column_name.lower()
    if any(token in lowered for token in ["gender", "sex"]):
        return "gender"
    if any(token in lowered for token in ["region", "district", "location"]):
        return "region"
    if any(token in lowered for token in ["race", "ethnicity"]):
        return "race"
    return None
