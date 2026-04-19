from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from app.services.plain_language import join_readable, make_monitoring_headline


def create_monitor_state(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "records": [],
        "snapshots": [],
        "alerts": [],
        "latest_status": "configured",
        "latest_snapshot": {},
    }


def ingest_monitoring_records(config: dict[str, Any], state: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    stored_records = list(state.get("records", []))
    stored_records.extend(records)
    window_size = int(config["thresholds"].get("alert_window_size", 50))
    # Cap stored records to prevent unbounded memory growth
    max_stored = window_size * 2
    stored_records = stored_records[-max_stored:]
    active_window = stored_records[-window_size:]

    snapshot = _compute_snapshot(active_window, config)
    alerts = _build_alerts(snapshot, config)
    latest_status = "alerting" if alerts else "monitoring"

    snapshots = list(state.get("snapshots", []))
    snapshots.append(snapshot)

    return {
        "records": stored_records,
        "snapshots": snapshots,
        "alerts": alerts,
        "latest_status": latest_status,
        "latest_snapshot": snapshot,
    }


def summarize_monitor_state(job_id: str, config: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    alerts = state.get("alerts", [])
    snapshot = state.get("latest_snapshot", {})
    records_seen = len(state.get("records", []))
    headline = make_monitoring_headline(len(alerts), config["system_name"])

    if not snapshot:
        summary = (
            f"{config['system_name']} is configured for continuous monitoring. "
            "Once webhook events arrive, FairLens will turn them into plain-language fairness updates."
        )
        action = "Connect the prediction pipeline to the webhook and send the first batch of records."
    else:
        watched = join_readable(config["protected_attributes"])
        summary = (
            f"FairLens has processed {records_seen} records and is watching {watched}. "
            f"The current monitoring window contains {snapshot['window_size']} recent decisions."
        )
        action = (
            "Review the alerts and decide whether the affected workflow needs a rollback, retraining, or manual review."
            if alerts
            else "Keep monitoring active and review trends after each new release or policy change."
        )

    return {
        "job_id": job_id,
        "status": state.get("latest_status", "configured"),
        "records_seen": records_seen,
        "insight_headline": headline,
        "insight_summary": summary,
        "recommended_action": action,
        "alerts": alerts,
        "latest_snapshot": snapshot,
    }


def _compute_snapshot(records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    prediction_field = config["prediction_field"]
    favorable_outcome = config["favorable_outcome"]
    attributes = config["protected_attributes"]

    per_attribute: dict[str, Any] = {}
    for attribute in attributes:
        counts_by_group: Counter[str] = Counter()
        favorable_by_group: Counter[str] = Counter()
        for record in records:
            group = str(record.get(attribute, "Unknown"))
            counts_by_group[group] += 1
            if record.get(prediction_field) == favorable_outcome:
                favorable_by_group[group] += 1

        rates = {
            group: favorable_by_group[group] / count
            for group, count in counts_by_group.items()
            if count > 0
        }
        gap = (max(rates.values()) - min(rates.values())) if len(rates) >= 2 else 0.0
        impact = (min(rates.values()) / max(rates.values())) if len(rates) >= 2 and max(rates.values()) > 0 else 1.0
        per_attribute[attribute] = {
            "group_counts": dict(counts_by_group),
            "approval_rates": {group: round(rate, 4) for group, rate in rates.items()},
            "demographic_parity_gap": round(gap, 4),
            "disparate_impact_ratio": round(impact, 4),
        }

    return {
        "window_size": len(records),
        "attributes": per_attribute,
    }


def _build_alerts(snapshot: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    thresholds = config["thresholds"]

    for attribute, details in snapshot.get("attributes", {}).items():
        gap = details["demographic_parity_gap"]
        impact = details["disparate_impact_ratio"]
        approval_rates = details["approval_rates"]
        if gap > thresholds["demographic_parity_gap"]:
            best_group = max(approval_rates, key=approval_rates.get)
            worst_group = min(approval_rates, key=approval_rates.get)
            alerts.append(
                {
                    "title": f"{attribute} decisions are separating across groups",
                    "summary": (
                        f"{worst_group} is being approved less often than {best_group} in the current monitoring window."
                    ),
                    "severity": "critical" if gap >= thresholds["demographic_parity_gap"] * 1.5 else "warning",
                }
            )
        if impact < thresholds["disparate_impact_ratio"]:
            alerts.append(
                {
                    "title": f"{attribute} fairness ratio dropped below your guardrail",
                    "summary": (
                        f"The least favored group is currently receiving approvals at only {impact:.0%} of the rate "
                        "of the most favored group."
                    ),
                    "severity": "critical" if impact < 0.7 else "warning",
                }
            )

    deduped: dict[str, dict[str, Any]] = {}
    for alert in alerts:
        deduped[alert["title"]] = alert
    return list(deduped.values())
