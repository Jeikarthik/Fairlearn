"""Gemini AI report generation with anti-hallucination hardening.

Anti-hallucination strategy (7 layers):
  1. GROUNDED PROMPT — System prompt forbids inventing numbers, cites only data
  2. FACT EXTRACTION — Pre-extract all numbers from audit data as a "fact sheet"
  3. STRUCTURED OUTPUT — responseMimeType forces JSON, no freetext parsing
  4. POST-GENERATION VALIDATION — Percentages AND decimals checked against known values
  5. CROSS-REFERENCE CHECK — Pass/fail claims verified + temporal claims blocked
  6. RETRY — On first hallucination, retry with stricter prompt
  7. HARD DISCARD — If retry also hallucinates, FULLY discard AI output, use template only
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.reporting import build_report

logger = logging.getLogger("fairlens")

_CACHE_SECRET = b"fairlens-cache-integrity-key"  # In production, load from env


def generate_validated_report(job_config: dict[str, Any], audit_results: dict[str, Any]) -> dict[str, Any]:
    """Generate and validate a report — DISCARDS AI output entirely if it hallucinates."""
    # Layer 0: Build the template report (always correct, zero hallucination)
    template_report = build_report(job_config, audit_results)
    template_report["_source"] = "template"

    # Attempt AI enrichment
    enriched = enrich_report_with_gemini(job_config, audit_results, dict(template_report))

    # Layer 4+5: Post-generation validation
    validation = validate_report_against_data(enriched, audit_results)

    if validation["passed"]:
        enriched["_validation"] = validation
        enriched["_source"] = "gemini_validated"
        return enriched

    # First attempt hallucinated — retry with stricter prompt
    logger.warning("Gemini hallucinated on first attempt: %s", validation["issues"][:3])
    enriched_retry = _retry_with_stricter_prompt(job_config, audit_results, dict(template_report))

    if enriched_retry:
        validation_retry = validate_report_against_data(enriched_retry, audit_results)
        if validation_retry["passed"]:
            enriched_retry["_validation"] = validation_retry
            enriched_retry["_source"] = "gemini_retry_validated"
            return enriched_retry

    # Layer 7: HARD DISCARD — both attempts hallucinated, use template ONLY
    logger.warning("Gemini hallucinated on both attempts — using template-only report")
    template_report["_validation"] = {
        "passed": True,
        "issues": [],
        "checks_run": ["template_fallback"],
        "ai_discarded": True,
        "discard_reason": validation["issues"][:5],
    }
    template_report["_source"] = "template_fallback"
    return template_report


def _retry_with_stricter_prompt(
    job_config: dict[str, Any], audit_results: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any] | None:
    """Retry Gemini with an even stricter prompt after first hallucination."""
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    return _call_gemini(
        job_config, audit_results, report,
        settings.gemini_api_key, settings.gemini_model,
        temperature=0.1,  # Even lower creativity
        extra_instruction="PREVIOUS ATTEMPT FAILED VALIDATION. Do NOT invent ANY numbers. "
                         "If unsure, use qualitative descriptions instead of quantities.",
    )


def enrich_report_with_gemini(
    job_config: dict[str, Any], audit_results: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    settings = get_settings()
    cache_dir = settings.reports_dir / "gemini_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    raw = json.dumps({"job": job_config, "audit": audit_results}, sort_keys=True, default=str).encode("utf-8")
    cache_key = hashlib.sha256(raw).hexdigest()
    cache_file = cache_dir / f"{cache_key}.json"
    hmac_file = cache_dir / f"{cache_key}.hmac"

    # Cache with HMAC integrity check (prevents cache poisoning)
    if cache_file.exists() and hmac_file.exists():
        cached_data = cache_file.read_bytes()
        expected_hmac = hmac_file.read_text(encoding="utf-8")
        actual_hmac = hmac.new(_CACHE_SECRET, cached_data, hashlib.sha256).hexdigest()
        if hmac.compare_digest(actual_hmac, expected_hmac):
            return json.loads(cached_data)
        else:
            logger.warning("Cache integrity check failed for %s — regenerating", cache_key[:8])

    if not settings.gemini_api_key:
        return report

    generated = _call_gemini(job_config, audit_results, report, settings.gemini_api_key, settings.gemini_model)

    # Write cache with HMAC
    cache_bytes = json.dumps(generated).encode("utf-8")
    cache_file.write_bytes(cache_bytes)
    hmac_file.write_text(
        hmac.new(_CACHE_SECRET, cache_bytes, hashlib.sha256).hexdigest(),
        encoding="utf-8",
    )
    return generated


# ─── Anti-Hallucination Layer 1: Fact Sheet Extraction ───────────


def _extract_fact_sheet(audit_results: dict[str, Any]) -> dict[str, Any]:
    """Extract every verifiable number from the audit into a lookup table.

    This gives the LLM a "cheat sheet" of correct numbers and gives
    the validator a ground truth to check against.
    """
    facts: dict[str, float] = {}
    claims: list[str] = []

    for attr, attr_data in audit_results.get("results", {}).items():
        for metric_name, metric_data in attr_data.get("metrics", {}).items():
            value = metric_data.get("value")
            if isinstance(value, (int, float)):
                key = f"{attr}.{metric_name}"
                facts[key] = round(float(value), 4)
                passed = metric_data.get("passed")
                claims.append(f"{attr} {metric_name} = {value:.4f} ({'PASS' if passed else 'FAIL'})")

        for group, stats in attr_data.get("group_stats", {}).items():
            rate = stats.get("rate")
            if isinstance(rate, (int, float)):
                facts[f"{attr}.{group}.rate"] = round(float(rate), 4)

    # Power analysis
    adv = audit_results.get("advanced_statistics", {})
    for attr, attr_adv in adv.items():
        if isinstance(attr_adv, dict):
            pa = attr_adv.get("power_analysis", {})
            if pa.get("power") is not None:
                facts[f"{attr}.power"] = pa["power"]
                claims.append(f"{attr} statistical power = {pa['power']:.0%}")

    # Counterfactual
    cf = audit_results.get("counterfactual_fairness", {})
    for attr, cf_data in cf.items():
        if isinstance(cf_data, dict) and "overall_flip_rate" in cf_data:
            facts[f"{attr}.counterfactual_flip_rate"] = cf_data["overall_flip_rate"]
            claims.append(f"{attr} counterfactual flip rate = {cf_data['overall_flip_rate']:.1%}")

    # Simpson's paradox
    causal = audit_results.get("causal_analysis", {})
    sp = causal.get("simpsons_paradox", {}) if isinstance(causal, dict) else {}
    for attr, sp_data in sp.items():
        if isinstance(sp_data, dict):
            paradoxes = sp_data.get("paradoxes_found", [])
            if paradoxes:
                claims.append(f"⚠️ Simpson's paradox detected for {attr}")

    return {"facts": facts, "claims": claims}


# ─── Anti-Hallucination Layer 2: Grounded Prompt ─────────────────


def _build_grounded_prompt(
    job_config: dict[str, Any],
    audit_results: dict[str, Any],
    fact_sheet: dict[str, Any],
) -> str:
    """Build a prompt that's grounded in verified facts."""

    fact_lines = "\n".join(f"  - {c}" for c in fact_sheet["claims"][:40])

    # Summarize new analysis modules for the prompt
    module_summaries: list[str] = []

    # Causal analysis
    causal = audit_results.get("causal_analysis", {})
    if isinstance(causal, dict):
        adj = causal.get("adjusted_metrics", {})
        if isinstance(adj, dict):
            for attr, adj_data in adj.items():
                if isinstance(adj_data, dict) and "interpretation" in adj_data:
                    module_summaries.append(f"Regression-adjusted ({attr}): {adj_data['interpretation']}")

    # Counterfactual
    cf = audit_results.get("counterfactual_fairness", {})
    if isinstance(cf, dict):
        for attr, cf_data in cf.items():
            if isinstance(cf_data, dict) and "interpretation" in cf_data:
                module_summaries.append(f"Counterfactual ({attr}): {cf_data['interpretation']}")

    # Data diagnostics
    diag = audit_results.get("data_diagnostics", {})
    if isinstance(diag, dict):
        imb = diag.get("class_imbalance", {})
        if isinstance(imb, dict) and imb.get("imbalance_warning"):
            module_summaries.append(f"Class imbalance: {imb['imbalance_warning']}")

    # Completeness
    comp = audit_results.get("_completeness", {})
    if comp:
        module_summaries.append(f"Analysis completeness: {comp.get('succeeded', 0)}/{comp.get('total_modules', 0)} modules succeeded")

    module_text = "\n".join(f"  - {s}" for s in module_summaries[:15])

    return f"""You are a fairness compliance analyst writing an official audit report.

CRITICAL RULES (violation = report rejected):
1. ONLY cite numbers from the VERIFIED FACTS below. Do NOT invent any percentages, rates, or statistics.
2. If you mention a number, it MUST appear in the verified facts. If you're unsure, say "the audit data shows" without a specific number.
3. NEVER use technical jargon: no "p-value", "TPR", "FPR", "AUC", "ROC", "F1", "precision", "recall".
4. Every claim must be directly supported by the data below.
5. Include findings from the advanced analysis modules (causal, counterfactual, data quality).

VERIFIED FACTS (use ONLY these numbers):
{fact_lines}

ADVANCED ANALYSIS FINDINGS:
{module_text}

AUDIT CONTEXT:
- Organization: {job_config.get('org_name', 'The organization')}
- Model/System: {job_config.get('model_name', 'the audited system')}
- Domain: {job_config.get('domain', 'the selected domain')}

Return a JSON object with exactly these keys:
- executive_summary: 3-5 sentences, plain language, cite only verified facts
- intersectional_findings: 2-3 sentences about compound group effects
- proxy_warnings: 1-2 sentences about proxy/indirect discrimination
- priority_action: 1-2 sentences, the single most important next step
- causal_findings: 2-3 sentences about regression-adjusted and counterfactual results
- data_quality_notes: 1-2 sentences about data quality concerns (missing data, imbalance)
"""


# ─── Anti-Hallucination Layer 3+4: Post-Generation Validation ────


def validate_report_against_data(report: dict[str, Any], audit_results: dict[str, Any]) -> dict[str, Any]:
    """7-layer validation of AI-generated report text against audit data.

    Layer 3: Jargon scan
    Layer 4: Percentage + decimal validation against known values
    Layer 5: Pass/fail claim cross-reference
    Layer 6: Temporal claim detection (blocks "improved", "decreased" etc.)
    """
    issues: list[str] = []
    fact_sheet = _extract_fact_sheet(audit_results)
    known_values = list(fact_sheet["facts"].values())

    all_text = " ".join(
        str(report.get(key, ""))
        for key in ["executive_summary", "intersectional_findings", "proxy_warnings",
                     "priority_action", "causal_findings", "data_quality_notes"]
    )

    # Layer 3: Jargon scan
    banned_terms = [
        "confusion matrix", "TPR", "FPR", "precision", "recall",
        "F1 score", "AUC", "ROC",
    ]
    for term in banned_terms:
        if term.lower() in all_text.lower():
            issues.append(f"Jargon detected: '{term}'")

    metric_context_words = {
        "approval", "rate", "gap", "ratio", "parity", "impact",
        "disparity", "hire", "reject", "favorable", "denied",
        "difference", "equity", "fairness", "score", "power",
    }

    # Layer 4a: Percentage validation
    for match in re.finditer(r"(\d+(?:\.\d+)?)%", all_text):
        number = float(match.group(1)) / 100
        context_start = max(0, match.start() - 80)
        context_end = min(len(all_text), match.end() + 80)
        context = all_text[context_start:context_end].lower()
        if not any(word in context for word in metric_context_words):
            continue
        if known_values and all(abs(round(number, 2) - round(v, 2)) > 0.03 for v in known_values):
            issues.append(
                f"Hallucinated number: report says {number:.0%} but doesn't match any audit value."
            )

    # Layer 4b: Decimal validation (catches "0.15 gap" style claims)
    for match in re.finditer(r"(?<!\d)(0\.\d{2,4})(?!\d)", all_text):
        number = float(match.group(1))
        context_start = max(0, match.start() - 80)
        context_end = min(len(all_text), match.end() + 80)
        context = all_text[context_start:context_end].lower()
        if not any(word in context for word in metric_context_words):
            continue
        if known_values and all(abs(round(number, 4) - round(v, 4)) > 0.03 for v in known_values):
            issues.append(
                f"Hallucinated decimal: report says {number} but doesn't match any audit value."
            )

    # Layer 5: Pass/fail claim cross-reference
    for attr, attr_data in audit_results.get("results", {}).items():
        overall_passed = attr_data.get("overall_passed")
        attr_lower = attr.lower()
        text_lower = all_text.lower()
        attr_pos = text_lower.find(attr_lower)
        if attr_pos < 0:
            continue
        nearby = text_lower[attr_pos:attr_pos + 250]
        if overall_passed is True:
            if any(w in nearby for w in ["fail", "bias detected", "unfair", "discriminat"]):
                issues.append(f"Contradiction: '{attr}' PASSED but report implies failure.")
        elif overall_passed is False:
            if any(w in nearby for w in ["passed all", "no bias", "fair treatment", "no issues"]):
                issues.append(f"Contradiction: '{attr}' FAILED but report implies it passed.")

    # Layer 6: Temporal claim detection — LLM has no history, temporal claims are hallucinations
    temporal_phrases = [
        "improved from", "decreased since", "increased from",
        "compared to last", "previous audit", "year-over-year",
        "historically", "trend shows", "over time",
    ]
    for phrase in temporal_phrases:
        if phrase.lower() in all_text.lower():
            issues.append(f"Temporal hallucination: '{phrase}' — no audit history was provided.")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "checks_run": [
            "jargon_scan", "percentage_verification", "decimal_verification",
            "claim_cross_reference", "temporal_claim_detection",
        ],
        "known_values_count": len(known_values),
    }


# ─── Gemini API Call ─────────────────────────────────────────────


def _call_gemini(
    job_config: dict[str, Any],
    audit_results: dict[str, Any],
    fallback_report: dict[str, Any],
    api_key: str,
    model: str,
    *,
    temperature: float = 0.2,
    extra_instruction: str = "",
) -> dict[str, Any]:
    fact_sheet = _extract_fact_sheet(audit_results)
    prompt = _build_grounded_prompt(job_config, audit_results, fact_sheet)
    if extra_instruction:
        prompt = f"{extra_instruction}\n\n{prompt}"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        response = httpx.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "topP": 0.8,
                    "maxOutputTokens": 2000,
                    "responseMimeType": "application/json",  # Force structured JSON output
                },
            },
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            timeout=30.0,
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
        allowed_keys = [
            "executive_summary", "intersectional_findings", "proxy_warnings",
            "priority_action", "causal_findings", "data_quality_notes",
        ]
        for key in allowed_keys:
            if parsed.get(key):
                merged[key] = parsed[key]
        merged["_gemini_model"] = model
        merged["_gemini_temperature"] = temperature
        return merged
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini API call failed: %s", exc)
        fallback_report["_gemini_error"] = str(exc)
        return fallback_report


def _extract_json_object(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
