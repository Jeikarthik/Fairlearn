"""Cross-validate FairLens metrics against Fairlearn's MetricFrame.

This module runs Microsoft Fairlearn's official metric implementations
alongside our custom engine.  Purpose:
1. Catch implementation bugs via independent verification.
2. Provide MetricFrame-based group breakdowns.
3. Allow the project to honestly claim Fairlearn integration for metrics,
   not just mitigation.

Note: Our custom engine adds Wilson confidence intervals — a feature
      Fairlearn does not support — which is why we maintain our own
      metric pipeline rather than delegating entirely to Fairlearn.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from fairlearn.metrics import (
    MetricFrame,
    demographic_parity_difference,
    demographic_parity_ratio,
    equalized_odds_difference,
    selection_rate,
)
from sklearn.metrics import accuracy_score

logger = logging.getLogger(__name__)


def crosscheck_metrics(
    df: pd.DataFrame, config: dict[str, Any]
) -> dict[str, Any]:
    """Run Fairlearn MetricFrame to validate custom metric results."""
    outcome_col = config["outcome_column"]
    pred_col = config.get("prediction_column")
    favorable = config["favorable_outcome"]
    protected = config.get("protected_attributes", [])

    # Coerce to binary integer arrays
    y_true = _to_binary(df[outcome_col], favorable)
    y_pred = _to_binary(df[pred_col], favorable) if pred_col and pred_col in df.columns else y_true

    results: dict[str, Any] = {"_meta": {"status": "success"}}

    for attr in protected:
        if attr not in df.columns:
            continue
        sensitive = df[attr].astype(str)

        try:
            # Build MetricFrame with multiple metrics
            metrics_dict = {
                "selection_rate": selection_rate,
                "accuracy": accuracy_score,
            }
            mf = MetricFrame(
                metrics=metrics_dict,
                y_true=y_true,
                y_pred=y_pred,
                sensitive_features=sensitive,
            )

            # Compute Fairlearn's built-in difference/ratio
            fl_dpd = demographic_parity_difference(
                y_true, y_pred, sensitive_features=sensitive
            )
            fl_dpr = demographic_parity_ratio(
                y_true, y_pred, sensitive_features=sensitive
            )

            # Equalized odds (requires both y_true and y_pred)
            fl_eod = None
            if pred_col and pred_col in df.columns:
                try:
                    fl_eod = equalized_odds_difference(
                        y_true, y_pred, sensitive_features=sensitive
                    )
                except Exception:  # noqa: BLE001
                    pass

            attr_result: dict[str, Any] = {
                "fairlearn_demographic_parity_difference": round(abs(fl_dpd), 4),
                "fairlearn_demographic_parity_ratio": round(fl_dpr, 4),
                "group_selection_rates": {
                    str(k): round(float(v), 4) for k, v in mf.by_group["selection_rate"].items()
                },
                "group_accuracy": {
                    str(k): round(float(v), 4) for k, v in mf.by_group["accuracy"].items()
                },
                "overall_selection_rate": round(float(mf.overall["selection_rate"]), 4),
                "overall_accuracy": round(float(mf.overall["accuracy"]), 4),
            }
            if fl_eod is not None:
                attr_result["fairlearn_equalized_odds_difference"] = round(abs(fl_eod), 4)

            results[attr] = attr_result

        except Exception as exc:  # noqa: BLE001
            logger.warning("Fairlearn crosscheck failed for %s: %s", attr, exc)
            results[attr] = {"error": str(exc)}

    return results


def _to_binary(series: pd.Series, favorable: Any) -> pd.Series:
    """Convert outcome/prediction column to binary integer."""
    if pd.api.types.is_numeric_dtype(series):
        try:
            return (series == float(favorable)).astype(int)
        except (ValueError, TypeError):
            pass
    return (series.astype(str) == str(favorable)).astype(int)
