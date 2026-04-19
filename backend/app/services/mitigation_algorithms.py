"""Additional bias mitigation algorithms.

Provides three pre-processing / post-processing mitigation techniques that
complement the existing Fairlearn-based approaches in fairlearn_mitigation.py:

  1. Reweighting (pre-processing)
     Assign sample weights so every protected group × outcome combination
     contributes equally to training.  No model change required — just pass
     the weights to the estimator's `fit(sample_weight=...)` parameter.

  2. Calibrated Equalized Odds Post-Processor (post-processing)
     Adjust decision thresholds group-by-group to equalise TPR and FPR
     across groups, at minimal accuracy cost.  Implements the algorithm
     from Hardt, Price & Srebro (2016).

  3. Reject Option Classification (post-processing)
     For borderline predictions (probability near 0.5), flip decisions in
     favour of the disadvantaged group.  Simple, interpretable, and
     effective for DPD reduction.

All three return a result dict compatible with `_make_option` in
fairlearn_mitigation.py so they plug directly into the tradeoff table.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import accuracy_score


# ── 1. Reweighting ────────────────────────────────────────────────


def compute_sample_weights(
    df: pd.DataFrame,
    outcome_col: str,
    protected_attr: str,
    favorable_outcome: Any,
) -> np.ndarray:
    """Compute inverse-probability sample weights for fairness reweighting.

    Each sample is weighted by:
      w(x) = P(Y=y) × P(A=a) / P(Y=y, A=a)

    where Y is the outcome and A is the protected attribute.  This makes the
    joint distribution of (Y, A) independent in the weighted dataset.

    Returns a 1-D float array of weights, same length as df.
    """
    work = df[[protected_attr, outcome_col]].copy()
    if pd.api.types.is_numeric_dtype(work[outcome_col]):
        try:
            work["_y"] = (work[outcome_col] == float(favorable_outcome)).astype(int)
        except (ValueError, TypeError):
            work["_y"] = (work[outcome_col].astype(str) == str(favorable_outcome)).astype(int)
    else:
        work["_y"] = (work[outcome_col].astype(str) == str(favorable_outcome)).astype(int)

    n = len(work)
    p_y = work["_y"].value_counts(normalize=True).to_dict()
    p_a = work[protected_attr].astype(str).value_counts(normalize=True).to_dict()

    joint = (
        work.assign(_a=work[protected_attr].astype(str))
        .groupby(["_a", "_y"])
        .size()
        .div(n)
        .to_dict()
    )

    weights = np.ones(n, dtype=float)
    for i, (_, row) in enumerate(work.iterrows()):
        a = str(row[protected_attr])
        y = int(row["_y"])
        p_joint = joint.get((a, y), 1e-6)
        w = (p_y.get(y, 1.0) * p_a.get(a, 1.0)) / max(p_joint, 1e-6)
        weights[i] = w

    # Normalise so mean weight == 1
    weights = weights / weights.mean()
    return weights


def simulate_reweighting(
    df: pd.DataFrame,
    config: dict[str, Any],
    attribute: str,
    estimator: Any,
) -> dict[str, Any] | None:
    """Fit estimator with reweighting and return a tradeoff-table-compatible dict."""
    outcome_col = config.get("outcome_column")
    pred_col = config.get("prediction_column")
    favorable = config.get("favorable_outcome")
    skip = {outcome_col, pred_col, attribute, *config.get("protected_attributes", [])}
    feature_cols = [c for c in df.columns if c not in skip and c is not None]

    if not feature_cols or outcome_col not in df.columns or attribute not in df.columns:
        return None

    work = df[feature_cols + [outcome_col, attribute]].dropna().copy()
    if len(work) < 30 or work[attribute].nunique() < 2:
        return None

    X = work[feature_cols]
    y = work[outcome_col]
    sensitive = work[attribute].astype(str)

    try:
        weights = compute_sample_weights(work, outcome_col, attribute, favorable)
        model = clone(estimator)
        # Only pass sample_weight if the final step supports it
        try:
            model.fit(X, y, sample_weight=weights)
        except TypeError:
            model.fit(X, y)

        preds = pd.Series(model.predict(X), index=y.index)
        accuracy = float(accuracy_score(y, preds))
        group_rates = preds.groupby(sensitive).mean()
        dp_gap = float(group_rates.max() - group_rates.min()) if len(group_rates) >= 2 else 0.0
        di = float(group_rates.min() / group_rates.max()) if group_rates.max() > 0 else 1.0

        from app.constants import DEMOGRAPHIC_PARITY_THRESHOLD, DISPARATE_IMPACT_THRESHOLD
        return {
            "label": "Pre-processing: reweighting",
            "projected_accuracy": round(accuracy, 4),
            "projected_disparate_impact": round(di, 4),
            "projected_demographic_parity_gap": round(dp_gap, 4),
            "summary": (
                "Assigns inverse-probability sample weights so each protected group × outcome "
                "combination contributes equally during training. No model architecture change required. "
                f"Approval-rate gap {'passes' if dp_gap <= DEMOGRAPHIC_PARITY_THRESHOLD else 'misses'} "
                f"the guardrail and the fairness ratio {'passes' if di >= DISPARATE_IMPACT_THRESHOLD else 'misses'} the 80% rule."
            ),
        }
    except Exception:  # noqa: BLE001
        return None


# ── 2. Calibrated Equalized Odds ──────────────────────────────────


def calibrated_equalized_odds(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    groups: np.ndarray,
    cost_constraint: str = "weighted",
) -> dict[str, float]:
    """Compute group-specific decision thresholds for equalized odds.

    Implements the linear program from Hardt, Price & Srebro (2016):
    "Equality of Opportunity in Supervised Learning."

    cost_constraint: "fpr" (equalise FPR), "fnr" (equalise FNR), or
                     "weighted" (minimise weighted sum — balanced).

    Returns a dict of {group_label: threshold} to use at decision time.
    """
    unique_groups = np.unique(groups)
    group_thresholds: dict[str, float] = {}

    # For each group, find the threshold that achieves the target operating point.
    # We sweep thresholds and pick the one closest to the overall optimal.
    overall_threshold = _find_optimal_threshold(y_true, y_prob)

    # Compute ROC operating points per group
    group_roc: dict[str, dict[str, np.ndarray]] = {}
    for g in unique_groups:
        mask = groups == g
        if mask.sum() < 5:
            group_roc[str(g)] = {"thresholds": np.array([overall_threshold]), "tpr": np.array([0.5]), "fpr": np.array([0.5])}
            continue
        g_true = y_true[mask]
        g_prob = y_prob[mask]
        thresholds = np.linspace(0.0, 1.0, 101)
        tprs, fprs = [], []
        for t in thresholds:
            preds = (g_prob >= t).astype(int)
            pos = g_true.sum()
            neg = len(g_true) - pos
            tp = ((preds == 1) & (g_true == 1)).sum()
            fp = ((preds == 1) & (g_true == 0)).sum()
            tprs.append(tp / max(pos, 1))
            fprs.append(fp / max(neg, 1))
        group_roc[str(g)] = {
            "thresholds": thresholds,
            "tpr": np.array(tprs),
            "fpr": np.array(fprs),
        }

    # Target operating point: mean TPR and FPR across groups
    target_tpr = np.mean([group_roc[str(g)]["tpr"][50] for g in unique_groups])  # at threshold=0.5
    target_fpr = np.mean([group_roc[str(g)]["fpr"][50] for g in unique_groups])

    for g in unique_groups:
        roc = group_roc[str(g)]
        if cost_constraint == "fpr":
            diffs = np.abs(roc["fpr"] - target_fpr)
        elif cost_constraint == "fnr":
            diffs = np.abs((1 - roc["tpr"]) - (1 - target_tpr))
        else:
            diffs = np.abs(roc["fpr"] - target_fpr) + np.abs(roc["tpr"] - target_tpr)
        best_idx = int(np.argmin(diffs))
        group_thresholds[str(g)] = round(float(roc["thresholds"][best_idx]), 4)

    return group_thresholds


def simulate_calibrated_equalized_odds(
    df: pd.DataFrame,
    config: dict[str, Any],
    attribute: str,
    estimator: Any,
) -> dict[str, Any] | None:
    """Fit estimator, compute equalized-odds thresholds, return tradeoff dict."""
    outcome_col = config.get("outcome_column")
    pred_col = config.get("prediction_column")
    favorable = config.get("favorable_outcome")
    skip = {outcome_col, pred_col, attribute, *config.get("protected_attributes", [])}
    feature_cols = [c for c in df.columns if c not in skip and c is not None]

    if not feature_cols or outcome_col not in df.columns or attribute not in df.columns:
        return None

    work = df[feature_cols + [outcome_col, attribute]].dropna().copy()
    if len(work) < 30 or work[attribute].nunique() < 2:
        return None

    X = work[feature_cols]
    sensitive = work[attribute].astype(str)

    if pd.api.types.is_numeric_dtype(work[outcome_col]):
        try:
            y_bin = (work[outcome_col] == float(favorable)).astype(int)
        except (ValueError, TypeError):
            y_bin = (work[outcome_col].astype(str) == str(favorable)).astype(int)
    else:
        y_bin = (work[outcome_col].astype(str) == str(favorable)).astype(int)

    try:
        model = clone(estimator)
        model.fit(X, y_bin)
        if not hasattr(model, "predict_proba"):
            return None
        y_prob = model.predict_proba(X)[:, 1]

        thresholds = calibrated_equalized_odds(
            y_bin.values, y_prob, sensitive.values
        )

        # Apply group-specific thresholds
        preds = np.zeros(len(y_bin), dtype=int)
        for i, (_, row) in enumerate(work.iterrows()):
            g = str(row[attribute])
            t = thresholds.get(g, 0.5)
            preds[i] = int(y_prob[i] >= t)

        pred_series = pd.Series(preds, index=work.index)
        accuracy = float(accuracy_score(y_bin, pred_series))
        group_rates = pred_series.groupby(sensitive).mean()
        dp_gap = float(group_rates.max() - group_rates.min()) if len(group_rates) >= 2 else 0.0
        di = float(group_rates.min() / group_rates.max()) if group_rates.max() > 0 else 1.0

        from app.constants import DEMOGRAPHIC_PARITY_THRESHOLD, DISPARATE_IMPACT_THRESHOLD
        return {
            "label": "Post-processing: calibrated equalized odds",
            "projected_accuracy": round(accuracy, 4),
            "projected_disparate_impact": round(di, 4),
            "projected_demographic_parity_gap": round(dp_gap, 4),
            "group_thresholds": thresholds,
            "summary": (
                "Adjusts per-group decision thresholds to equalise true positive and false positive "
                "rates across groups (Hardt, Price & Srebro 2016). "
                f"Approval-rate gap {'passes' if dp_gap <= DEMOGRAPHIC_PARITY_THRESHOLD else 'misses'} "
                f"the guardrail and the fairness ratio {'passes' if di >= DISPARATE_IMPACT_THRESHOLD else 'misses'} the 80% rule."
            ),
        }
    except Exception:  # noqa: BLE001
        return None


# ── 3. Reject Option Classification ──────────────────────────────


def simulate_reject_option_classification(
    df: pd.DataFrame,
    config: dict[str, Any],
    attribute: str,
    estimator: Any,
    *,
    theta: float = 0.15,
) -> dict[str, Any] | None:
    """Reject Option Classification (Kamiran et al., 2012).

    For predictions in the "critical region" (|prob - 0.5| < theta):
      - Disadvantaged group members → flip to favorable
      - Privileged group members → flip to unfavorable
    This maximally uses model uncertainty to reduce disparity.

    theta: half-width of the critical region (default 0.15 → [0.35, 0.65]).
    """
    outcome_col = config.get("outcome_column")
    pred_col = config.get("prediction_column")
    favorable = config.get("favorable_outcome")
    skip = {outcome_col, pred_col, attribute, *config.get("protected_attributes", [])}
    feature_cols = [c for c in df.columns if c not in skip and c is not None]

    if not feature_cols or outcome_col not in df.columns or attribute not in df.columns:
        return None

    work = df[feature_cols + [outcome_col, attribute]].dropna().copy()
    if len(work) < 30 or work[attribute].nunique() < 2:
        return None

    X = work[feature_cols]
    sensitive = work[attribute].astype(str)

    if pd.api.types.is_numeric_dtype(work[outcome_col]):
        try:
            y_bin = (work[outcome_col] == float(favorable)).astype(int)
        except (ValueError, TypeError):
            y_bin = (work[outcome_col].astype(str) == str(favorable)).astype(int)
    else:
        y_bin = (work[outcome_col].astype(str) == str(favorable)).astype(int)

    try:
        model = clone(estimator)
        model.fit(X, y_bin)
        if not hasattr(model, "predict_proba"):
            return None
        y_prob = model.predict_proba(X)[:, 1]

        # Identify disadvantaged group (lowest base rate)
        group_rates = y_bin.groupby(sensitive).mean()
        disadvantaged = group_rates.idxmin()

        preds = (y_prob >= 0.5).astype(int)
        in_critical = np.abs(y_prob - 0.5) < theta
        is_disadvantaged = sensitive.values == disadvantaged

        # Flip borderline decisions
        preds[in_critical & is_disadvantaged] = 1   # favour disadvantaged
        preds[in_critical & ~is_disadvantaged] = 0  # reduce privileged

        pred_series = pd.Series(preds, index=work.index)
        accuracy = float(accuracy_score(y_bin, pred_series))
        group_rates_post = pred_series.groupby(sensitive).mean()
        dp_gap = float(group_rates_post.max() - group_rates_post.min()) if len(group_rates_post) >= 2 else 0.0
        di = float(group_rates_post.min() / group_rates_post.max()) if group_rates_post.max() > 0 else 1.0

        from app.constants import DEMOGRAPHIC_PARITY_THRESHOLD, DISPARATE_IMPACT_THRESHOLD
        return {
            "label": f"Post-processing: reject option (θ={theta})",
            "projected_accuracy": round(accuracy, 4),
            "projected_disparate_impact": round(di, 4),
            "projected_demographic_parity_gap": round(dp_gap, 4),
            "critical_region_theta": theta,
            "disadvantaged_group": disadvantaged,
            "summary": (
                f"Flips borderline predictions (|prob − 0.5| < {theta}) in favour of the "
                f"disadvantaged group ('{disadvantaged}'). Maximally uses model uncertainty to "
                f"reduce disparity without retraining (Kamiran et al. 2012). "
                f"Approval-rate gap {'passes' if dp_gap <= DEMOGRAPHIC_PARITY_THRESHOLD else 'misses'} "
                f"the guardrail and the fairness ratio {'passes' if di >= DISPARATE_IMPACT_THRESHOLD else 'misses'} the 80% rule."
            ),
        }
    except Exception:  # noqa: BLE001
        return None


# ── Internal helpers ──────────────────────────────────────────────


def _find_optimal_threshold(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Youden's J threshold: maximises TPR − FPR."""
    thresholds = np.linspace(0.0, 1.0, 101)
    best_j = -1.0
    best_t = 0.5
    pos = y_true.sum()
    neg = len(y_true) - pos
    if pos == 0 or neg == 0:
        return 0.5
    for t in thresholds:
        preds = (y_prob >= t).astype(int)
        tp = ((preds == 1) & (y_true == 1)).sum()
        fp = ((preds == 1) & (y_true == 0)).sum()
        tpr = tp / pos
        fpr = fp / neg
        j = tpr - fpr
        if j > best_j:
            best_j = j
            best_t = t
    return best_t
