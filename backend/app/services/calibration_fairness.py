"""Calibration fairness — detect when probability models are mis-calibrated per group.

Addresses deficiency #5: No calibration fairness.

When a model outputs a 70% probability of approval, it should mean 70%
for ALL demographic groups.  If it means 70% for Group A but only 50%
for Group B, the model has calibration disparity — one of the most
insidious forms of bias (cf. ProPublica's COMPAS analysis).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def compute_calibration_fairness(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Check calibration parity across protected groups.

    Requires either:
      - A prediction_column with probability scores (0-1 or 0-100)
      - Or a score_column explicitly specified in config

    Bins predicted scores into deciles, computes actual positive rate
    per bin per group, then measures calibration disparity.
    """
    outcome_col = config["outcome_column"]
    favorable = config["favorable_outcome"]
    score_col = config.get("score_column") or config.get("prediction_column")
    protected = config.get("protected_attributes", [])

    if not score_col or score_col not in df.columns:
        return {"_meta": {"status": "skipped", "reason": "No score/prediction column for calibration check."}}

    if not pd.api.types.is_numeric_dtype(df[score_col]):
        return {"_meta": {"status": "skipped", "reason": f"'{score_col}' is not numeric — cannot compute calibration."}}

    # Prepare binary outcome
    if pd.api.types.is_numeric_dtype(df[outcome_col]):
        try:
            y_true = (df[outcome_col] == float(favorable)).astype(int)
        except (ValueError, TypeError):
            y_true = (df[outcome_col].astype(str) == str(favorable)).astype(int)
    else:
        y_true = (df[outcome_col].astype(str) == str(favorable)).astype(int)

    scores = df[score_col].values.astype(float)

    # Normalize to 0-1 if scores appear to be 0-100
    if scores.max() > 1.5:
        scores = scores / 100.0

    n_bins = min(10, max(3, len(df) // 50))

    results: dict[str, Any] = {"_meta": {"status": "success"}, "n_bins": n_bins}

    for attr in protected:
        if attr not in df.columns:
            continue
        groups = df[attr].dropna().unique()
        if len(groups) < 2:
            continue

        group_calibrations: dict[str, list[dict[str, Any]]] = {}
        group_ece: dict[str, float] = {}  # Expected Calibration Error

        for g in groups:
            mask = (df[attr] == g).values
            g_scores = scores[mask]
            g_true = y_true.values[mask]

            if len(g_scores) < n_bins:
                continue

            # Bin by predicted score
            try:
                bins = pd.qcut(g_scores, n_bins, duplicates="drop")
            except ValueError:
                # All scores are the same
                continue

            cal_points = []
            ece_sum = 0.0
            total_n = len(g_scores)

            bin_df = pd.DataFrame({"score": g_scores, "true": g_true, "bin": bins})
            for bin_name, bin_data in bin_df.groupby("bin"):
                predicted_mean = float(bin_data["score"].mean())
                actual_mean = float(bin_data["true"].mean())
                n_bin = len(bin_data)
                cal_error = abs(predicted_mean - actual_mean)
                ece_sum += cal_error * n_bin / total_n
                cal_points.append({
                    "bin": str(bin_name),
                    "predicted_mean": round(predicted_mean, 4),
                    "actual_rate": round(actual_mean, 4),
                    "calibration_error": round(cal_error, 4),
                    "count": n_bin,
                })

            group_calibrations[str(g)] = cal_points
            group_ece[str(g)] = round(ece_sum, 4)

        if len(group_ece) < 2:
            continue

        # Calibration disparity = max ECE difference between groups
        best_calibrated = min(group_ece, key=group_ece.get)
        worst_calibrated = max(group_ece, key=group_ece.get)
        disparity = group_ece[worst_calibrated] - group_ece[best_calibrated]

        results[attr] = {
            "group_ece": group_ece,
            "calibration_disparity": round(disparity, 4),
            "best_calibrated_group": best_calibrated,
            "worst_calibrated_group": worst_calibrated,
            "passed": disparity < 0.05,
            "calibration_curves": group_calibrations,
            "interpretation": (
                f"Calibration disparity for '{attr}': {disparity:.1%}. "
                + (
                    f"The model is equally well-calibrated across groups."
                    if disparity < 0.05
                    else f"The model is POORLY CALIBRATED for '{worst_calibrated}' "
                         f"(ECE={group_ece[worst_calibrated]:.1%}) compared to "
                         f"'{best_calibrated}' (ECE={group_ece[best_calibrated]:.1%}). "
                         f"A predicted 70% for '{worst_calibrated}' may actually mean "
                         f"a very different real probability."
                )
            ),
        }

    return results
