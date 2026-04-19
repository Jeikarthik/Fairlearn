from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, f_oneway, fisher_exact, kruskal, norm, pearsonr, pointbiserialr

from app.constants import (
    DEFAULT_AGE_BINS,
    DEFAULT_AGE_LABELS,
    MAX_INTERSECTIONAL_GROUPS,
    MIN_GROUP_SIZE,
)
from app.core.threshold_config import ThresholdConfig, algorithm_fingerprint, build_threshold_config
from app.core.sampling import maybe_sample
from app.services.explainability import generate_root_cause_analysis
from app.services.normalization import normalize_dataframe


def run_audit(df: pd.DataFrame, config: dict[str, Any], *, model_path: str | None = None) -> dict[str, Any]:
    import logging
    _logger = logging.getLogger("fairlens")

    # ── Config validation ──────────────────────────────────────
    from app.services.config_validation import validate_config_against_dataframe, validate_favorable_outcome
    col_errors = validate_config_against_dataframe(config, list(df.columns))
    if col_errors:
        return {"status": "error", "errors": col_errors, "_schema_version": 3}
    fav_errors = validate_favorable_outcome(config, df[config["outcome_column"]].unique().tolist())
    if fav_errors:
        return {"status": "error", "errors": fav_errors, "_schema_version": 3}

    # ── Build versioned threshold config ───────────────────────
    thresholds = build_threshold_config(config)

    # ── Large-dataset sampling ─────────────────────────────────
    df, sampling_meta = maybe_sample(df, config)
    if sampling_meta["sampled"]:
        _logger.warning(
            "Sampling %d → %d rows for audit (%.0f%%).",
            sampling_meta["original_rows"],
            sampling_meta["sample_rows"],
            sampling_meta["sampling_fraction"] * 100,
        )

    prepared = prepare_dataframe(df, config)

    # ── Normalization changelog (audit trail) ──────────────────
    from app.services.normalization import get_normalization_changelog
    normalization_changes = get_normalization_changelog(df, prepared)

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
            thresholds=thresholds,
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
            thresholds=thresholds,
        ),
        "normalization_changelog": normalization_changes,
        "sampling": sampling_meta,
        "threshold_config": {**thresholds.to_dict(), "fingerprint": thresholds.fingerprint()},
    }
    payload["root_cause_analysis"] = generate_root_cause_analysis(prepared, config, payload, model_path)

    # ── Extended Analysis Modules — run ALL in parallel ────────
    _MODULE_TIMEOUT = 120  # seconds per module

    def _safe(label: str, fn, *args, **kwargs):
        """Run fn in the current thread; ThreadPoolExecutor manages parallelism."""
        try:
            return fn(*args, **kwargs)
        except MemoryError:
            _logger.error("%s ran out of memory — propagating to surface OOM", label)
            raise  # OOM must not be silently swallowed — let the executor surface it
        except Exception as exc:  # noqa: BLE001
            _logger.warning("%s failed: %s", label, exc)
            return {"_meta": {"status": "error", "error": type(exc).__name__, "message": str(exc)}}

    # Build module task map
    from app.services.individual_fairness import compute_individual_fairness
    from app.services.fairlearn_crosscheck import crosscheck_metrics
    from app.services.advanced_statistics import enrich_metrics_with_statistics
    from app.services.data_diagnostics import (
        analyze_missing_patterns,
        detect_class_imbalance,
        verify_data_representativeness,
    )
    from app.services.causal_analysis import (
        compute_adjusted_metrics,
        detect_interaction_effects,
        detect_simpsons_paradox,
    )
    from app.services.calibration_fairness import compute_calibration_fairness
    from app.services.counterfactual_fairness import compute_counterfactual_fairness
    from app.services.outcome_analysis import compute_multiclass_fairness

    def _run_data_diagnostics():
        return {
            "missing_data": analyze_missing_patterns(prepared, config),
            "class_imbalance": detect_class_imbalance(prepared, config),
            "representativeness": verify_data_representativeness(prepared, config),
        }

    def _run_covariate_adjusted():
        return {
            "adjusted_metrics": compute_adjusted_metrics(prepared, config),
            "simpsons_paradox": detect_simpsons_paradox(prepared, config),
            "interaction_effects": detect_interaction_effects(prepared, config),
        }

    module_tasks = {
        "individual_fairness":   (compute_individual_fairness,  prepared, config),
        "fairlearn_crosscheck":  (crosscheck_metrics,           prepared, config),
        "advanced_statistics":   (enrich_metrics_with_statistics, results),
        "data_diagnostics":      (_run_data_diagnostics,),
        "covariate_adjusted":    (_run_covariate_adjusted,),
        "calibration_fairness":  (compute_calibration_fairness, prepared, config),
        "counterfactual_fairness": (compute_counterfactual_fairness, prepared, config),
        "multi_outcome":         (compute_multiclass_fairness,  prepared, config),
    }

    # Execute all modules in parallel using ThreadPoolExecutor
    future_to_label: dict[Any, str] = {}
    with ThreadPoolExecutor(max_workers=len(module_tasks)) as pool:
        for label, task in module_tasks.items():
            fn, *args = task
            future = pool.submit(_safe, label, fn, *args)
            future_to_label[future] = label

        for future in as_completed(future_to_label, timeout=_MODULE_TIMEOUT + 5):
            label = future_to_label[future]
            try:
                payload[label] = future.result(timeout=_MODULE_TIMEOUT)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Module %s timed out or failed: %s", label, exc)
                payload[label] = {"_meta": {"status": "timeout", "timeout_seconds": _MODULE_TIMEOUT}}

    # ── Keep "causal_analysis" as an alias for backward compatibility ──
    payload["causal_analysis"] = payload.get("covariate_adjusted", {})

    # ── Completeness scoring ─────────────────────────────────────
    analysis_sections = [
        "individual_fairness", "fairlearn_crosscheck", "advanced_statistics",
        "data_diagnostics", "covariate_adjusted", "calibration_fairness",
        "counterfactual_fairness", "multi_outcome",
    ]
    succeeded = sum(
        1 for s in analysis_sections
        if isinstance(payload.get(s), dict) and payload[s].get("_meta", {}).get("status") not in ("error", "timeout")
    )
    payload["_completeness"] = {
        "total_modules": len(analysis_sections),
        "succeeded": succeeded,
        "failed": len(analysis_sections) - succeeded,
        "score": round(succeeded / len(analysis_sections), 2),
    }
    payload["status"] = "complete" if succeeded == len(analysis_sections) else "partial"
    payload["_schema_version"] = 3
    payload["_algorithm_version"] = algorithm_fingerprint()

    return payload


def run_aggregate_audit(payload: dict[str, Any]) -> dict[str, Any]:
    """Run audit from aggregate group statistics (no raw data required).

    Supports the same config["domain"] / config["thresholds"] as file-based
    audits so thresholds are consistent across both modes.
    """
    groups = payload["groups"]
    config = payload.get("config", {})
    thresholds = build_threshold_config(config)

    rates = {group["name"]: group["favorable"] / max(group["total"], 1) for group in groups}
    best_group = max(rates, key=rates.get)
    worst_group = min(rates, key=rates.get)
    dpd = rates[best_group] - rates[worst_group]
    dir_value = rates[worst_group] / rates[best_group] if rates[best_group] else None

    from app.services.advanced_statistics import cohens_h, compute_power_analysis, newcombe_ci_diff

    best_data = next(g for g in groups if g["name"] == best_group)
    worst_data = next(g for g in groups if g["name"] == worst_group)
    ncl, ncu = newcombe_ci_diff(best_data["favorable"], best_data["total"], worst_data["favorable"], worst_data["total"])

    # Multi-group omnibus significance for aggregate mode
    group_favs = [g["favorable"] for g in groups]
    group_totals = [g["total"] for g in groups]
    omnibus_sig = _omnibus_significance(group_favs, group_totals)

    attr_name = payload["attribute_name"]
    group_stats_dict = {
        group["name"]: {
            "total": group["total"],
            "favorable": group["favorable"],
            "rate": round(rates[group["name"]], 4),
        }
        for group in groups
    }

    # Pairwise significance tests with BH correction
    pairwise = _pairwise_significance_corrected(groups)

    results_dict = {
        attr_name: {
            "metrics": {
                "demographic_parity_difference": _metric(
                    dpd, max(0.0, ncl), max(0.0, ncu),
                    thresholds.demographic_parity_threshold, higher_is_bad=True,
                ),
                "disparate_impact_ratio": _metric(
                    dir_value, dir_value, dir_value,
                    thresholds.disparate_impact_threshold, higher_is_bad=False,
                ),
            },
            "group_stats": group_stats_dict,
            "overall_passed": (
                abs(dpd) <= thresholds.demographic_parity_threshold
                and (dir_value or 0) >= thresholds.disparate_impact_threshold
            ),
            "failed_count": (
                int(abs(dpd) > thresholds.demographic_parity_threshold)
                + int((dir_value or 0) < thresholds.disparate_impact_threshold)
            ),
            "significance": _test_significance(
                best_data["favorable"], best_data["total"],
                worst_data["favorable"], worst_data["total"],
            ),
            "omnibus_significance": omnibus_sig,
            "pairwise_significance": pairwise,
        }
    }

    return {
        "status": "complete",
        "mode": "aggregate",
        "results": results_dict,
        "intersectional": {},
        "proxy_features": [],
        "advanced_statistics": {
            attr_name: {
                "newcombe_ci": {"lower": ncl, "upper": ncu, "method": "newcombe_method_10"},
                "power_analysis": compute_power_analysis(
                    best_data["total"], worst_data["total"],
                    rates[best_group], rates[worst_group],
                ),
                "effect_size": cohens_h(rates[best_group], rates[worst_group]),
            }
        },
        "threshold_config": {**thresholds.to_dict(), "fingerprint": thresholds.fingerprint()},
        "_schema_version": 3,
        "_algorithm_version": algorithm_fingerprint(),
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
        outcome_s, fav_coerced = _coerce_favorable(subset[outcome_column], favorable_outcome)
        subgroup = subset.assign(
            intersection=subset[left].astype(str) + "_" + subset[right].astype(str),
            _is_fav=(outcome_s == fav_coerced).astype(int),
        )
        grouped = subgroup.groupby("intersection")["_is_fav"].agg(["count", "sum"])
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
    thresholds: ThresholdConfig | None = None,
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
            # Use method-specific threshold if available
            threshold = (
                thresholds.proxy_threshold_for(method)
                if thresholds
                else 0.30
            )
            if value > threshold:
                findings.append(
                    {
                        "feature": feature,
                        "correlated_with": protected,
                        "correlation": round(value, 4),
                        "method": method,
                        "threshold_used": threshold,
                    }
                )
    findings.sort(key=lambda item: item["correlation"], reverse=True)
    return findings


def _coerce_favorable(series: pd.Series, favorable_outcome: Any) -> tuple[pd.Series, Any]:
    if pd.api.types.is_numeric_dtype(series):
        try:
            return series, float(favorable_outcome)
        except (ValueError, TypeError):
            return series.astype(str), str(favorable_outcome)
    return series.astype(str), str(favorable_outcome)


def _test_significance(
    group_a_fav: int, group_a_total: int,
    group_b_fav: int, group_b_total: int,
) -> dict[str, Any]:
    """Fisher exact or chi-squared test for two groups."""
    table = np.array([
        [group_a_fav, group_a_total - group_a_fav],
        [group_b_fav, group_b_total - group_b_fav],
    ])
    if table.min() < 0:
        return {"p_value": None, "significant": None, "method": "invalid"}
    try:
        if table.min() < 5:
            _, p_value = fisher_exact(table)
            method = "fisher_exact"
        else:
            chi2_val, p_value, _, _ = chi2_contingency(table)
            method = "chi_squared"
        return {"p_value": round(p_value, 4), "significant": p_value < 0.05, "method": method}
    except Exception:  # noqa: BLE001
        return {"p_value": None, "significant": None, "method": "error"}


def _omnibus_significance(
    group_favs: list[int],
    group_totals: list[int],
) -> dict[str, Any]:
    """Kruskal-Wallis omnibus test across ALL groups (3+ groups).

    For 2 groups this degenerates to a Mann-Whitney U, equivalent to
    chi-squared for binary outcomes.  Returns the omnibus p-value so
    callers know whether *any* pair is significantly different before
    looking at pairwise tests.
    """
    if len(group_favs) < 2:
        return {"p_value": None, "significant": None, "method": "not_applicable", "n_groups": len(group_favs)}
    if len(group_favs) == 2:
        return _test_significance(group_favs[0], group_totals[0], group_favs[1], group_totals[1])

    # Build binary outcome arrays per group for Kruskal-Wallis
    try:
        arrays = []
        for fav, total in zip(group_favs, group_totals):
            n_unfav = total - fav
            arrays.append(np.array([1] * fav + [0] * max(0, n_unfav)))
        stat, p_value = kruskal(*arrays)
        return {
            "p_value": round(float(p_value), 4),
            "significant": p_value < 0.05,
            "method": "kruskal_wallis",
            "statistic": round(float(stat), 4),
            "n_groups": len(group_favs),
        }
    except Exception:  # noqa: BLE001
        return {"p_value": None, "significant": None, "method": "error", "n_groups": len(group_favs)}


def _pairwise_significance_corrected(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Pairwise chi-squared / Fisher tests with Benjamini-Hochberg correction.

    Only run for 3+ groups (2-group audits already have the main significance test).
    Returns a dict of "GroupA vs GroupB" → {p_value, corrected_p_value, significant}.
    """
    if len(groups) < 3:
        return {"_meta": {"status": "skipped", "reason": "Pairwise tests only needed for 3+ groups."}}

    pairs = list(combinations(groups, 2))
    raw_results: list[tuple[str, float | None]] = []

    for g1, g2 in pairs:
        key = f"{g1['name']} vs {g2['name']}"
        sig = _test_significance(g1["favorable"], g1["total"], g2["favorable"], g2["total"])
        raw_results.append((key, sig.get("p_value"), sig.get("method", "unknown")))

    # BH correction on raw p-values
    p_values = [p for _, p, _ in raw_results if p is not None]
    m = len(p_values)
    if m == 0:
        return {"_meta": {"status": "no_p_values"}}

    sorted_idx = sorted(range(m), key=lambda i: p_values[i])
    corrected = [0.0] * m
    for rank_minus_1, orig_idx in enumerate(sorted_idx):
        corrected[orig_idx] = min(1.0, p_values[orig_idx] * m / (rank_minus_1 + 1))
    # Monotonicity
    for i in range(m - 2, -1, -1):
        corrected[sorted_idx[i]] = min(corrected[sorted_idx[i]], corrected[sorted_idx[i + 1]])

    output: dict[str, Any] = {"_meta": {"method": "benjamini_hochberg", "total_tests": m}}
    p_idx = 0
    for key, raw_p, method in raw_results:
        if raw_p is None:
            output[key] = {"p_value": None, "corrected_p_value": None, "significant": None, "method": method}
        else:
            adj_p = corrected[p_idx]
            output[key] = {
                "p_value": round(raw_p, 4),
                "corrected_p_value": round(adj_p, 6),
                "significant_after_correction": adj_p < 0.05,
                "method": method,
            }
            p_idx += 1

    return output


def _audit_attribute(
    df: pd.DataFrame,
    *,
    attribute: str,
    outcome_column: str,
    prediction_column: str | None,
    favorable_outcome: Any,
    thresholds: ThresholdConfig,
) -> dict[str, Any]:
    subset_columns = [attribute, outcome_column]
    if prediction_column:
        subset_columns.append(prediction_column)
    subset = df[subset_columns].dropna()
    grouped = subset.groupby(attribute)
    rates: dict[str, float] = {}
    rate_cis: dict[str, tuple[float, float]] = {}
    stats: dict[str, Any] = {}

    outcome_series, favorable_coerced = _coerce_favorable(subset[outcome_column], favorable_outcome)
    pred_series = None
    if prediction_column:
        pred_series, _ = _coerce_favorable(subset[prediction_column], favorable_outcome)

    for name, group in grouped:
        total = int(len(group))
        favorable = int((outcome_series.loc[group.index] == favorable_coerced).sum())
        rate = favorable / total if total else 0.0
        rates[str(name)] = rate
        rate_cis[str(name)] = wilson_ci(favorable, total)
        stats[str(name)] = {"total": total, "favorable": favorable, "rate": round(rate, 4)}

    metrics = {
        "demographic_parity_difference": _difference_metric(
            rates, rate_cis, thresholds.demographic_parity_threshold, group_stats=stats,
        ),
        "disparate_impact_ratio": _ratio_metric(
            rates, rate_cis, thresholds.disparate_impact_threshold,
        ),
    }

    if prediction_column and pred_series is not None:
        pred_match = pred_series == favorable_coerced
        out_match = outcome_series == favorable_coerced
        metrics["equal_opportunity_difference"] = _conditional_difference_metric(
            subset, attribute,
            numerator_mask=pred_match & out_match,
            denominator_mask=out_match,
            threshold=thresholds.equal_opportunity_threshold,
        )
        metrics["predictive_parity_difference"] = _conditional_difference_metric(
            subset, attribute,
            numerator_mask=pred_match & out_match,
            denominator_mask=pred_match,
            threshold=thresholds.predictive_parity_threshold,
        )
        metrics["accuracy_equity"] = _conditional_difference_metric(
            subset, attribute,
            numerator_mask=pred_series == outcome_series,
            denominator_mask=pd.Series([True] * len(subset), index=subset.index),
            threshold=thresholds.accuracy_equity_threshold,
        )
        metrics["fnr_disparity"] = _conditional_difference_metric(
            subset, attribute,
            numerator_mask=(~pred_match) & out_match,
            denominator_mask=out_match,
            threshold=thresholds.fnr_disparity_threshold,
        )

    # ── Multi-group significance testing ────────────────────────
    group_list = list(stats.values())
    group_names = list(stats.keys())

    # Omnibus test across all groups
    omnibus_sig = _omnibus_significance(
        [g["favorable"] for g in group_list],
        [g["total"] for g in group_list],
    )

    # Pairwise tests with BH correction (only meaningful for 3+ groups)
    pairwise_groups = [{"name": n, **stats[n]} for n in group_names]
    pairwise_sig = _pairwise_significance_corrected(pairwise_groups)

    # Legacy best-vs-worst significance (kept for backward compat)
    significance: dict[str, Any] = {}
    if len(stats) >= 2:
        best_name = max(stats, key=lambda g: stats[g]["rate"])
        worst_name = min(stats, key=lambda g: stats[g]["rate"])
        significance = _test_significance(
            stats[best_name]["favorable"], stats[best_name]["total"],
            stats[worst_name]["favorable"], stats[worst_name]["total"],
        )

    # Identify all failing groups
    failing_groups = []
    if len(rates) >= 2:
        best_group = max(rates, key=rates.get)
        failing_groups = [
            name for name, rate in rates.items()
            if name != best_group and (rates[best_group] - rate) > thresholds.demographic_parity_threshold
        ]

    failed_count = sum(1 for metric in metrics.values() if metric["passed"] is False)
    return {
        "metrics": metrics,
        "group_stats": stats,
        "overall_passed": failed_count == 0,
        "failed_count": failed_count,
        "significance": significance,
        "omnibus_significance": omnibus_sig,
        "pairwise_significance": pairwise_sig,
        "failing_groups": failing_groups,
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


def _difference_metric(
    rates: dict[str, float],
    cis: dict[str, tuple[float, float]],
    threshold: float,
    *,
    group_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if len(rates) < 2:
        return _metric(None, None, None, threshold, error="Need at least two groups to compare.")
    best = max(rates, key=rates.get)
    worst = min(rates, key=rates.get)
    value = rates[best] - rates[worst]
    from app.services.advanced_statistics import newcombe_ci_diff
    ci_lower = max(0.0, cis[best][0] - cis[worst][1])
    ci_upper = max(0.0, cis[best][1] - cis[worst][0])
    ci_method = "wald"
    try:
        if group_stats and best in group_stats and worst in group_stats:
            x1, n1 = group_stats[best]["favorable"], group_stats[best]["total"]
            x2, n2 = group_stats[worst]["favorable"], group_stats[worst]["total"]
        else:
            x1, n1 = int(rates[best] * 1000), 1000
            x2, n2 = int(rates[worst] * 1000), 1000
        ncl, ncu = newcombe_ci_diff(x1, n1, x2, n2)
        ci_lower = max(0.0, ncl)
        ci_upper = max(0.0, ncu)
        ci_method = "newcombe_method_10"
    except Exception:  # noqa: BLE001
        pass
    result = _metric(value, ci_lower, ci_upper, threshold, higher_is_bad=True)
    result["best_group"] = best
    result["worst_group"] = worst
    result["ci_method"] = ci_method
    return result


def _ratio_metric(
    rates: dict[str, float],
    cis: dict[str, tuple[float, float]],
    threshold: float,
) -> dict[str, Any]:
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
        conclusive = not (threshold is not None and ci_lower is not None and ci_upper is not None and ci_lower <= threshold <= ci_upper)
    elif higher_is_bad is False:
        passed = value >= (threshold or 0)
        conclusive = not (threshold is not None and ci_lower is not None and ci_upper is not None and ci_lower <= threshold <= ci_upper)
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
    if feature_numeric and not protected_numeric:
        n_groups = joined["protected"].nunique()
        if n_groups == 2:
            encoded = pd.Categorical(joined["protected"]).codes
            return abs(float(pointbiserialr(encoded, joined["feature"]).statistic)), "point_biserial"
        if n_groups >= 2:
            groups = [group["feature"].values for _, group in joined.groupby("protected")]
            if all(len(g) > 0 for g in groups):
                try:
                    f_stat, _ = f_oneway(*groups)
                    k = len(groups)
                    n = len(joined)
                    denominator = f_stat * (k - 1) + (n - k)
                    eta_sq = (f_stat * (k - 1)) / denominator if denominator > 0 else 0.0
                    return float(np.sqrt(max(0.0, eta_sq))), "eta_squared"
                except Exception:  # noqa: BLE001
                    return None, "eta_squared_error"
        return None, "unsupported"
    if feature_numeric and protected_numeric:
        return abs(float(pearsonr(joined["feature"], joined["protected"]).statistic)), "pearson"
    return None, "unsupported"
