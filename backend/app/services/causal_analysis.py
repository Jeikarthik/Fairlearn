"""Covariate-adjusted analysis — regression-adjusted metrics, Simpson's paradox, interaction effects.

NOTE: This module performs *covariate adjustment* (logistic regression residuals),
NOT causal inference.  True causal inference requires a user-specified causal DAG
and a library such as DoWhy or CausalML.  Calling these results "causal" in
compliance reports is misleading; they are labeled "covariate_adjusted" throughout.

Addresses 3 deficiencies:
  #9   Purely observational → covariate-adjusted disparities
  #10  No Simpson's paradox detection
  #14  No feature interaction effects
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OrdinalEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier


# ─── 1. Regression-Adjusted Fairness Metrics ────────────────────


def compute_adjusted_metrics(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Compute fairness metrics AFTER controlling for legitimate factors.

    The raw audit reports: "Group A has 80% approval, Group B has 60%."
    But what if Group A has higher average income? After controlling for
    income, the gap might shrink (legitimate factor) or grow (hidden bias).

    Method: Logistic regression on legitimate features → predicted
    probabilities → residual analysis by group.
    """
    outcome_col = config["outcome_column"]
    favorable = config["favorable_outcome"]
    protected = config.get("protected_attributes", [])
    legitimate_factors = config.get("legitimate_factors", [])

    # If no legitimate factors specified, use all non-protected, non-outcome features
    if not legitimate_factors:
        legitimate_factors = [
            c for c in df.columns
            if c not in {outcome_col, config.get("prediction_column"), *protected}
        ]

    if not legitimate_factors:
        return {"_meta": {"status": "skipped", "reason": "No legitimate factors available."}}

    # Prepare data
    work = df[[outcome_col] + protected + legitimate_factors].dropna()
    if len(work) < 30:
        return {"_meta": {"status": "skipped", "reason": "Too few rows after dropping missing."}}

    # Encode outcome as binary
    if pd.api.types.is_numeric_dtype(work[outcome_col]):
        try:
            y = (work[outcome_col] == float(favorable)).astype(int)
        except (ValueError, TypeError):
            y = (work[outcome_col].astype(str) == str(favorable)).astype(int)
    else:
        y = (work[outcome_col].astype(str) == str(favorable)).astype(int)

    # Encode features
    X = _encode_mixed(work[legitimate_factors])
    if X is None or X.shape[1] == 0:
        return {"_meta": {"status": "skipped", "reason": "Could not encode features."}}

    results: dict[str, Any] = {"_meta": {"status": "success", "method": "covariate_adjusted", "note": "logistic regression residuals — NOT causal inference"}}

    try:
        model = LogisticRegression(max_iter=1000, solver="lbfgs", random_state=42)
        model.fit(X, y)
        predicted_prob = model.predict_proba(X)[:, 1]
        residuals = y.values - predicted_prob  # positive = got favorable unexpectedly
    except Exception as exc:  # noqa: BLE001
        return {"_meta": {"status": "failed", "reason": str(exc)}}

    for attr in protected:
        if attr not in work.columns:
            continue
        groups = work[attr].astype(str)
        unique_groups = groups.unique()
        if len(unique_groups) < 2:
            continue

        # Raw rates
        raw_rates = {g: round(float(y[groups == g].mean()), 4) for g in unique_groups}
        raw_gap = max(raw_rates.values()) - min(raw_rates.values())

        # Adjusted rates (mean predicted probability per group)
        adjusted_rates = {g: round(float(predicted_prob[groups == g].mean()), 4) for g in unique_groups}
        adjusted_gap = max(adjusted_rates.values()) - min(adjusted_rates.values())

        # Residual analysis: mean residual per group
        # Positive residual = "this group is approved MORE than expected given their features"
        residual_means = {g: round(float(residuals[groups == g].mean()), 4) for g in unique_groups}
        residual_gap = max(residual_means.values()) - min(residual_means.values())

        best_raw = max(raw_rates, key=raw_rates.get)
        worst_raw = min(raw_rates, key=raw_rates.get)
        best_residual = max(residual_means, key=residual_means.get)

        # Did the direction flip?
        direction_changed = (best_raw != best_residual)

        results[attr] = {
            "raw_rates": raw_rates,
            "raw_gap": round(raw_gap, 4),
            "adjusted_rates": adjusted_rates,
            "adjusted_gap": round(adjusted_gap, 4),
            "residual_means": residual_means,
            "residual_gap": round(residual_gap, 4),
            "controlled_for": legitimate_factors,
            "direction_changed": direction_changed,
            "interpretation": _adjusted_interpretation(
                raw_gap, residual_gap, direction_changed, best_raw, worst_raw, attr
            ),
        }

    return results


def _adjusted_interpretation(
    raw_gap: float, residual_gap: float, direction_changed: bool,
    best_raw: str, worst_raw: str, attr: str,
) -> str:
    if direction_changed:
        return (
            f"⚠️ SIMPSON'S PARADOX: After controlling for legitimate factors, "
            f"the direction of bias for '{attr}' REVERSED. The raw data shows "
            f"'{best_raw}' is advantaged, but after adjustment '{worst_raw}' may "
            f"actually be advantaged. The raw metrics are MISLEADING."
        )
    if residual_gap < raw_gap * 0.5:
        return (
            f"After controlling for legitimate factors, the gap between '{best_raw}' "
            f"and '{worst_raw}' shrank from {raw_gap:.1%} to {residual_gap:.1%}. "
            f"Most of the observed disparity is explained by legitimate differences, "
            f"not by the protected attribute '{attr}'."
        )
    if residual_gap > raw_gap * 1.2:
        return (
            f"⚠️ After controlling for legitimate factors, the gap INCREASED from "
            f"{raw_gap:.1%} to {residual_gap:.1%}. Legitimate factors were partially "
            f"MASKING the true extent of bias for '{attr}'. This is a red flag."
        )
    return (
        f"After controlling for legitimate factors, the gap remained similar "
        f"({raw_gap:.1%} raw → {residual_gap:.1%} adjusted). The disparity for "
        f"'{attr}' is not explained by the available legitimate factors."
    )


# ─── 2. Simpson's Paradox Detection ─────────────────────────────


def detect_simpsons_paradox(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Check if overall bias direction reverses when stratified.

    Simpson's paradox occurs when Group A appears advantaged overall,
    but within every subgroup (e.g., department), Group B is advantaged.
    """
    outcome_col = config["outcome_column"]
    favorable = config["favorable_outcome"]
    protected = config.get("protected_attributes", [])

    if pd.api.types.is_numeric_dtype(df[outcome_col]):
        try:
            is_fav = df[outcome_col] == float(favorable)
        except (ValueError, TypeError):
            is_fav = df[outcome_col].astype(str) == str(favorable)
    else:
        is_fav = df[outcome_col].astype(str) == str(favorable)

    # Candidate stratification variables
    stratify_candidates = [
        c for c in df.columns
        if c not in {outcome_col, config.get("prediction_column"), *protected}
        and df[c].nunique() >= 2
        and df[c].nunique() <= 20  # only reasonable stratifiers
    ]

    results: dict[str, Any] = {"_meta": {"status": "success"}}

    for attr in protected:
        if attr not in df.columns:
            continue
        groups = df[attr].dropna().unique()
        if len(groups) < 2:
            continue

        # Overall direction
        overall_rates = {}
        for g in groups:
            mask = df[attr] == g
            overall_rates[str(g)] = is_fav[mask].mean()
        overall_best = max(overall_rates, key=overall_rates.get)

        paradoxes: list[dict[str, Any]] = []

        for strat_col in stratify_candidates:
            if strat_col not in df.columns:
                continue

            reversals = 0
            total_strata = 0
            reversal_details = []

            for stratum_val, stratum_df in df.groupby(strat_col):
                if len(stratum_df) < 10:
                    continue
                total_strata += 1

                strat_rates = {}
                for g in groups:
                    mask = stratum_df[attr] == g
                    n = mask.sum()
                    if n < 5:
                        continue
                    strat_rates[str(g)] = is_fav[stratum_df.index][mask].mean()

                if len(strat_rates) < 2:
                    continue
                strat_best = max(strat_rates, key=strat_rates.get)
                if strat_best != overall_best:
                    reversals += 1
                    reversal_details.append({
                        "stratum": f"{strat_col}={stratum_val}",
                        "rates": {k: round(v, 4) for k, v in strat_rates.items()},
                        "advantaged_in_stratum": strat_best,
                    })

            if reversals > 0 and total_strata > 0:
                reversal_rate = reversals / total_strata
                paradoxes.append({
                    "stratify_by": strat_col,
                    "reversal_count": reversals,
                    "total_strata": total_strata,
                    "reversal_rate": round(reversal_rate, 4),
                    "is_paradox": reversal_rate > 0.5,
                    "details": reversal_details[:5],
                    "explanation": (
                        f"When stratified by '{strat_col}', the bias direction "
                        f"reverses in {reversals}/{total_strata} subgroups "
                        f"({reversal_rate:.0%}). "
                        + ("⚠️ SIMPSON'S PARADOX DETECTED — the overall bias "
                           "direction is MISLEADING."
                           if reversal_rate > 0.5
                           else "Partial reversal detected but not dominant.")
                    ),
                })

        results[attr] = {
            "overall_best_group": overall_best,
            "overall_rates": {k: round(v, 4) for k, v in overall_rates.items()},
            "paradoxes_found": [p for p in paradoxes if p["is_paradox"]],
            "partial_reversals": [p for p in paradoxes if not p["is_paradox"]],
            "total_checked": len(stratify_candidates),
        }

    return results


# ─── 3. Feature Interaction Effects ──────────────────────────────


def detect_interaction_effects(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Detect bias hidden in feature interactions.

    A feature alone may not correlate with the protected attribute,
    but COMBINED with another feature it does. This uses a shallow
    decision tree to find the most discriminative feature splits.
    """
    protected = config.get("protected_attributes", [])
    outcome_col = config.get("outcome_column")
    pred_col = config.get("prediction_column")
    skip = {outcome_col, pred_col, *protected}
    feature_cols = [c for c in df.columns if c not in skip and c is not None]

    if len(feature_cols) < 2:
        return {"_meta": {"status": "skipped", "reason": "Need ≥2 features for interaction detection."}}

    results: dict[str, Any] = {"_meta": {"status": "success"}}

    for attr in protected:
        if attr not in df.columns or df[attr].nunique() < 2:
            continue

        work = df[[attr] + feature_cols].dropna()
        if len(work) < 30:
            continue

        X = _encode_mixed(work[feature_cols])
        if X is None:
            continue

        # Encode protected attribute as target for the tree
        y_attr = OrdinalEncoder().fit_transform(work[[attr]]).ravel().astype(int)

        try:
            tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=20, random_state=42)
            tree.fit(X, y_attr)

            # Extract interaction paths (depth > 1 = interaction)
            importances = tree.feature_importances_
            encoded_names = _get_encoded_names(work[feature_cols])
            if len(encoded_names) != len(importances):
                encoded_names = [f"feature_{i}" for i in range(len(importances))]

            # Top interaction features
            top_idx = np.argsort(importances)[::-1][:5]
            interactions = []
            for idx in top_idx:
                if importances[idx] < 0.01:
                    continue
                interactions.append({
                    "feature": encoded_names[idx] if idx < len(encoded_names) else f"feature_{idx}",
                    "importance": round(float(importances[idx]), 4),
                })

            results[attr] = {
                "tree_accuracy": round(float(tree.score(X, y_attr)), 4),
                "top_interaction_features": interactions,
                "interpretation": (
                    f"A decision tree can predict '{attr}' from other features "
                    f"with {tree.score(X, y_attr):.0%} accuracy. "
                    + ("This means feature combinations effectively encode "
                       "the protected attribute — proxy bias through interactions."
                       if tree.score(X, y_attr) > 0.70
                       else "Feature interactions have limited predictive power "
                            "for the protected attribute.")
                ),
            }
        except Exception as exc:  # noqa: BLE001
            results[attr] = {"error": str(exc)}

    return results


# ─── Helpers ────────────────────────────────────────────────────


def _encode_mixed(df: pd.DataFrame) -> np.ndarray | None:
    """Encode mixed-type DataFrame to numeric array."""
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


def _get_encoded_names(df: pd.DataFrame) -> list[str]:
    """Get feature names after encoding."""
    names = []
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            names.append(col)
        else:
            names.append(col)
    return names
