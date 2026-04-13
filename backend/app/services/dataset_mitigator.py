from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd

from app.services.audit_engine import prepare_dataframe


def build_mitigated_csv(df: pd.DataFrame, config: dict[str, Any], method: str) -> str:
    prepared = prepare_dataframe(df, config)
    protected_attributes = config.get("protected_attributes", [])
    if not protected_attributes:
        raise ValueError("At least one protected attribute is required for mitigation.")
    protected = protected_attributes[0]
    if protected not in prepared.columns:
        raise ValueError(f"Protected attribute '{protected}' not found.")

    if method == "reweight":
        return _reweight_csv(prepared, protected)
    if method == "resample":
        return _resample_csv(prepared, protected)
    raise ValueError("method must be 'reweight' or 'resample'")


def _reweight_csv(df: pd.DataFrame, protected: str) -> str:
    counts = df[protected].value_counts(dropna=False)
    max_count = counts.max()
    weighted = df.copy()
    weighted["sample_weight"] = weighted[protected].map(lambda value: round(max_count / counts[value], 4))
    return weighted.to_csv(index=False)


def _resample_csv(df: pd.DataFrame, protected: str) -> str:
    counts = df[protected].value_counts(dropna=False)
    max_count = counts.max()
    frames = []
    for value, group in df.groupby(protected, dropna=False):
        frames.append(group.sample(n=max_count, replace=True, random_state=42))
    balanced = pd.concat(frames, ignore_index=True)
    return balanced.to_csv(index=False)
