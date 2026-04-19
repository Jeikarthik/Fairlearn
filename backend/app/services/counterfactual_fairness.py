"""Counterfactual fairness — would the outcome change if only the protected attribute changed?

Addresses deficiency #6: No counterfactual fairness.

Uses nearest-neighbor counterfactual matching with Gower distance, which handles
mixed-type features (numeric + categorical) correctly.  Euclidean distance on
ordinally-encoded categoricals is mathematically wrong because it implies an
ordering and metric structure that doesn't exist.

Gower distance:
  - Numeric features:    |xi - xj| / range(feature)        (Manhattan, range-normalised)
  - Categorical features: 0 if same value, 1 if different  (simple matching)
  Combined: mean over all features, weighted equally.

NOTE: This is nearest-neighbor propensity matching, NOT full causal counterfactual
inference (Kusner et al., 2017).  Full counterfactual fairness requires a
user-specified causal DAG.  Results here are a rigorous approximation useful for
auditing purposes.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def compute_counterfactual_fairness(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Gower-distance nearest-neighbor counterfactual fairness analysis.

    For each individual:
      1. Find the nearest neighbor from EACH other group, matching on
         all non-protected features using Gower distance.
      2. Compare outcomes: did they get different results?
      3. Aggregate: what fraction of matched pairs have different outcomes?

    A high counterfactual flip rate = "changing only the protected
    attribute leads to different outcomes" = unfair.
    """
    outcome_col = config["outcome_column"]
    favorable = config["favorable_outcome"]
    protected = config.get("protected_attributes", [])
    pred_col = config.get("prediction_column")

    target_col = pred_col or outcome_col
    feature_cols = [
        c for c in df.columns
        if c not in {outcome_col, pred_col, *protected}
    ]

    if not feature_cols:
        return {"_meta": {"status": "skipped", "reason": "No features for matching."}}

    work = df[feature_cols + [target_col] + [a for a in protected if a in df.columns]].dropna()
    if len(work) < 20:
        return {"_meta": {"status": "skipped", "reason": "Too few rows for counterfactual analysis."}}

    # Precompute Gower metadata (ranges for numeric, identity for categorical)
    gower_meta = _gower_metadata(work[feature_cols])

    # Binary outcome
    if pd.api.types.is_numeric_dtype(work[target_col]):
        try:
            outcomes = (work[target_col] == float(favorable)).astype(int).values
        except (ValueError, TypeError):
            outcomes = (work[target_col].astype(str) == str(favorable)).astype(int).values
    else:
        outcomes = (work[target_col].astype(str) == str(favorable)).astype(int).values

    results: dict[str, Any] = {"_meta": {"status": "success", "distance_metric": "gower"}}

    for attr in protected:
        if attr not in work.columns:
            continue
        groups = work[attr].astype(str).values
        unique_groups = np.unique(groups)
        if len(unique_groups) < 2:
            continue

        feat_array = work[feature_cols].reset_index(drop=True)
        total_pairs = 0
        flipped_pairs = 0
        group_flip_rates: dict[str, dict[str, Any]] = {}

        for g in unique_groups:
            g_mask = groups == g
            g_feat = feat_array[g_mask].reset_index(drop=True)
            g_outcomes = outcomes[g_mask]
            other_mask = ~g_mask
            other_feat = feat_array[other_mask].reset_index(drop=True)
            other_outcomes = outcomes[other_mask]

            if len(g_feat) == 0 or len(other_feat) == 0:
                continue

            # Compute Gower distance matrix: shape (len(g_feat), len(other_feat))
            distances, matched_idx = _gower_nearest_neighbor(g_feat, other_feat, gower_meta)

            matched_outcomes = other_outcomes[matched_idx]
            n_matched = len(g_outcomes)
            n_flipped = int((g_outcomes != matched_outcomes).sum())
            flip_rate = n_flipped / max(1, n_matched)

            flips_unfavorable = int(((g_outcomes == 0) & (matched_outcomes == 1)).sum())
            flips_favorable = int(((g_outcomes == 1) & (matched_outcomes == 0)).sum())

            group_flip_rates[g] = {
                "matched_pairs": n_matched,
                "flipped": n_flipped,
                "flip_rate": round(flip_rate, 4),
                "flips_unfavorable": flips_unfavorable,
                "flips_favorable": flips_favorable,
                "avg_match_distance": round(float(distances.mean()), 4),
            }

            total_pairs += n_matched
            flipped_pairs += n_flipped

        overall_flip_rate = flipped_pairs / max(1, total_pairs)

        most_unfavorable = (
            max(group_flip_rates, key=lambda g: group_flip_rates[g]["flips_unfavorable"])
            if group_flip_rates
            else None
        )

        results[attr] = {
            "overall_flip_rate": round(overall_flip_rate, 4),
            "total_matched_pairs": total_pairs,
            "total_flipped": flipped_pairs,
            "passed": overall_flip_rate < 0.15,
            "threshold": 0.15,
            "group_details": group_flip_rates,
            "most_disadvantaged_group": most_unfavorable,
            "interpretation": (
                f"Counterfactual flip rate: {overall_flip_rate:.1%} (Gower distance matching). "
                + (
                    "Similar individuals across groups generally receive similar outcomes."
                    if overall_flip_rate < 0.15
                    else f"When we match similar people across '{attr}' groups, "
                         f"{overall_flip_rate:.0%} get DIFFERENT outcomes — meaning "
                         f"the protected attribute itself likely influences the decision."
                         + (f" '{most_unfavorable}' is most disadvantaged by these flips."
                            if most_unfavorable else "")
                )
            ),
        }

    return results


# ── Gower distance helpers ────────────────────────────────────────


def _gower_metadata(df: pd.DataFrame) -> dict[str, Any]:
    """Precompute per-column metadata needed for Gower distance.

    Returns a dict with:
      numeric_cols: list of column names that are numeric
      categorical_cols: list of column names that are categorical
      ranges: {col: range_value} for numeric cols (0 → skip that column)
    """
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    categorical_cols = [c for c in df.columns if c not in numeric_cols]

    ranges: dict[str, float] = {}
    for col in numeric_cols:
        col_range = float(df[col].max() - df[col].min())
        ranges[col] = col_range if col_range > 0 else 1.0  # avoid /0

    return {
        "numeric_cols": numeric_cols,
        "categorical_cols": categorical_cols,
        "ranges": ranges,
        "n_features": len(df.columns),
    }


def _gower_nearest_neighbor(
    query_df: pd.DataFrame,
    reference_df: pd.DataFrame,
    meta: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    """Find the nearest reference row for each query row using Gower distance.

    Returns (distances, indices) where distances[i] is the Gower distance to
    the nearest reference and indices[i] is its row index in reference_df.

    Complexity: O(|query| × |reference| × n_features).
    For very large groups this can be expensive; the caller already filters
    to ≥20 rows which keeps this tractable for audit-scale datasets.
    """
    numeric_cols = meta["numeric_cols"]
    categorical_cols = meta["categorical_cols"]
    ranges = meta["ranges"]
    n_features = meta["n_features"]

    if n_features == 0:
        return np.zeros(len(query_df)), np.zeros(len(query_df), dtype=int)

    n_q = len(query_df)
    n_r = len(reference_df)

    # Build numeric contribution matrix
    dist_matrix = np.zeros((n_q, n_r), dtype=np.float64)

    for col in numeric_cols:
        q_vals = query_df[col].fillna(0).values.reshape(-1, 1).astype(float)
        r_vals = reference_df[col].fillna(0).values.reshape(1, -1).astype(float)
        col_dist = np.abs(q_vals - r_vals) / ranges[col]
        dist_matrix += col_dist

    for col in categorical_cols:
        q_vals = query_df[col].fillna("__missing__").astype(str).values
        r_vals = reference_df[col].fillna("__missing__").astype(str).values
        # Broadcasting: (n_q, 1) != (1, n_r) → (n_q, n_r) bool
        mismatch = (q_vals.reshape(-1, 1) != r_vals.reshape(1, -1)).astype(float)
        dist_matrix += mismatch

    gower_dist = dist_matrix / n_features

    nearest_idx = np.argmin(gower_dist, axis=1)
    nearest_dist = gower_dist[np.arange(n_q), nearest_idx]

    return nearest_dist, nearest_idx
