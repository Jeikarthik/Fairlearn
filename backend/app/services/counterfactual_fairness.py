"""Counterfactual fairness — would the outcome change if only the protected attribute changed?

Addresses deficiency #6: No counterfactual fairness.

Uses nearest-neighbor counterfactual matching: for each individual,
find the closest person from a different group and compare outcomes.
This is a practical approximation of full causal counterfactual inference
without requiring a causal DAG specification.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import OrdinalEncoder, StandardScaler


def compute_counterfactual_fairness(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Nearest-neighbor counterfactual fairness analysis.

    For each individual:
      1. Find the nearest neighbor from EACH other group
         (matching on all non-protected features)
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

    # Encode features
    X = _encode_features(work[feature_cols])
    if X is None or X.shape[1] == 0:
        return {"_meta": {"status": "skipped", "reason": "Could not encode features."}}

    # Binary outcome
    if pd.api.types.is_numeric_dtype(work[target_col]):
        try:
            outcomes = (work[target_col] == float(favorable)).astype(int).values
        except (ValueError, TypeError):
            outcomes = (work[target_col].astype(str) == str(favorable)).astype(int).values
    else:
        outcomes = (work[target_col].astype(str) == str(favorable)).astype(int).values

    results: dict[str, Any] = {"_meta": {"status": "success"}}

    for attr in protected:
        if attr not in work.columns:
            continue
        groups = work[attr].astype(str).values
        unique_groups = np.unique(groups)
        if len(unique_groups) < 2:
            continue

        total_pairs = 0
        flipped_pairs = 0
        group_flip_rates: dict[str, dict[str, Any]] = {}

        for g in unique_groups:
            g_mask = groups == g
            g_X = X[g_mask]
            g_outcomes = outcomes[g_mask]
            other_mask = ~g_mask
            other_X = X[other_mask]
            other_outcomes = outcomes[other_mask]

            if len(g_X) == 0 or len(other_X) == 0:
                continue

            # Find nearest neighbor in the other group(s)
            nn = NearestNeighbors(n_neighbors=1, algorithm="auto")
            nn.fit(other_X)
            distances, indices = nn.kneighbors(g_X)

            matched_outcomes = other_outcomes[indices.flatten()]
            n_matched = len(g_outcomes)
            n_flipped = int((g_outcomes != matched_outcomes).sum())
            flip_rate = n_flipped / max(1, n_matched)

            # Of flips, how many went unfavorable for this group?
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

        # Determine if there's directional unfairness
        if group_flip_rates:
            most_unfavorable = max(
                group_flip_rates,
                key=lambda g: group_flip_rates[g]["flips_unfavorable"]
            )
        else:
            most_unfavorable = None

        results[attr] = {
            "overall_flip_rate": round(overall_flip_rate, 4),
            "total_matched_pairs": total_pairs,
            "total_flipped": flipped_pairs,
            "passed": overall_flip_rate < 0.15,
            "threshold": 0.15,
            "group_details": group_flip_rates,
            "most_disadvantaged_group": most_unfavorable,
            "interpretation": (
                f"Counterfactual flip rate: {overall_flip_rate:.1%}. "
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


def _encode_features(df: pd.DataFrame) -> np.ndarray | None:
    """Encode mixed-type features to numeric for distance computation."""
    numeric = df.select_dtypes(include=[np.number])
    categorical = df.select_dtypes(exclude=[np.number])
    parts: list[np.ndarray] = []
    try:
        if not numeric.empty:
            scaled = StandardScaler().fit_transform(numeric.fillna(0).values)
            parts.append(scaled)
        if not categorical.empty:
            encoded = OrdinalEncoder(
                handle_unknown="use_encoded_value", unknown_value=-1
            ).fit_transform(categorical.fillna("__missing__").values)
            parts.append(encoded)
    except Exception:  # noqa: BLE001
        return None
    return np.hstack(parts) if parts else None
