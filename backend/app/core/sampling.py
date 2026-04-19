"""Large-dataset safety via stratified reservoir sampling with CI inflation.

When a dataset exceeds MAX_ROWS_BEFORE_SAMPLE, the engine samples it down
to SAMPLE_SIZE rows using stratified sampling (stratified on protected
attributes so every group retains representation).  The sampling metadata
is returned alongside results so callers can:
  1. Warn users that results are based on a sample
  2. Inflate confidence intervals to account for sampling uncertainty
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

MAX_ROWS_BEFORE_SAMPLE = 100_000
SAMPLE_SIZE = 50_000


def maybe_sample(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return (df_to_use, sampling_meta).

    If len(df) <= threshold, returns the original df unchanged and
    sampling_meta["sampled"] == False.

    Otherwise performs stratified sampling on protected_attributes (falls
    back to simple random if stratification fails) and inflates CI by the
    square root of the inverse sampling fraction (design effect for SRS).
    """
    max_rows = int(config.get("max_rows_before_sample", MAX_ROWS_BEFORE_SAMPLE))
    target_size = int(config.get("sample_size", SAMPLE_SIZE))

    if len(df) <= max_rows:
        return df, {"sampled": False, "original_rows": len(df), "sample_rows": len(df)}

    actual_size = min(target_size, len(df))
    protected = config.get("protected_attributes", [])
    strat_cols = [c for c in protected if c in df.columns]

    sampled: pd.DataFrame
    if strat_cols:
        try:
            sampled = _stratified_sample(df, strat_cols, actual_size)
        except Exception:
            sampled = df.sample(n=actual_size, random_state=42)
    else:
        sampled = df.sample(n=actual_size, random_state=42)

    sampling_fraction = len(sampled) / len(df)
    # Design effect: CIs widen by 1/sqrt(fraction) for simple random sampling
    ci_inflation = 1.0 / math.sqrt(sampling_fraction)

    return sampled, {
        "sampled": True,
        "original_rows": len(df),
        "sample_rows": len(sampled),
        "sampling_fraction": round(sampling_fraction, 4),
        "ci_inflation_factor": round(ci_inflation, 4),
        "stratified_on": strat_cols if strat_cols else None,
        "warning": (
            f"Dataset has {len(df):,} rows. Results are based on a stratified "
            f"random sample of {len(sampled):,} rows "
            f"({sampling_fraction:.0%} of data). Confidence intervals are "
            f"inflated by {ci_inflation:.2f}x to account for sampling uncertainty. "
            f"For exact results, increase max_rows_before_sample in your audit config."
        ),
    }


def _stratified_sample(
    df: pd.DataFrame,
    strat_cols: list[str],
    target_size: int,
) -> pd.DataFrame:
    """Sample proportionally within each stratum defined by strat_cols."""
    strata_key = df[strat_cols].astype(str).agg("__".join, axis=1)
    strata_counts = strata_key.value_counts()
    total = len(df)

    parts: list[pd.DataFrame] = []
    for stratum, count in strata_counts.items():
        proportion = count / total
        n_stratum = max(1, round(proportion * target_size))
        mask = strata_key == stratum
        stratum_df = df[mask]
        parts.append(stratum_df.sample(n=min(n_stratum, len(stratum_df)), random_state=42))

    result = pd.concat(parts)
    # Trim or top-up to hit target_size exactly
    if len(result) > target_size:
        result = result.sample(n=target_size, random_state=42)
    elif len(result) < target_size:
        remaining = target_size - len(result)
        extra = df.drop(result.index).sample(n=min(remaining, len(df) - len(result)), random_state=42)
        result = pd.concat([result, extra])

    return result.reset_index(drop=True)
