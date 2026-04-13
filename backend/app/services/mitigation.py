from __future__ import annotations

from typing import Any


def build_mitigation_cards(results: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for attribute, payload in results.get("results", {}).items():
        metrics = payload["metrics"]
        if _failed(metrics, "disparate_impact_ratio"):
            cards.append(
                {
                    "title": f"Reduce approval-rate imbalance for {attribute}",
                    "severity": "critical",
                    "triggered_by": "disparate_impact_ratio",
                    "attribute": attribute,
                    "action": "Retrain with fairness constraints or rebalance the dataset before the next release.",
                    "tradeoff": "Expected trade-off: fairness improves, overall accuracy may drop slightly.",
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
                }
            )
        if _failed(metrics, "demographic_parity_difference"):
            cards.append(
                {
                    "title": f"Bring approval rates closer together for {attribute}",
                    "severity": "warning",
                    "triggered_by": "demographic_parity_difference",
                    "attribute": attribute,
                    "action": "Review thresholds and screening rules that are suppressing one group’s approval rate.",
                    "tradeoff": "Expected trade-off: group outcomes become more balanced, but some existing rules may need revision.",
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
            }
        )
    return cards


def _failed(metrics: dict[str, Any], key: str) -> bool:
    metric = metrics.get(key)
    return bool(metric and metric.get("passed") is False)
