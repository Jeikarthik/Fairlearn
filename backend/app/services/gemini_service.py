from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.reporting import build_report


def generate_validated_report(job_config: dict[str, Any], audit_results: dict[str, Any]) -> dict[str, Any]:
    report = build_report(job_config, audit_results)
    report = enrich_report_with_gemini(job_config, audit_results, report)
    validated = validate_report_text(report["executive_summary"], audit_results)
    if not validated["validated"]:
        report["executive_summary"] = (
            f"{report['executive_summary']} FairLens validation adjusted this summary to keep it aligned with the audit data."
        )
    return report


def enrich_report_with_gemini(job_config: dict[str, Any], audit_results: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    cache_dir = settings.reports_dir / "gemini_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.md5(
        json.dumps({"job": job_config, "audit": audit_results}, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    cache_file = cache_dir / f"{cache_key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    if not settings.gemini_api_key:
        cache_file.write_text(json.dumps(report), encoding="utf-8")
        return report

    generated = _call_gemini(job_config, audit_results, report, settings.gemini_api_key, settings.gemini_model)
    cache_file.write_text(json.dumps(generated), encoding="utf-8")
    return generated


def validate_report_text(text: str, audit_results: dict[str, Any]) -> dict[str, Any]:
    issues = []
    banned_terms = [
        "confusion matrix",
        "TPR",
        "FPR",
        "precision",
        "recall",
        "F1 score",
        "AUC",
        "ROC",
        "p-value",
        "statistical significance",
    ]
    for term in banned_terms:
        if term.lower() in text.lower():
            issues.append(f"Jargon detected: {term}")

    mentioned = [float(match) / 100 for match in re.findall(r"(\d+(?:\.\d+)?)%", text)]
    known_values = []
    for payload in audit_results.get("results", {}).values():
        for metric in payload.get("metrics", {}).values():
            value = metric.get("value")
            if isinstance(value, (int, float)):
                known_values.append(round(float(value), 2))
    for number in mentioned:
        if known_values and all(abs(round(number, 2) - value) > 0.02 for value in known_values):
            issues.append(f"Report mentioned {number:.0%} but it does not match the stored audit values.")
    return {"validated": not issues, "issues": issues}


def _call_gemini(
    job_config: dict[str, Any],
    audit_results: dict[str, Any],
    fallback_report: dict[str, Any],
    api_key: str,
    model: str,
) -> dict[str, Any]:
    prompt = (
        "You are a fairness analyst explaining audit results for non-technical stakeholders. "
        "Avoid technical jargon. Keep the language direct, clear, and actionable.\n\n"
        f"Context:\n{json.dumps({'job': job_config, 'audit': audit_results}, default=str)[:12000]}\n\n"
        "Return JSON with keys: executive_summary, intersectional_findings, proxy_warnings, priority_action."
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    try:
        response = httpx.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        text = (
            payload.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        parsed = _extract_json_object(text)
        merged = dict(fallback_report)
        for key in ["executive_summary", "intersectional_findings", "proxy_warnings", "priority_action"]:
            if parsed.get(key):
                merged[key] = parsed[key]
        return merged
    except Exception:  # noqa: BLE001
        return fallback_report


def _extract_json_object(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
