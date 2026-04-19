"""Drift alerting rules engine.

Evaluates per-metric threshold rules against live monitoring state and
emits alerts when rules are breached.  Rules are stored inside the
monitor job's config_json so they require no additional schema migration.

A rule dict:
  {
    "id":          str,          # unique rule identifier (uuid)
    "metric":      str,          # e.g. "demographic_parity_difference"
    "attribute":   str | None,   # protected attribute to watch (None = any)
    "operator":    str,          # ">" | ">=" | "<" | "<=" | "==" | "!="
    "threshold":   float,        # trigger value
    "channel":     str,          # "log" | "webhook"
    "webhook_url": str | None,   # required when channel="webhook"
    "description": str,          # human-readable label
    "enabled":     bool,         # can be toggled without deletion
  }

Alert payload emitted to webhook:
  {
    "alert_id":    str,
    "job_id":      str,
    "rule_id":     str,
    "metric":      str,
    "attribute":   str | None,
    "value":       float,
    "threshold":   float,
    "operator":    str,
    "description": str,
    "fired_at":    ISO-8601 str,
  }
"""
from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

logger = logging.getLogger("fairlens.alerting")

_OPERATORS = {
    ">":  lambda v, t: v > t,
    ">=": lambda v, t: v >= t,
    "<":  lambda v, t: v < t,
    "<=": lambda v, t: v <= t,
    "==": lambda v, t: v == t,
    "!=": lambda v, t: v != t,
}


# ── Rule management ───────────────────────────────────────────────


def add_rule(config: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    """Append a validated rule to config["alert_rules"] and return updated config."""
    _validate_rule(rule)
    rules: list[dict[str, Any]] = config.get("alert_rules", [])
    if not any(r["id"] == rule.get("id") for r in rules):
        rule.setdefault("id", str(uuid.uuid4()))
        rule.setdefault("enabled", True)
        rules.append(rule)
    config["alert_rules"] = rules
    return config


def remove_rule(config: dict[str, Any], rule_id: str) -> dict[str, Any]:
    """Remove a rule by id from config["alert_rules"]."""
    config["alert_rules"] = [r for r in config.get("alert_rules", []) if r["id"] != rule_id]
    return config


def list_rules(config: dict[str, Any]) -> list[dict[str, Any]]:
    return config.get("alert_rules", [])


# ── Evaluation ────────────────────────────────────────────────────


def evaluate_rules(
    job_id: str,
    config: dict[str, Any],
    monitoring_state: dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate all enabled rules against the latest monitoring metrics.

    Returns a list of fired alert dicts (one per triggered rule).
    Side effect: sends webhook if channel="webhook".
    """
    rules = [r for r in config.get("alert_rules", []) if r.get("enabled", True)]
    if not rules:
        return []

    # Extract current per-attribute metric values from monitoring state
    current_metrics = _extract_metrics(monitoring_state)
    fired: list[dict[str, Any]] = []

    for rule in rules:
        metric = rule["metric"]
        attribute = rule.get("attribute")
        op_fn = _OPERATORS.get(rule["operator"])
        if op_fn is None:
            continue

        # Collect matching (attribute, value) pairs
        pairs: list[tuple[str | None, float]] = []
        for attr, metrics in current_metrics.items():
            if attribute and attr != attribute:
                continue
            val = metrics.get(metric)
            if val is not None:
                pairs.append((attr, val))

        for attr, value in pairs:
            if op_fn(value, rule["threshold"]):
                alert = _build_alert(job_id, rule, metric, attr, value)
                fired.append(alert)
                _dispatch(alert, rule)

    return fired


# ── Internal helpers ──────────────────────────────────────────────


def _extract_metrics(state: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Pull {attribute: {metric_name: value}} from monitoring state."""
    result: dict[str, dict[str, float]] = {}
    for attr, attr_data in state.get("results", {}).items():
        if not isinstance(attr_data, dict):
            continue
        metrics: dict[str, float] = {}
        for metric_name, metric_data in attr_data.get("metrics", {}).items():
            val = metric_data.get("value") if isinstance(metric_data, dict) else None
            if val is not None:
                metrics[metric_name] = float(val)
        if metrics:
            result[attr] = metrics
    return result


def _build_alert(
    job_id: str,
    rule: dict[str, Any],
    metric: str,
    attribute: str | None,
    value: float,
) -> dict[str, Any]:
    return {
        "alert_id": str(uuid.uuid4()),
        "job_id": job_id,
        "rule_id": rule["id"],
        "metric": metric,
        "attribute": attribute,
        "value": round(value, 6),
        "threshold": rule["threshold"],
        "operator": rule["operator"],
        "description": rule.get("description", ""),
        "fired_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


def _dispatch(alert: dict[str, Any], rule: dict[str, Any]) -> None:
    channel = rule.get("channel", "log")

    if channel == "log":
        logger.warning(
            "ALERT fired: %s %s %s (value=%.4f threshold=%.4f) job=%s",
            alert["metric"],
            rule["operator"],
            rule["threshold"],
            alert["value"],
            rule["threshold"],
            alert["job_id"],
        )
        return

    if channel == "webhook":
        webhook_url = rule.get("webhook_url")
        if not webhook_url:
            logger.error("Alert rule %s has channel='webhook' but no webhook_url", rule["id"])
            return
        try:
            import json
            import urllib.request
            data = json.dumps(alert).encode()
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                logger.info(
                    "Alert webhook delivered: rule=%s status=%s",
                    rule["id"], resp.status,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Alert webhook failed for rule %s: %s", rule["id"], exc)


def _validate_rule(rule: dict[str, Any]) -> None:
    required = {"metric", "operator", "threshold", "channel"}
    missing = required - rule.keys()
    if missing:
        raise ValueError(f"Alert rule missing required fields: {missing}")
    if rule["operator"] not in _OPERATORS:
        raise ValueError(f"Unknown operator '{rule['operator']}'. Use one of {list(_OPERATORS)}")
    if not isinstance(rule["threshold"], (int, float)):
        raise ValueError("threshold must be a number")
    if rule["channel"] not in ("log", "webhook"):
        raise ValueError("channel must be 'log' or 'webhook'")
    if rule["channel"] == "webhook" and not rule.get("webhook_url"):
        raise ValueError("webhook_url is required when channel='webhook'")
