from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, norm, pearsonr, pointbiserialr

from app.constants import (
    ACCURACY_EQUITY_THRESHOLD,
    DEFAULT_AGE_BINS,
    DEFAULT_AGE_LABELS,
    DEMOGRAPHIC_PARITY_THRESHOLD,
    DISPARATE_IMPACT_THRESHOLD,
    EQUAL_OPPORTUNITY_THRESHOLD,
    FNR_DISPARITY_THRESHOLD,
    MAX_INTERSECTIONAL_GROUPS,
    MIN_GROUP_SIZE,
    PREDICTIVE_PARITY_THRESHOLD,
    PROXY_CORRELATION_THRESHOLD,
)
from app.services.explainability import generate_root_cause_analysis
from app.services.normalization import normalize_dataframe


def run_audit(df: pd.DataFrame, config: dict[str, Any], *, model_path: str | None = None) -> dict[str, Any]:
    prepared = prepare_dataframe(df, config)
    outcome_column = config["outcome_column"]
    prediction_column = config.get("prediction_column")
    favorable_outcome = config["favorable_outcome"]
    protected_attributes = config.get("protected_attributes", [])

    results: dict[str, Any] = {}
    for attribute in protected_attributes:
        if attribute not in prepared.columns:
            continue
        results[attribute] = _audit_attribute(
            prepared,
            attribute=attribute,
            outcome_column=outcome_column,
            prediction_column=prediction_column,
            favorable_outcome=favorable_outcome,
        )

    payload = {
        "status": "complete",
        "mode": config.get("mode") or ("prediction" if prediction_column else "dataset"),
        "results": results,
        "intersectional": build_intersectional(prepared, protected_attributes, outcome_column, favorable_outcome),
        "proxy_features": scan_proxy_features(
            prepared,
            protected_attributes=protected_attributes,
            outcome_column=outcome_column,
            prediction_column=prediction_column,
        ),
    }
    payload["root_cause_analysis"] = generate_root_cause_analysis(prepared, config, payload, model_path)
    return payload


def run_aggregate_audit(payload: dict[str, Any]) -> dict[str, Any]:
    groups = payload["groups"]
    rates = {group["name"]: group["favorable"] / max(group["total"], 1) for group in groups}
    best_group = max(rates, key=rates.get)
    worst_group = min(rates, key=rates.get)
    dpd = rates[best_group] - rates[worst_group]
    dir_value = rates[worst_group] / rates[best_group] if rates[best_group] else None
    return {
        "status": "complete",
        "mode": "aggregate",
        "results": {
            payload["attribute_name"]: {
                "metrics": {
                    "demographic_parity_difference": _metric(dpd, 0.0, 0.0, DEMOGRAPHIC_PARITY_THRESHOLD, higher_is_bad=True),
                    "disparate_impact_ratio": _metric(dir_value, dir_value, dir_value, DISPARATE_IMPACT_THRESHOLD, higher_is_bad=False),
                },
                "group_stats": {
                    group["name"]: {
                        "total": group["total"],
                        "favorable": group["favorable"],
                        "rate": round(rates[group["name"]], 4),
                    }
                    for group in groups
                },
                "overall_passed": abs(dpd) <= DEMOGRAPHIC_PARITY_THRESHOLD and (dir_value or 0) >= DISPARATE_IMPACT_THRESHOLD,
                "failed_count": int(abs(dpd) > DEMOGRAPHIC_PARITY_THRESHOLD) + int((dir_value or 0) < DISPARATE_IMPACT_THRESHOLD),
            }
        },
        "intersectional": {},
        "proxy_features": [],
    }


def prepare_dataframe(df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    prepared = normalize_dataframe(df)
    for column, strategy in config.get("continuous_binning", {}).items():
        if column not in prepared.columns:
            continue
        if strategy.get("edges"):
            edges = strategy["edges"]
            labels = [f"{edges[index]}-{edges[index + 1]}" for index in range(len(edges) - 1)]
            prepared[column] = pd.cut(prepared[column], bins=edges, labels=labels, include_lowest=True)
        elif strategy.get("method") == "quartile":
            prepared[column] = pd.qcut(prepared[column], q=4, duplicates="drop")
    for column in config.get("protected_attributes", []):
        if column in prepared.columns and pd.api.types.is_numeric_dtype(prepared[column]) and prepared[column].nunique(dropna=True) > 10:
            if "age" in column.lower():
                prepared[column] = pd.cut(
                    prepared[column],
                    bins=DEFAULT_AGE_BINS,
                    labels=DEFAULT_AGE_LABELS,
                    include_lowest=True,
                )
    return prepared


def build_intersectional(
    df: pd.DataFrame,
    protected_attributes: list[str],
    outcome_column: str,
    favorable_outcome: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for left, right in combinations(protected_attributes, 2):
        if left not in df.columns or right not in df.columns:
            continue
        key = f"{left}×{right}"
        subset = df[[left, right, outcome_column]].dropna()
        if subset.empty:
            continue
        subgroup = subset.assign(intersection=subset[left].astype(str) + "_" + subset[right].astype(str))
        grouped = subgroup.groupby("intersection")[outcome_column].agg(["count", "sum"])
        if grouped.empty or len(grouped) > MAX_INTERSECTIONAL_GROUPS:
            continue
        rates = grouped["sum"] / grouped["count"]
        best = rates.max()
        payload[key] = {
            name: {
                "total": int(grouped.loc[name, "count"]),
                "rate": round(rates.loc[name], 4),
                "disparity_vs_best": round((rates.loc[name] / best) if best else 0.0, 4),
                "reliable": bool(grouped.loc[name, "count"] >= MIN_GROUP_SIZE),
            }
            for name in grouped.index
        }
    return payload


def scan_proxy_features(
    df: pd.DataFrame,
    *,
    protected_attributes: list[str],
    outcome_column: str,
    prediction_column: str | None,
) -> list[dict[str, Any]]:
    skipped = {outcome_column, prediction_column, *protected_attributes}
    candidates = [column for column in df.columns if column not in skipped]
    findings: list[dict[str, Any]] = []
    for feature in candidates:
        for protected in protected_attributes:
            if feature not in df.columns or protected not in df.columns:
                continue
            value, method = _correlation(df[feature], df[protected])
            if value is None:
                continue
            if value > PROXY_CORRELATION_THRESHOLD:
                findings.append(
                    {
                        "feature": feature,
                        "correlated_with": protected,
                        "correlation": round(value, 4),
                        "method": method,
                    }
                )
    findings.sort(key=lambda item: item["correlation"], reverse=True)
    return findings


def _audit_attribute(
    df: pd.DataFrame,
    *,
    attribute: str,
    outcome_column: str,
    prediction_column: str | None,
    favorable_outcome: Any,
) -> dict[str, Any]:
    subset_columns = [attribute, outcome_column]
    if prediction_column:
        subset_columns.append(prediction_column)
    subset = df[subset_columns].dropna()
    grouped = subset.groupby(attribute)
    rates: dict[str, float] = {}
    rate_cis: dict[str, tuple[float, float]] = {}
    stats: dict[str, Any] = {}
    for name, group in grouped:
        total = int(len(group))
        favorable = int((group[outcome_column] == favorable_outcome).sum())
        rate = favorable / total if total else 0.0
        rates[str(name)] = rate
        rate_cis[str(name)] = wilson_ci(favorable, total)
        stats[str(name)] = {"total": total, "favorable": favorable, "rate": round(rate, 4)}

    metrics = {
        "demographic_parity_difference": _difference_metric(rates, rate_cis, DEMOGRAPHIC_PARITY_THRESHOLD),
        "disparate_impact_ratio": _ratio_metric(rates, rate_cis, DISPARATE_IMPACT_THRESHOLD),
    }

    if prediction_column:
        metrics["equal_opportunity_difference"] = _conditional_difference_metric(
            subset,
            attribute,
            numerator_mask=(subset[prediction_column] == favorable_outcome) & (subset[outcome_column] == favorable_outcome),
            denominator_mask=subset[outcome_column] == favorable_outcome,
            threshold=EQUAL_OPPORTUNITY_THRESHOLD,
        )
        metrics["predictive_parity_difference"] = _conditional_difference_metric(
            subset,
            attribute,
            numerator_mask=(subset[prediction_column] == favorable_outcome) & (subset[outcome_column] == favorable_outcome),
            denominator_mask=subset[prediction_column] == favorable_outcome,
            threshold=PREDICTIVE_PARITY_THRESHOLD,
        )
        metrics["accuracy_equity"] = _conditional_difference_metric(
            subset,
            attribute,
            numerator_mask=subset[prediction_column] == subset[outcome_column],
            denominator_mask=pd.Series([True] * len(subset)),
            threshold=ACCURACY_EQUITY_THRESHOLD,
        )
        metrics["fnr_disparity"] = _conditional_difference_metric(
            subset,
            attribute,
            numerator_mask=(subset[prediction_column] != favorable_outcome) & (subset[outcome_column] == favorable_outcome),
            denominator_mask=subset[outcome_column] == favorable_outcome,
            threshold=FNR_DISPARITY_THRESHOLD,
        )

    failed_count = sum(1 for metric in metrics.values() if metric["passed"] is False)
    return {
        "metrics": metrics,
        "group_stats": stats,
        "overall_passed": failed_count == 0,
        "failed_count": failed_count,
    }


def wilson_ci(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    z = norm.ppf(1 - (1 - confidence) / 2)
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    margin = z * np.sqrt((p * (1 - p) / total) + z**2 / (4 * total**2)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def _difference_metric(rates: dict[str, float], cis: dict[str, tuple[float, float]], threshold: float) -> dict[str, Any]:
    if len(rates) < 2:
        return _metric(None, None, None, threshold, error="Need at least two groups to compare.")
    best = max(rates, key=rates.get)
    worst = min(rates, key=rates.get)
    value = rates[best] - rates[worst]
    ci_lower = max(0.0, cis[best][0] - cis[worst][1])
    ci_upper = max(0.0, cis[best][1] - cis[worst][0])
    return _metric(value, ci_lower, ci_upper, threshold, higher_is_bad=True)


def _ratio_metric(rates: dict[str, float], cis: dict[str, tuple[float, float]], threshold: float) -> dict[str, Any]:
    if len(rates) < 2:
        return _metric(None, None, None, threshold, error="Need at least two groups to compare.")
    best = max(rates, key=rates.get)
    worst = min(rates, key=rates.get)
    if rates[best] == 0:
        return _metric(None, None, None, threshold, error="Reference group has zero favorable outcomes.")
    value = rates[worst] / rates[best]
    lower = 0.0 if cis[best][1] == 0 else cis[worst][0] / cis[best][1]
    upper = 1.0 if cis[best][0] == 0 else min(1.0, cis[worst][1] / cis[best][0])
    return _metric(value, lower, upper, threshold, higher_is_bad=False)


def _conditional_difference_metric(
    subset: pd.DataFrame,
    attribute: str,
    *,
    numerator_mask: pd.Series,
    denominator_mask: pd.Series,
    threshold: float,
) -> dict[str, Any]:
    rates: dict[str, float] = {}
    cis: dict[str, tuple[float, float]] = {}
    for name, group in subset.groupby(attribute):
        denominator_total = int(denominator_mask.loc[group.index].sum())
        numerator_total = int(numerator_mask.loc[group.index].sum())
        if denominator_total == 0:
            rates[str(name)] = 0.0
            cis[str(name)] = (0.0, 0.0)
            continue
        rates[str(name)] = numerator_total / denominator_total
        cis[str(name)] = wilson_ci(numerator_total, denominator_total)
    return _difference_metric(rates, cis, threshold)


def _metric(
    value: float | None,
    ci_lower: float | None,
    ci_upper: float | None,
    threshold: float | None,
    *,
    higher_is_bad: bool | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    if value is None:
        return {
            "value": None,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "threshold": threshold,
            "passed": None,
            "conclusive": False,
            "error": error,
        }
    if higher_is_bad is True:
        passed = value <= (threshold or 0)
        conclusive = False if threshold is not None and ci_lower is not None and ci_upper is not None and ci_lower <= threshold <= ci_upper else True
    elif higher_is_bad is False:
        passed = value >= (threshold or 0)
        conclusive = False if threshold is not None and ci_lower is not None and ci_upper is not None and ci_lower <= threshold <= ci_upper else True
    else:
        passed = None
        conclusive = True
    return {
        "value": round(value, 4),
        "ci_lower": None if ci_lower is None else round(ci_lower, 4),
        "ci_upper": None if ci_upper is None else round(ci_upper, 4),
        "threshold": threshold,
        "passed": passed,
        "conclusive": conclusive,
        "error": error,
    }


def _correlation(feature: pd.Series, protected: pd.Series) -> tuple[float | None, str]:
    joined = pd.DataFrame({"feature": feature, "protected": protected}).dropna()
    if joined.empty:
        return None, "none"
    feature_numeric = pd.api.types.is_numeric_dtype(joined["feature"])
    protected_numeric = pd.api.types.is_numeric_dtype(joined["protected"])
    if not feature_numeric and not protected_numeric:
        table = pd.crosstab(joined["feature"], joined["protected"])
        if table.shape[0] < 2 or table.shape[1] < 2:
            return None, "cramers_v"
        chi2 = chi2_contingency(table)[0]
        n = table.to_numpy().sum()
        phi2 = chi2 / n
        r, k = table.shape
        return float(np.sqrt(phi2 / max(min(k - 1, r - 1), 1))), "cramers_v"
    if feature_numeric and not protected_numeric and joined["protected"].nunique() == 2:
        encoded = pd.Categorical(joined["protected"]).codes
        return abs(float(pointbiserialr(encoded, joined["feature"]).statistic)), "point_biserial"
    if feature_numeric and protected_numeric:
        return abs(float(pearsonr(joined["feature"], joined["protected"]).statistic)), "pearson"
    return None, "unsupported"
