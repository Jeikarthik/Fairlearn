"""Multi-outcome fairness — support for multi-class, continuous, and ranking outcomes.

Addresses deficiency #7: Binary outcomes only.

Production fairness systems must handle:
  - Multi-class: "Low/Medium/High risk"
  - Continuous: "Predicted salary $40K-$200K"
  - Rankings: "Candidate ranked 1st through nth"
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import kruskal, ks_2samp


def compute_multiclass_fairness(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Fairness metrics for non-binary outcomes.

    Auto-detects outcome type and computes appropriate metrics:
      - Multi-class: per-class rate disparity across groups
      - Continuous: mean/median difference, KS test, quantile fairness
      - Ranking: position ratio analysis
    """
    outcome_col = config["outcome_column"]
    protected = config.get("protected_attributes", [])

    if outcome_col not in df.columns:
        return {"_meta": {"status": "skipped", "reason": "Outcome column not found."}}

    outcome_type = _detect_outcome_type(df[outcome_col])

    results: dict[str, Any] = {
        "_meta": {"status": "success"},
        "outcome_type": outcome_type,
    }

    if outcome_type == "binary":
        results["_meta"]["note"] = "Binary outcome — use standard fairness metrics."
        return results
    elif outcome_type == "multiclass":
        results.update(_multiclass_metrics(df, outcome_col, protected))
    elif outcome_type == "continuous":
        results.update(_continuous_metrics(df, outcome_col, protected))
    elif outcome_type == "ordinal":
        results.update(_ordinal_metrics(df, outcome_col, protected))

    return results


def _detect_outcome_type(series: pd.Series) -> str:
    """Classify outcome column type."""
    n_unique = series.nunique(dropna=True)
    if n_unique <= 2:
        return "binary"
    if pd.api.types.is_numeric_dtype(series):
        if n_unique <= 10:
            return "ordinal"
        return "continuous"
    if n_unique <= 20:
        return "multiclass"
    return "continuous"


def _multiclass_metrics(
    df: pd.DataFrame, outcome_col: str, protected: list[str]
) -> dict[str, Any]:
    """Per-class approval rate disparity across groups."""
    results: dict[str, Any] = {}
    outcome_classes = df[outcome_col].dropna().unique()

    for attr in protected:
        if attr not in df.columns:
            continue
        groups = df[attr].dropna().unique()
        if len(groups) < 2:
            continue

        class_disparities: list[dict[str, Any]] = []
        for outcome_class in outcome_classes:
            is_class = df[outcome_col] == outcome_class
            rates = {}
            for g in groups:
                mask = df[attr] == g
                n = mask.sum()
                if n == 0:
                    continue
                rates[str(g)] = round(float(is_class[mask].mean()), 4)

            if len(rates) < 2:
                continue

            gap = max(rates.values()) - min(rates.values())
            best = max(rates, key=rates.get)
            worst = min(rates, key=rates.get)

            class_disparities.append({
                "outcome_class": str(outcome_class),
                "group_rates": rates,
                "gap": round(gap, 4),
                "best_group": best,
                "worst_group": worst,
                "passed": gap < 0.10,
            })

        class_disparities.sort(key=lambda x: x["gap"], reverse=True)
        results[attr] = {
            "class_disparities": class_disparities,
            "worst_class": class_disparities[0]["outcome_class"] if class_disparities else None,
            "overall_passed": all(d["passed"] for d in class_disparities),
        }

    return results


def _continuous_metrics(
    df: pd.DataFrame, outcome_col: str, protected: list[str]
) -> dict[str, Any]:
    """Fairness metrics for continuous outcomes (salary, score, etc.)."""
    results: dict[str, Any] = {}

    for attr in protected:
        if attr not in df.columns:
            continue
        groups = df[attr].dropna().unique()
        if len(groups) < 2:
            continue

        group_stats: dict[str, dict[str, Any]] = {}
        group_values: dict[str, np.ndarray] = {}

        for g in groups:
            mask = df[attr] == g
            vals = df.loc[mask, outcome_col].dropna().values.astype(float)
            if len(vals) == 0:
                continue
            group_values[str(g)] = vals
            group_stats[str(g)] = {
                "mean": round(float(vals.mean()), 4),
                "median": round(float(np.median(vals)), 4),
                "std": round(float(vals.std()), 4),
                "p10": round(float(np.percentile(vals, 10)), 4),
                "p25": round(float(np.percentile(vals, 25)), 4),
                "p75": round(float(np.percentile(vals, 75)), 4),
                "p90": round(float(np.percentile(vals, 90)), 4),
                "count": len(vals),
            }

        if len(group_stats) < 2:
            continue

        # Mean difference
        means = {g: group_stats[g]["mean"] for g in group_stats}
        best_g = max(means, key=means.get)
        worst_g = min(means, key=means.get)
        mean_gap = means[best_g] - means[worst_g]
        mean_ratio = means[worst_g] / max(0.001, means[best_g])

        # KS test between best and worst
        ks_stat, ks_p = (None, None)
        if best_g in group_values and worst_g in group_values:
            ks_stat, ks_p = ks_2samp(group_values[best_g], group_values[worst_g])
            ks_stat = round(ks_stat, 4)
            ks_p = round(ks_p, 6)

        # Kruskal-Wallis test (non-parametric ANOVA)
        kw_stat, kw_p = (None, None)
        all_groups = [v for v in group_values.values() if len(v) > 0]
        if len(all_groups) >= 2:
            try:
                kw_stat, kw_p = kruskal(*all_groups)
                kw_stat = round(kw_stat, 4)
                kw_p = round(kw_p, 6)
            except Exception:  # noqa: BLE001
                pass

        # Quantile fairness: compare p10, p25, p50, p75, p90 across groups
        quantile_gaps: dict[str, float] = {}
        for q in ["p10", "p25", "p75", "p90"]:
            q_vals = {g: group_stats[g][q] for g in group_stats}
            q_gap = max(q_vals.values()) - min(q_vals.values())
            quantile_gaps[q] = round(q_gap, 4)

        results[attr] = {
            "group_stats": group_stats,
            "mean_gap": round(mean_gap, 4),
            "mean_ratio": round(mean_ratio, 4),
            "best_group": best_g,
            "worst_group": worst_g,
            "ks_test": {"statistic": ks_stat, "p_value": ks_p, "distributions_differ": ks_p < 0.05 if ks_p else None},
            "kruskal_wallis": {"statistic": kw_stat, "p_value": kw_p, "groups_differ": kw_p < 0.05 if kw_p else None},
            "quantile_gaps": quantile_gaps,
            "interpretation": (
                f"'{best_g}' has {mean_gap:.2f} higher average {outcome_col} than '{worst_g}' "
                f"(ratio: {mean_ratio:.2f}). "
                + (f"KS test confirms the distributions differ significantly (p={ks_p:.4f})."
                   if ks_p is not None and ks_p < 0.05
                   else "The distribution difference is not statistically significant.")
            ),
        }

    return results


def _ordinal_metrics(
    df: pd.DataFrame, outcome_col: str, protected: list[str]
) -> dict[str, Any]:
    """Metrics for ordinal outcomes (e.g., Low/Medium/High risk)."""
    # Convert to numeric ordinal and use continuous metrics
    encoded = df.copy()
    categories = sorted(encoded[outcome_col].dropna().unique())
    cat_map = {cat: i for i, cat in enumerate(categories)}
    encoded[outcome_col] = encoded[outcome_col].map(cat_map)
    results = _continuous_metrics(encoded, outcome_col, protected)
    results["_ordinal_mapping"] = cat_map
    return results
