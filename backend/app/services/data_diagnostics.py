"""Data diagnostics — detect bias hidden in data quality issues.

Addresses 3 deficiencies:
  #12  Missing data bias analysis
  #13  Class imbalance detection
  #14  Adversarial robustness / distribution verification
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, ks_2samp


# ─── 1. Missing Data Bias Analysis ──────────────────────────────


def analyze_missing_patterns(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Detect whether missingness patterns differ across protected groups.

    For each (protected_attribute, feature) pair, computes per-group
    missing rates and runs a chi-squared test for association between
    group membership and missingness.

    A significant result means "this feature is more often missing for
    some groups" — which means dropna() biases the analysis.
    """
    protected = config.get("protected_attributes", [])
    outcome_col = config.get("outcome_column")
    pred_col = config.get("prediction_column")
    skip = {outcome_col, pred_col, *protected}
    feature_cols = [c for c in df.columns if c not in skip and c is not None]

    results: dict[str, Any] = {"_meta": {"status": "success"}}
    total_missing = int(df.isna().sum().sum())
    results["total_missing_values"] = total_missing
    results["total_cells"] = int(df.shape[0] * df.shape[1])
    results["overall_missing_rate"] = round(total_missing / max(1, results["total_cells"]), 4)

    for attr in protected:
        if attr not in df.columns:
            continue
        attr_findings: list[dict[str, Any]] = []
        groups = df[attr].dropna().unique()
        if len(groups) < 2:
            continue

        for feature in feature_cols:
            if feature not in df.columns:
                continue

            # Per-group missing rates
            group_missing: dict[str, float] = {}
            group_counts: dict[str, dict[str, int]] = {}
            for g in groups:
                mask = df[attr] == g
                n_group = int(mask.sum())
                n_missing = int(df.loc[mask, feature].isna().sum())
                rate = n_missing / max(1, n_group)
                group_missing[str(g)] = round(rate, 4)
                group_counts[str(g)] = {"total": n_group, "missing": n_missing}

            max_diff = max(group_missing.values()) - min(group_missing.values())
            if max_diff < 0.02:
                continue  # trivial difference

            # Chi-squared test: is missingness associated with group?
            p_value = None
            try:
                contingency = pd.crosstab(
                    df[attr].astype(str),
                    df[feature].isna().map({True: "missing", False: "present"}),
                )
                if contingency.shape[0] >= 2 and contingency.shape[1] >= 2:
                    _, p_value, _, _ = chi2_contingency(contingency)
                    p_value = round(p_value, 6)
            except Exception:  # noqa: BLE001
                pass

            severity = "critical" if max_diff > 0.10 else "warning" if max_diff > 0.05 else "info"
            most_affected = max(group_missing, key=group_missing.get)
            least_affected = min(group_missing, key=group_missing.get)

            attr_findings.append({
                "feature": feature,
                "group_missing_rates": group_missing,
                "max_difference": round(max_diff, 4),
                "p_value": p_value,
                "significant": p_value < 0.05 if p_value is not None else None,
                "severity": severity,
                "explanation": (
                    f"'{feature}' is missing {max_diff:.1%} more often for "
                    f"'{most_affected}' ({group_missing[most_affected]:.1%}) vs "
                    f"'{least_affected}' ({group_missing[least_affected]:.1%}). "
                    + ("This is statistically significant — dropna() introduces bias."
                       if p_value is not None and p_value < 0.05
                       else "Could be due to chance.")
                ),
            })

        # Sort by severity
        attr_findings.sort(key=lambda x: x["max_difference"], reverse=True)
        results[attr] = attr_findings

    return results


# ─── 2. Class Imbalance Detection ───────────────────────────────


def detect_class_imbalance(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Detect if extreme class imbalance hides bias in the minority class.

    When 95% of outcomes are "approved," standard rate-based metrics
    will show small disparities even if the 5% denial pool is extremely
    biased.  This module:
      1. Reports base rates and flags imbalance
      2. Analyzes the DENIED population separately
      3. Computes odds ratios (more appropriate for imbalanced data)
    """
    outcome_col = config["outcome_column"]
    favorable = config["favorable_outcome"]
    protected = config.get("protected_attributes", [])

    if outcome_col not in df.columns:
        return {"_meta": {"status": "skipped", "reason": "Outcome column not found."}}

    # Coerce favorable outcome comparison
    if pd.api.types.is_numeric_dtype(df[outcome_col]):
        try:
            is_favorable = df[outcome_col] == float(favorable)
        except (ValueError, TypeError):
            is_favorable = df[outcome_col].astype(str) == str(favorable)
    else:
        is_favorable = df[outcome_col].astype(str) == str(favorable)

    n_total = len(df)
    n_favorable = int(is_favorable.sum())
    n_unfavorable = n_total - n_favorable
    base_rate = n_favorable / max(1, n_total)

    results: dict[str, Any] = {
        "_meta": {"status": "success"},
        "total": n_total,
        "favorable": n_favorable,
        "unfavorable": n_unfavorable,
        "base_rate": round(base_rate, 4),
    }

    # Flag imbalance
    if base_rate > 0.95 or base_rate < 0.05:
        results["imbalance_severity"] = "extreme"
        results["imbalance_warning"] = (
            f"Extreme class imbalance: {base_rate:.1%} favorable rate. "
            "Standard fairness metrics may be misleading. "
            "Odds ratios and denied-population analysis are more reliable."
        )
    elif base_rate > 0.85 or base_rate < 0.15:
        results["imbalance_severity"] = "moderate"
        results["imbalance_warning"] = (
            f"Moderate class imbalance: {base_rate:.1%} favorable rate. "
            "Consider supplementing rate-based metrics with odds ratios."
        )
    else:
        results["imbalance_severity"] = "none"

    # Per-attribute: odds ratios + denied-population analysis
    for attr in protected:
        if attr not in df.columns:
            continue

        groups = df[attr].dropna().unique()
        if len(groups) < 2:
            continue

        group_data: dict[str, dict[str, Any]] = {}
        for g in groups:
            mask = df[attr] == g
            n_g = int(mask.sum())
            n_fav = int((mask & is_favorable).sum())
            n_unfav = n_g - n_fav
            rate = n_fav / max(1, n_g)
            odds = n_fav / max(1, n_unfav)
            group_data[str(g)] = {
                "total": n_g,
                "favorable": n_fav,
                "unfavorable": n_unfav,
                "rate": round(rate, 4),
                "odds": round(odds, 4),
            }

        # Odds ratio: best group vs worst group
        best_g = max(group_data, key=lambda g: group_data[g]["rate"])
        worst_g = min(group_data, key=lambda g: group_data[g]["rate"])
        best_odds = group_data[best_g]["odds"]
        worst_odds = group_data[worst_g]["odds"]
        odds_ratio = round(best_odds / max(0.001, worst_odds), 4)

        # Denied population composition
        denied = df[~is_favorable]
        if len(denied) > 0:
            denied_composition = {}
            for g in groups:
                n_denied_g = int((denied[attr] == g).sum())
                n_total_g = int((df[attr] == g).sum())
                denied_composition[str(g)] = {
                    "count": n_denied_g,
                    "share_of_denied": round(n_denied_g / max(1, len(denied)), 4),
                    "share_of_group_denied": round(n_denied_g / max(1, n_total_g), 4),
                }
        else:
            denied_composition = {}

        results[attr] = {
            "group_data": group_data,
            "odds_ratio": odds_ratio,
            "odds_ratio_interpretation": (
                f"'{best_g}' has {odds_ratio:.1f}x the odds of a favorable outcome "
                f"compared to '{worst_g}'."
                + (" This is a large disparity." if odds_ratio > 2.0 else "")
            ),
            "denied_population": denied_composition,
        }

    return results


# ─── 3. Distribution Verification (Adversarial Robustness) ─────


def verify_data_representativeness(
    df: pd.DataFrame,
    config: dict[str, Any],
    reference_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Check whether the audited data is a representative sample.

    Detects strategic sample selection (cherry-picking favorable data)
    by comparing the audited dataset's distributions against a reference
    dataset (e.g., full production data) or internal consistency checks.
    """
    protected = config.get("protected_attributes", [])
    results: dict[str, Any] = {"_meta": {"status": "success"}}

    # Internal consistency checks (no reference needed)
    checks: list[dict[str, Any]] = []

    # Check 1: Group size balance
    for attr in protected:
        if attr not in df.columns:
            continue
        counts = df[attr].value_counts()
        ratio = counts.min() / max(1, counts.max())
        if ratio < 0.1:
            checks.append({
                "check": "group_size_balance",
                "attribute": attr,
                "severity": "warning",
                "detail": (
                    f"Extreme group size imbalance for '{attr}': "
                    f"smallest group has {counts.min()} rows vs largest {counts.max()} "
                    f"(ratio: {ratio:.2f}). Small groups may not be representative."
                ),
                "group_sizes": counts.to_dict(),
            })

    # Check 2: Suspiciously uniform favorable rates
    outcome_col = config.get("outcome_column")
    favorable = config.get("favorable_outcome")
    if outcome_col and outcome_col in df.columns:
        for attr in protected:
            if attr not in df.columns:
                continue
            if pd.api.types.is_numeric_dtype(df[outcome_col]):
                try:
                    is_fav = df[outcome_col] == float(favorable)
                except (ValueError, TypeError):
                    is_fav = df[outcome_col].astype(str) == str(favorable)
            else:
                is_fav = df[outcome_col].astype(str) == str(favorable)

            rates = df.groupby(attr).apply(lambda g: is_fav.loc[g.index].mean())
            if rates.std() < 0.001 and len(rates) >= 2:
                checks.append({
                    "check": "suspiciously_uniform_rates",
                    "attribute": attr,
                    "severity": "warning",
                    "detail": (
                        f"All '{attr}' groups have nearly identical favorable rates "
                        f"(std={rates.std():.4f}). This is statistically unusual and "
                        "may indicate curated data."
                    ),
                })

    # Check 3: Distribution comparison with reference
    if reference_df is not None:
        for col in df.columns:
            if col not in reference_df.columns:
                continue
            if pd.api.types.is_numeric_dtype(df[col]) and pd.api.types.is_numeric_dtype(reference_df[col]):
                stat, p_val = ks_2samp(
                    df[col].dropna().values,
                    reference_df[col].dropna().values,
                )
                if p_val < 0.01:
                    checks.append({
                        "check": "distribution_drift",
                        "feature": col,
                        "severity": "critical" if p_val < 0.001 else "warning",
                        "ks_statistic": round(stat, 4),
                        "p_value": round(p_val, 6),
                        "detail": (
                            f"'{col}' distribution in audit data differs significantly "
                            f"from reference (KS={stat:.3f}, p={p_val:.4f}). "
                            "The audited sample may not represent production data."
                        ),
                    })

    results["checks"] = checks
    results["passed"] = not any(c["severity"] == "critical" for c in checks)
    results["warnings"] = sum(1 for c in checks if c["severity"] == "warning")
    results["critical"] = sum(1 for c in checks if c["severity"] == "critical")

    return results
