"""Advanced statistical methods for production-grade fairness auditing.

Addresses 4 critical statistical deficiencies:
  1. Multiple Testing Correction (Benjamini-Hochberg FDR)
  2. Newcombe CI for Differences (replaces Wald-type)
  3. Statistical Power Analysis
  4. Effect Size Reporting (Cohen's h)
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import norm


# ─── 1. Multiple Testing Correction (Benjamini-Hochberg) ────────


def apply_fdr_correction(
    metric_results: dict[str, dict[str, Any]],
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Apply Benjamini-Hochberg FDR correction across ALL p-values.

    Collects every p-value from every attribute × metric combination,
    applies BH procedure, then updates each metric with:
      - corrected_p_value
      - significant_after_correction (bool)
      - correction_method: "benjamini_hochberg"
      - total_tests: how many tests were corrected across

    Returns a summary dict with overall correction metadata.
    """
    # Collect all (attribute, metric_name, p_value) triples
    p_entries: list[tuple[str, str, float]] = []
    for attr, attr_data in metric_results.items():
        significance = attr_data.get("significance", {})
        p_val = significance.get("p_value")
        if p_val is not None:
            p_entries.append((attr, "__overall__", p_val))

        for metric_name, metric_data in attr_data.get("metrics", {}).items():
            p_val = metric_data.get("p_value")
            if p_val is not None:
                p_entries.append((attr, metric_name, p_val))

    if not p_entries:
        return {"correction_applied": False, "reason": "No p-values available."}

    # Benjamini-Hochberg procedure
    m = len(p_entries)
    sorted_indices = sorted(range(m), key=lambda i: p_entries[i][2])
    corrected = [0.0] * m

    for rank_minus_1, orig_idx in enumerate(sorted_indices):
        rank = rank_minus_1 + 1
        raw_p = p_entries[orig_idx][2]
        corrected[orig_idx] = min(1.0, raw_p * m / rank)

    # Enforce monotonicity (step-up)
    for i in range(m - 2, -1, -1):
        idx = sorted_indices[i]
        idx_next = sorted_indices[i + 1]
        corrected[idx] = min(corrected[idx], corrected[idx_next])

    # Write back into metric_results
    for i, (attr, metric_name, _raw_p) in enumerate(p_entries):
        adj_p = round(corrected[i], 6)
        target: dict[str, Any]
        if metric_name == "__overall__":
            target = metric_results[attr].setdefault("significance", {})
        else:
            target = metric_results[attr]["metrics"][metric_name]
        target["corrected_p_value"] = adj_p
        target["significant_after_correction"] = adj_p < alpha
        target["correction_method"] = "benjamini_hochberg"

    n_significant_raw = sum(1 for _, _, p in p_entries if p < alpha)
    n_significant_corrected = sum(1 for c in corrected if c < alpha)

    return {
        "correction_applied": True,
        "method": "benjamini_hochberg",
        "alpha": alpha,
        "total_tests": m,
        "significant_before_correction": n_significant_raw,
        "significant_after_correction": n_significant_corrected,
        "false_positives_prevented": n_significant_raw - n_significant_corrected,
    }


# ─── 2. Newcombe CI for Difference of Proportions ───────────────


def newcombe_ci_diff(
    x1: int, n1: int, x2: int, n2: int, confidence: float = 0.95
) -> tuple[float, float]:
    """Newcombe Method 10 — CI for p1 - p2 using hybrid score intervals.

    This is the gold-standard CI for the difference of two independent
    proportions because it:
      - Never produces impossible CIs (outside [-1, 1])
      - Has correct coverage even at extreme proportions
      - Handles zero counts gracefully
    """
    if n1 == 0 or n2 == 0:
        return (0.0, 0.0)

    p1 = x1 / n1
    p2 = x2 / n2
    diff = p1 - p2

    l1, u1 = _wilson_score_ci(x1, n1, confidence)
    l2, u2 = _wilson_score_ci(x2, n2, confidence)

    lower = diff - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = diff + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)

    return (round(lower, 6), round(upper, 6))


def _wilson_score_ci(x: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a single proportion."""
    if n == 0:
        return (0.0, 0.0)
    z = norm.ppf(1 - (1 - confidence) / 2)
    p_hat = x / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


# ─── 3. Statistical Power Analysis ──────────────────────────────


def compute_power_analysis(
    n1: int, n2: int, p1: float, p2: float, alpha: float = 0.05
) -> dict[str, Any]:
    """Compute statistical power and minimum detectable effect.

    Returns:
      - power: probability of detecting the observed effect
      - min_detectable_effect: smallest difference detectable at 80% power
      - sample_size_needed: samples per group needed for 80% power on observed effect
      - interpretation: plain-language explanation
    """
    z_alpha = norm.ppf(1 - alpha / 2)

    # Power for the observed effect
    if n1 == 0 or n2 == 0:
        return {"power": 0.0, "interpretation": "Cannot compute — empty group."}

    p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2)) if p_pool > 0 and p_pool < 1 else 1e-10
    effect = abs(p1 - p2)
    z_effect = effect / se if se > 0 else 0
    power = 1 - norm.cdf(z_alpha - z_effect)
    power = round(min(1.0, max(0.0, power)), 4)

    # Minimum detectable effect at 80% power
    z_beta = norm.ppf(0.80)
    mde_se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2)) if p_pool > 0 and p_pool < 1 else 0.5
    mde = (z_alpha + z_beta) * mde_se
    mde = round(min(1.0, mde), 4)

    # Sample size needed for 80% power on the observed effect
    if effect > 0 and p_pool > 0 and p_pool < 1:
        n_needed = int(math.ceil(
            2 * ((z_alpha + z_beta) ** 2) * p_pool * (1 - p_pool) / (effect ** 2)
        ))
    else:
        n_needed = None

    # Interpretation
    if power >= 0.80:
        interp = (
            f"Adequate power ({power:.0%}). The test can reliably detect the "
            f"observed {effect:.1%} gap with your sample sizes ({n1}, {n2})."
        )
    else:
        interp = (
            f"LOW power ({power:.0%}). Your sample sizes ({n1}, {n2}) can only "
            f"reliably detect gaps ≥{mde:.1%}. The observed {effect:.1%} gap "
            f"may be real but your data is too small to confirm it."
        )
        if n_needed:
            interp += f" You would need ~{n_needed} per group for reliable detection."

    return {
        "power": power,
        "observed_effect": round(effect, 4),
        "min_detectable_effect": mde,
        "sample_size_per_group_needed": n_needed,
        "adequate_power": power >= 0.80,
        "interpretation": interp,
    }


# ─── 4. Effect Size Reporting (Cohen's h) ───────────────────────


def cohens_h(p1: float, p2: float) -> dict[str, Any]:
    """Cohen's h — standardized effect size for difference of proportions.

    Unlike raw difference, Cohen's h accounts for the fact that
    a 5% gap near 50% is more meaningful than a 5% gap near 95%.

    Magnitude thresholds (Cohen, 1988):
      |h| < 0.20  → Negligible
      0.20 ≤ |h| < 0.50 → Small
      0.50 ≤ |h| < 0.80 → Medium
      |h| ≥ 0.80  → Large
    """
    h1 = 2 * math.asin(math.sqrt(max(0, min(1, p1))))
    h2 = 2 * math.asin(math.sqrt(max(0, min(1, p2))))
    h = round(abs(h1 - h2), 4)

    if h < 0.20:
        magnitude = "negligible"
    elif h < 0.50:
        magnitude = "small"
    elif h < 0.80:
        magnitude = "medium"
    else:
        magnitude = "large"

    return {
        "cohens_h": h,
        "magnitude": magnitude,
        "interpretation": (
            f"Effect size is {magnitude} (h={h:.3f}). "
            + {
                "negligible": "The observed difference is unlikely to have practical significance.",
                "small": "The difference is small but may be practically meaningful in high-stakes decisions.",
                "medium": "The difference is substantial and likely has real-world impact.",
                "large": "The difference is very large — strong evidence of disparate treatment.",
            }[magnitude]
        ),
    }


def enrich_metrics_with_statistics(
    results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Run all advanced statistics on audit results and return enrichment data.

    Called after the base audit to add:
      - Newcombe CIs
      - Power analysis
      - Cohen's h effect sizes
      - FDR-corrected p-values
    """
    enrichment: dict[str, Any] = {}

    for attr, attr_data in results.items():
        group_stats = attr_data.get("group_stats", {})
        if len(group_stats) < 2:
            continue

        best_name = max(group_stats, key=lambda g: group_stats[g]["rate"])
        worst_name = min(group_stats, key=lambda g: group_stats[g]["rate"])
        best = group_stats[best_name]
        worst = group_stats[worst_name]

        attr_enrichment: dict[str, Any] = {}

        # Newcombe CI
        newcombe_lower, newcombe_upper = newcombe_ci_diff(
            best["favorable"], best["total"],
            worst["favorable"], worst["total"],
        )
        attr_enrichment["newcombe_ci"] = {
            "lower": newcombe_lower,
            "upper": newcombe_upper,
            "method": "newcombe_method_10",
        }

        # Power analysis
        attr_enrichment["power_analysis"] = compute_power_analysis(
            best["total"], worst["total"],
            best["rate"], worst["rate"],
        )

        # Cohen's h
        attr_enrichment["effect_size"] = cohens_h(best["rate"], worst["rate"])

        enrichment[attr] = attr_enrichment

    # FDR correction across all tests
    enrichment["_fdr_correction"] = apply_fdr_correction(results)

    return enrichment
