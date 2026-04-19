"""Individual fairness metrics — complementing group-level analysis.

Implements Consistency Score (k-NN), Generalized Entropy Index, and
Between/Within Group inequality decomposition.  These are modeled on the
individual fairness metrics in IBM AIF360 but computed from scratch so we
control the interface and can return plain-language explanations.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import OrdinalEncoder, StandardScaler


def compute_individual_fairness(
    df: pd.DataFrame, config: dict[str, Any]
) -> dict[str, Any]:
    """Compute individual fairness metrics on the dataset."""
    outcome_col = config["outcome_column"]
    pred_col = config.get("prediction_column")
    favorable = config["favorable_outcome"]
    protected = config.get("protected_attributes", [])

    target_col = pred_col or outcome_col
    if target_col not in df.columns:
        return {"_meta": {"status": "skipped", "reason": "Target column not found."}}

    # Prepare feature matrix (exclude protected + outcome + prediction)
    feature_cols = [
        c
        for c in df.columns
        if c not in {outcome_col, pred_col, *protected}
    ]
    if not feature_cols:
        return {"_meta": {"status": "skipped", "reason": "No feature columns available for individual fairness."}}

    work = df[feature_cols + [target_col] + [a for a in protected if a in df.columns]].dropna()
    if len(work) < 10:
        return {"_meta": {"status": "skipped", "reason": "Too few complete rows (need ≥10)."}}

    decisions = _coerce_binary(work[target_col], favorable)
    X = _encode_features(work[feature_cols])

    results: dict[str, Any] = {"_meta": {"status": "success"}}

    # ── 1. Consistency Score ────────────────────────────
    consistency = _consistency_score(X, decisions, n_neighbors=5)
    results["consistency_score"] = {
        "value": round(consistency, 4),
        "threshold": 0.80,
        "passed": consistency >= 0.80,
        "explanation": (
            f"Consistency score is {consistency:.1%}. "
            + (
                "Similar individuals receive similar decisions — the system treats comparable people fairly."
                if consistency >= 0.80
                else "Similar individuals often receive different decisions — "
                "the system may be treating comparable people unfairly."
            )
        ),
        "method": "k-nearest-neighbors (k=5)",
    }

    # ── 2. Generalized Entropy Index ────────────────────
    gei = _generalized_entropy_index(decisions, alpha=2)
    results["generalized_entropy_index"] = {
        "value": round(gei, 4),
        "threshold": 0.20,
        "passed": gei <= 0.20,
        "explanation": (
            f"Generalized Entropy Index is {gei:.4f}. "
            + (
                "Outcome distribution is relatively uniform across individuals."
                if gei <= 0.20
                else "Outcomes are concentrated unevenly — some individuals bear a "
                "disproportionate share of negative decisions."
            )
        ),
        "method": "GE(α=2) — Coefficient of Variation",
    }

    # ── 3. Between/Within Group Inequality ─────────────
    for attr in protected:
        if attr not in work.columns:
            continue
        groups = work[attr].astype(str).values
        between, within = _between_within_entropy(decisions, groups, alpha=2)
        total = between + within
        results[f"between_group_inequality_{attr}"] = {
            "between": round(between, 4),
            "within": round(within, 4),
            "between_fraction": round(between / total if total > 0 else 0, 4),
            "explanation": (
                f"{between / total:.0%} of outcome inequality is explained by "
                f"differences BETWEEN {attr} groups; {within / total:.0%} is "
                f"within groups."
                if total > 0
                else "Insufficient data to decompose inequality."
            ),
        }

    return results


# ── helpers ────────────────────────────────────────────


def _coerce_binary(series: pd.Series, favorable: Any) -> np.ndarray:
    """Convert outcome series to 0/1 integer array."""
    if pd.api.types.is_numeric_dtype(series):
        try:
            return (series == float(favorable)).astype(int).values
        except (ValueError, TypeError):
            pass
    return (series.astype(str) == str(favorable)).astype(int).values


def _encode_features(X: pd.DataFrame) -> np.ndarray:
    """Encode mixed-type features to numeric for distance computation."""
    numeric = X.select_dtypes(include=[np.number])
    categorical = X.select_dtypes(exclude=[np.number])

    parts: list[np.ndarray] = []
    if not numeric.empty:
        scaled = StandardScaler().fit_transform(numeric.values)
        parts.append(scaled)
    if not categorical.empty:
        encoded = OrdinalEncoder(
            handle_unknown="use_encoded_value", unknown_value=-1
        ).fit_transform(categorical.values)
        parts.append(encoded)

    return np.hstack(parts) if parts else np.empty((len(X), 0))


def _consistency_score(
    X: np.ndarray, decisions: np.ndarray, n_neighbors: int = 5
) -> float:
    """
    For each sample, check what fraction of its k nearest neighbors
    received the same decision.  Average across all samples.
    High consistency → similar people treated similarly.
    """
    if X.shape[1] == 0 or len(X) <= n_neighbors:
        return 1.0
    nn = NearestNeighbors(n_neighbors=min(n_neighbors, len(X) - 1))
    nn.fit(X)
    _, indices = nn.kneighbors(X)
    scores: list[float] = []
    for i, neighbors in enumerate(indices):
        same = sum(1 for j in neighbors if decisions[j] == decisions[i])
        scores.append(same / len(neighbors))
    return float(np.mean(scores))


def _generalized_entropy_index(
    benefits: np.ndarray, alpha: float = 2
) -> float:
    """
    GE(α) — measures inequality in a distribution of benefits.
    α=0: mean log deviation, α=1: Theil index, α=2: half CV²
    """
    b = benefits.astype(float)
    mu = b.mean()
    if mu == 0 or len(b) == 0:
        return 0.0
    if alpha == 1:
        ratios = b / mu
        ratios = ratios[ratios > 0]
        return float(np.mean(ratios * np.log(ratios))) if len(ratios) > 0 else 0.0
    if alpha == 0:
        ratios = b / mu
        ratios = ratios[ratios > 0]
        return float(-np.mean(np.log(ratios))) if len(ratios) > 0 else 0.0
    return float(
        (1.0 / (alpha * (alpha - 1))) * np.mean((b / mu) ** alpha - 1)
    )


def _between_within_entropy(
    benefits: np.ndarray, groups: np.ndarray, alpha: float = 2
) -> tuple[float, float]:
    """Decompose GE into between-group and within-group components."""
    total_ge = _generalized_entropy_index(benefits, alpha)
    mu = benefits.mean()
    if mu == 0 or total_ge == 0:
        return 0.0, 0.0

    unique_groups = np.unique(groups)
    group_means = np.array([benefits[groups == g].mean() for g in unique_groups])
    group_sizes = np.array([np.sum(groups == g) for g in unique_groups])

    # Between-group: GE of group means (repeated per member)
    between = _generalized_entropy_index(
        np.repeat(group_means, group_sizes), alpha
    )
    within = max(0.0, total_ge - between)
    return between, within
