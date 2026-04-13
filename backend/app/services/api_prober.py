from __future__ import annotations

import base64
import time
from typing import Any

import httpx

from app.services.plain_language import join_readable


def build_api_probe_pairs(config: dict[str, Any]) -> list[dict[str, Any]]:
    fields = list(config["input_schema"].items())
    pairs: list[dict[str, Any]] = []
    for index in range(config.get("num_test_pairs", 12)):
        base_payload = {}
        for field_name, field_type in fields:
            if field_name == config["protected_attribute"]:
                continue
            base_payload[field_name] = _sample_value(field_name, field_type, index)
        prompts = {
            group: {**base_payload, config["protected_attribute"]: group}
            for group in config["group_values"]
        }
        pairs.append({"pair_id": f"probe-{index + 1}", "payloads": prompts})
    return pairs


def run_api_probe(config: dict[str, Any], mock_outcomes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    pairs = build_api_probe_pairs(config)
    mocked = {(item["pair_id"], item["group"]): item["response"] for item in (mock_outcomes or [])}
    pair_results: list[dict[str, Any]] = []
    mismatches = 0
    failed_calls = 0

    for pair in pairs:
        outcomes = {}
        for group, payload in pair["payloads"].items():
            response = mocked.get((pair["pair_id"], group))
            if response is None and config.get("api_endpoint"):
                try:
                    response = _send_with_backoff(config, payload)
                except Exception as exc:  # noqa: BLE001
                    response = {"error": str(exc)}
                    failed_calls += 1
            label = _classify_response(response, config)
            outcomes[group] = {"response": response, "label": label}
        changed = len({item["label"] for item in outcomes.values()}) > 1
        mismatches += int(changed)
        pair_results.append({"pair_id": pair["pair_id"], "changed_between_groups": changed, "outcomes": outcomes})

    discrepancy_rate = mismatches / max(len(pair_results), 1)
    fail_rate = failed_calls / max(len(pair_results) * max(len(config["group_values"]), 1), 1)
    status = "failed" if discrepancy_rate >= 0.25 else "partial" if fail_rate > 0.3 or discrepancy_rate > 0 else "complete"
    headline = (
        f"{config['system_name']} responds differently when only {config['protected_attribute']} changes"
        if discrepancy_rate > 0
        else f"{config['system_name']} stayed consistent in the current API probe set"
    )
    summary = (
        f"FairLens tested {len(pair_results)} matched API input pairs across {join_readable(config['group_values'])}. "
        f"The response changed in {discrepancy_rate:.0%} of those pairs. "
        f"{'Some calls failed during probing.' if fail_rate > 0 else 'No probe-call failures were detected.'}"
    )
    findings = []
    if discrepancy_rate > 0:
        findings.append(
            {
                "title": "Counterfactual mismatch detected",
                "summary": "The API gave different decisions to otherwise matched inputs.",
                "severity": "critical" if discrepancy_rate >= 0.25 else "warning",
            }
        )
    if fail_rate > 0.3:
        findings.append(
            {
                "title": "Probe reliability issue",
                "summary": "A large share of API calls failed, so this run is only partially reliable.",
                "severity": "warning",
            }
        )
    if not findings:
        findings.append(
            {"title": "No major inconsistency detected", "summary": "The current probe set stayed aligned across groups.", "severity": "info"}
        )
    recommended_action = (
        f"Review the decision logic tied to {config['protected_attribute']} and replay the probe before release."
        if discrepancy_rate > 0
        else "Keep this API probe in regression testing whenever the external model or vendor configuration changes."
    )
    return {
        "job_id": config["job_id"],
        "status": status,
        "insight_headline": headline,
        "insight_summary": summary,
        "recommended_action": recommended_action,
        "discrepancy_rate": round(discrepancy_rate, 4),
        "findings": findings,
        "pair_results": pair_results,
    }


def _send_with_backoff(config: dict[str, Any], payload: dict[str, Any]) -> Any:
    endpoint = config["api_endpoint"]
    headers = {}
    params = {}
    auth_cfg = config.get("auth", {})
    if auth_cfg.get("type") == "bearer":
        headers["Authorization"] = f"Bearer {auth_cfg.get('key_value', '')}"
    elif auth_cfg.get("type") == "api_key_header":
        headers[auth_cfg.get("key_name") or "X-API-Key"] = auth_cfg.get("key_value") or ""
    elif auth_cfg.get("type") == "api_key_query":
        params[auth_cfg.get("key_name") or "api_key"] = auth_cfg.get("key_value") or ""
    elif auth_cfg.get("type") == "basic":
        token = base64.b64encode(f"{auth_cfg.get('username','')}:{auth_cfg.get('password','')}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {token}"

    delay = 1.0
    for _ in range(5):
        response = httpx.request(config.get("method", "POST"), endpoint, json=payload, headers=headers, params=params, timeout=10.0)
        if response.status_code == 429:
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
            continue
        response.raise_for_status()
        if "application/json" in response.headers.get("content-type", ""):
            return response.json()
        return response.text
    raise RuntimeError("API probe exhausted retries after repeated rate-limit responses.")


def _sample_value(name: str, field_type: str, index: int) -> Any:
    lowered = name.lower()
    if field_type in {"integer", "int"}:
        return 25 + (index % 15)
    if field_type in {"float", "number"}:
        return round(1000 + index * 37.5, 2)
    if "region" in lowered:
        return "Urban"
    if "income" in lowered:
        return "Mid"
    return f"{name}_{index + 1}"


def _classify_response(response: Any, config: dict[str, Any]) -> str:
    value = response
    if isinstance(response, dict) and config.get("decision_field"):
        value = _pluck(response, config["decision_field"])
    text = str(value).strip().lower()
    positives = {item.lower() for item in config.get("positive_values", [])}
    negatives = {item.lower() for item in config.get("negative_values", [])}
    if text in positives:
        return "positive"
    if text in negatives:
        return "negative"
    if any(token in text for token in ["approve", "allow", "accept", "positive", "safe"]):
        return "positive"
    if any(token in text for token in ["deny", "reject", "block", "negative", "unsafe"]):
        return "negative"
    return "unknown"


def _pluck(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current
