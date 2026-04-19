from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.fairlearn_mitigation import simulate_tradeoffs as _fairlearn_tradeoffs


def build_mitigation_cards(
    results: dict[str, Any],
    df: pd.DataFrame | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for attribute, payload in results.get("results", {}).items():
        metrics = payload["metrics"]
        tradeoff_options = _all_tradeoff_options(df, config, attribute) if df is not None and config is not None else []

        if _failed(metrics, "disparate_impact_ratio"):
            cards.append(
                {
                    "title": f"Reduce approval-rate imbalance for {attribute}",
                    "severity": "critical",
                    "triggered_by": "disparate_impact_ratio",
                    "attribute": attribute,
                    "action": "Retrain with fairness constraints or rebalance the dataset before the next release.",
                    "tradeoff": "Expected trade-off: fairness improves, overall accuracy may drop slightly.",
                    "tradeoff_options": tradeoff_options,
                }
            )
        if _failed(metrics, "equal_opportunity_difference"):
            cards.append(
                {
                    "title": f"Stop missing qualified people in {attribute}",
                    "severity": "critical",
                    "triggered_by": "equal_opportunity_difference",
                    "attribute": attribute,
                    "action": "Review false negatives from the disadvantaged group and reweight those cases in training.",
                    "tradeoff": "Expected trade-off: more qualified people are approved, but review volume may increase.",
                    "tradeoff_options": tradeoff_options,
                }
            )
        if _failed(metrics, "demographic_parity_difference"):
            cards.append(
                {
                    "title": f"Bring approval rates closer together for {attribute}",
                    "severity": "warning",
                    "triggered_by": "demographic_parity_difference",
                    "attribute": attribute,
                    "action": "Review thresholds and screening rules that are suppressing one group's approval rate.",
                    "tradeoff": "Expected trade-off: group outcomes become more balanced, but some existing rules may need revision.",
                    "tradeoff_options": tradeoff_options,
                }
            )
    if not cards:
        cards.append(
            {
                "title": "No urgent mitigation required",
                "severity": "info",
                "triggered_by": "none",
                "attribute": None,
                "action": "Keep monitoring the system and rerun the audit after data, model, or policy changes.",
                "tradeoff": None,
                "tradeoff_options": [],
            }
        )
    return cards


def _all_tradeoff_options(
    df: pd.DataFrame,
    config: dict[str, Any],
    attribute: str,
) -> list[dict[str, Any]]:
    """Collect tradeoff options from all mitigation algorithms.

    Runs Fairlearn-based options first (threshold optimizer, ExponentiatedGradient),
    then appends the three new algorithms: reweighting, calibrated equalized odds,
    and reject option classification.  Deduplicates by label.
    """
    options: list[dict[str, Any]] = []

    # Existing Fairlearn-based options
    try:
        options.extend(_fairlearn_tradeoffs(df, config, attribute))
    except Exception:  # noqa: BLE001
        pass

    # Build a shared estimator pipeline for the new algorithms
    estimator = _build_estimator(df, config, attribute)
    if estimator is not None:
        from app.services.mitigation_algorithms import (
            simulate_calibrated_equalized_odds,
            simulate_reject_option_classification,
            simulate_reweighting,
        )

        for fn in (simulate_reweighting, simulate_calibrated_equalized_odds, simulate_reject_option_classification):
            try:
                result = fn(df, config, attribute, estimator)
                if result:
                    options.append(result)
            except Exception:  # noqa: BLE001
                continue

    # Deduplicate by label
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for opt in options:
        label = opt.get("label", "")
        if label not in seen:
            seen.add(label)
            deduped.append(opt)

    return deduped


def _build_estimator(
    df: pd.DataFrame,
    config: dict[str, Any],
    attribute: str,
) -> Any | None:
    """Build a scikit-learn Pipeline for use by the mitigation algorithms."""
    outcome_col = config.get("outcome_column")
    pred_col = config.get("prediction_column")
    skip = {outcome_col, pred_col, attribute, *config.get("protected_attributes", [])}
    feature_cols = [c for c in df.columns if c not in skip and c is not None]

    if not feature_cols or outcome_col not in df.columns:
        return None

    try:
        from sklearn.compose import ColumnTransformer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder, StandardScaler

        numeric = [c for c in feature_cols if pd.api.types.is_numeric_dtype(df[c])]
        categorical = [c for c in feature_cols if c not in numeric]
        transformer = ColumnTransformer(
            transformers=[
                ("num", StandardScaler(), numeric),
                ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
            ],
            remainder="drop",
        )
        return Pipeline([("prep", transformer), ("clf", LogisticRegression(max_iter=1000))])
    except Exception:  # noqa: BLE001
        return None


def _failed(metrics: dict[str, Any], key: str) -> bool:
    metric = metrics.get(key)
    return bool(metric and metric.get("passed") is False)
