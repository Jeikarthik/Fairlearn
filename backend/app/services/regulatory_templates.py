"""Regulatory compliance report templates.

Generates structured report data in formats aligned with:
  - NYC Local Law 144 (2023) — automated employment decision tools bias audit
  - EU AI Act Article 13 (2024) — high-risk AI transparency requirements
  - ECOA / Regulation B — adverse action notice generation

These are structured data dicts, not final PDF/HTML — the frontend or a
report renderer converts them to the required output format.

DISCLAIMER: These templates assist with regulatory compliance but do not
constitute legal advice.  Have qualified counsel review any regulatory
submission.
"""
from __future__ import annotations

import datetime
from typing import Any


# ── NYC Local Law 144 ─────────────────────────────────────────────


def generate_nyc_ll144_report(
    audit_results: dict[str, Any],
    job_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Generate a bias audit summary aligned with NYC Local Law 144 requirements.

    LL144 requires automated employment decision tools (AEDTs) used in NYC to
    undergo an independent bias audit covering:
      - Impact ratio for each category and intersectional category
      - Selection rates by race/ethnicity, sex, and intersectional categories
      - Whether impact ratios are within the 80% rule
      - Date of most recent bias audit
      - Summary statistics available to candidates and employees
    """
    now = datetime.datetime.utcnow().isoformat() + "Z"
    results = audit_results.get("results", {})
    intersectional = audit_results.get("intersectional", {})
    threshold_config = audit_results.get("threshold_config", {})

    attribute_sections = []
    for attr, attr_data in results.items():
        group_stats = attr_data.get("group_stats", {})
        metrics = attr_data.get("metrics", {})
        dir_metric = metrics.get("disparate_impact_ratio", {})

        groups_table = []
        for group_name, stats in group_stats.items():
            rate = stats.get("rate", 0.0)
            groups_table.append({
                "category": group_name,
                "selection_rate": round(rate, 4),
                "selection_rate_pct": f"{rate:.1%}",
                "count_selected": stats.get("favorable", 0),
                "count_total": stats.get("total", 0),
            })

        # Compute impact ratios vs highest-rate group
        if groups_table:
            ref_rate = max(g["selection_rate"] for g in groups_table)
            for g in groups_table:
                ratio = (g["selection_rate"] / ref_rate) if ref_rate > 0 else None
                g["impact_ratio"] = round(ratio, 4) if ratio is not None else None
                g["passes_80pct_rule"] = (ratio >= 0.80) if ratio is not None else None

        attribute_sections.append({
            "protected_category": attr,
            "groups": groups_table,
            "overall_disparate_impact_ratio": dir_metric.get("value"),
            "passes_disparate_impact_threshold": dir_metric.get("passed"),
            "threshold_used": threshold_config.get("disparate_impact_threshold", 0.80),
        })

    # Intersectional categories (LL144 requires race × sex at minimum)
    intersectional_sections = []
    for combo_key, combo_data in intersectional.items():
        combo_groups = []
        for group_name, stats in combo_data.items():
            combo_groups.append({
                "category": group_name,
                "selection_rate": stats.get("rate", 0.0),
                "count_total": stats.get("total", 0),
                "disparity_vs_best": stats.get("disparity_vs_best", 1.0),
                "reliable": stats.get("reliable", False),
            })
        intersectional_sections.append({
            "combination": combo_key,
            "groups": combo_groups,
        })

    return {
        "_report_type": "nyc_local_law_144",
        "_generated_at": now,
        "_schema_version": 1,
        "disclaimer": (
            "This bias audit report is generated to assist compliance with NYC Local Law 144 (Int. 1894-A). "
            "It does not constitute legal advice. Have qualified counsel review before submission."
        ),
        "audit_metadata": {
            "audit_date": now,
            "tool_name": job_metadata.get("tool_name", "FairLens"),
            "tool_version": job_metadata.get("tool_version", "unknown"),
            "dataset_description": job_metadata.get("dataset_description", ""),
            "rows_audited": audit_results.get("sampling", {}).get("sample_rows") or audit_results.get("sampling", {}).get("original_rows"),
            "algorithm_version": audit_results.get("_algorithm_version", "unknown"),
            "threshold_fingerprint": threshold_config.get("fingerprint", "unknown"),
            "domain": threshold_config.get("domain", "employment"),
        },
        "bias_audit_results": attribute_sections,
        "intersectional_categories": intersectional_sections,
        "statistical_notes": {
            "confidence_interval_method": "Newcombe Method 10 (gold standard for proportions)",
            "multiple_testing_correction": "Benjamini-Hochberg FDR",
            "minimum_group_size_for_reliable_results": 30,
            "sampling_applied": audit_results.get("sampling", {}).get("sampled", False),
            "sampling_warning": audit_results.get("sampling", {}).get("warning"),
        },
        "required_posting": {
            "summary": (
                "An independent bias audit of our automated employment decision tool was completed. "
                f"The audit covered {len(attribute_sections)} protected characteristic(s). "
                "Results are available upon request."
            ),
            "contact_info_placeholder": "[INSERT: Name and contact for bias audit inquiries]",
            "audit_date_for_posting": now[:10],
        },
    }


# ── EU AI Act Article 13 ──────────────────────────────────────────


def generate_eu_ai_act_report(
    audit_results: dict[str, Any],
    job_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Generate a transparency report aligned with EU AI Act Article 13.

    Article 13 requires providers of high-risk AI systems to ensure that
    the system is transparent enough to allow deployers to interpret its output.
    This covers:
      - Intended purpose and limitations
      - Performance metrics across demographic groups
      - Known biases and risk mitigation measures
      - Human oversight mechanisms
      - Data governance summary
    """
    now = datetime.datetime.utcnow().isoformat() + "Z"
    results = audit_results.get("results", {})
    threshold_config = audit_results.get("threshold_config", {})
    completeness = audit_results.get("_completeness", {})

    performance_by_group = []
    all_passed = True
    for attr, attr_data in results.items():
        group_stats = attr_data.get("group_stats", {})
        metrics = attr_data.get("metrics", {})
        overall_passed = attr_data.get("overall_passed", True)
        if not overall_passed:
            all_passed = False

        failed_metrics = [k for k, v in metrics.items() if v.get("passed") is False]

        performance_by_group.append({
            "protected_characteristic": attr,
            "groups_analysed": list(group_stats.keys()),
            "n_groups": len(group_stats),
            "fairness_assessment": "PASS" if overall_passed else "FAIL",
            "failed_metrics": failed_metrics,
            "demographic_parity_difference": metrics.get("demographic_parity_difference", {}).get("value"),
            "disparate_impact_ratio": metrics.get("disparate_impact_ratio", {}).get("value"),
            "statistical_significance": attr_data.get("significance", {}).get("significant"),
        })

    proxy_features = audit_results.get("proxy_features", [])
    causal = audit_results.get("covariate_adjusted", audit_results.get("causal_analysis", {}))

    return {
        "_report_type": "eu_ai_act_article_13",
        "_generated_at": now,
        "_schema_version": 1,
        "disclaimer": (
            "This transparency report assists compliance with EU AI Act Article 13 "
            "transparency obligations for high-risk AI systems. "
            "It does not constitute legal advice."
        ),
        "system_identification": {
            "system_name": job_metadata.get("tool_name", "FairLens-Audited System"),
            "version": job_metadata.get("tool_version", "unknown"),
            "intended_purpose": job_metadata.get("intended_purpose", "[REQUIRED: Describe intended purpose]"),
            "high_risk_category": job_metadata.get("high_risk_category", "[REQUIRED: Specify EU AI Act Annex III category]"),
            "deployer_name": job_metadata.get("deployer_name", "[REQUIRED: Deployer name and contact]"),
        },
        "performance_and_fairness": {
            "overall_fairness_assessment": "PASS" if all_passed else "FAIL",
            "analysis_completeness_score": completeness.get("score", 0.0),
            "modules_completed": f"{completeness.get('succeeded', 0)}/{completeness.get('total_modules', 0)}",
            "by_protected_characteristic": performance_by_group,
            "proxy_risk_features": [
                {
                    "feature": p["feature"],
                    "correlated_with": p["correlated_with"],
                    "correlation_strength": p["correlation"],
                    "method": p["method"],
                }
                for p in proxy_features[:10]
            ],
            "threshold_configuration": {
                "domain": threshold_config.get("domain", "general"),
                "fingerprint": threshold_config.get("fingerprint"),
                "demographic_parity_threshold": threshold_config.get("demographic_parity_threshold"),
                "disparate_impact_threshold": threshold_config.get("disparate_impact_threshold"),
            },
        },
        "known_limitations": {
            "covariate_adjusted_analysis": (
                "Covariate-adjusted analysis uses logistic regression residuals, not causal inference. "
                "Results indicate association patterns, not causal mechanisms."
            ),
            "counterfactual_matching": (
                "Counterfactual fairness uses nearest-neighbor matching (Gower distance). "
                "Full causal counterfactual inference requires a domain-specific causal DAG."
            ),
            "sampling": audit_results.get("sampling", {}).get("warning"),
            "aggregate_mode_limitations": (
                "Aggregate audits provide DPD and DIR only. "
                "For full analysis including equal opportunity and individual fairness, provide row-level data."
            ) if audit_results.get("mode") == "aggregate" else None,
        },
        "human_oversight": {
            "override_mechanism": "[REQUIRED: Describe human override capability]",
            "monitoring_frequency": "[REQUIRED: State reaudit cadence]",
            "escalation_process": "[REQUIRED: Describe how flagged decisions are reviewed]",
        },
        "data_governance": {
            "training_data_description": job_metadata.get("training_data_description", "[REQUIRED]"),
            "audit_data_rows": audit_results.get("sampling", {}).get("original_rows"),
            "normalization_changes": len(audit_results.get("normalization_changelog", [])),
            "algorithm_version_stamp": audit_results.get("_algorithm_version"),
        },
    }


# ── ECOA Adverse Action ───────────────────────────────────────────


def generate_ecoa_adverse_action(
    individual_result: dict[str, Any],
    job_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Generate an ECOA / Regulation B-aligned adverse action notice template.

    ECOA (Equal Credit Opportunity Act) Regulation B requires creditors to
    provide adverse action notices listing the specific reasons for denial.
    This template generates the structured data; the creditor must review and
    send the actual notice.

    individual_result: the audit result dict for one applicant (group_stats entry
    or any per-record dict with feature contribution data).
    """
    now = datetime.datetime.utcnow().isoformat() + "Z"

    principal_reasons = individual_result.get("top_features", [])
    if not principal_reasons:
        principal_reasons = [
            {"feature": "[REQUIRED: Specify denial reason 1]", "contribution": None},
            {"feature": "[REQUIRED: Specify denial reason 2]", "contribution": None},
        ]

    return {
        "_report_type": "ecoa_adverse_action_notice",
        "_generated_at": now,
        "_schema_version": 1,
        "disclaimer": (
            "This template assists with ECOA / Regulation B adverse action notice requirements. "
            "Review by a qualified compliance officer is required before sending to applicants. "
            "Do not send this template directly — it must be reviewed and adapted."
        ),
        "creditor": {
            "name": job_metadata.get("creditor_name", "[REQUIRED: Creditor name]"),
            "address": job_metadata.get("creditor_address", "[REQUIRED: Creditor address]"),
            "phone": job_metadata.get("creditor_phone", "[REQUIRED: Creditor phone]"),
        },
        "notice_date": now[:10],
        "action_taken": "Credit application denied",
        "principal_reasons_for_action": [
            {
                "rank": i + 1,
                "reason": r.get("feature", "[Reason not available]"),
                "regulatory_code": "[MAP TO: Regulation B Sample Form C-1 reason codes]",
            }
            for i, r in enumerate(principal_reasons[:4])  # Reg B requires ≤4 reasons
        ],
        "fair_lending_statement": (
            "The Federal Equal Credit Opportunity Act prohibits creditors from discriminating "
            "against credit applicants on the basis of race, color, religion, national origin, "
            "sex, marital status, age (provided the applicant has the capacity to enter into a "
            "binding contract); because all or part of the applicant's income derives from any "
            "public assistance program; or because the applicant has in good faith exercised any "
            "right under the Consumer Credit Protection Act."
        ),
        "credit_score_disclosure": {
            "note": "[REQUIRED IF SCORE USED: Include credit score disclosure per FCRA 615(a)]",
            "score": None,
            "range": None,
            "date_obtained": None,
            "scoring_model": None,
            "key_factors": [],
        },
        "complaint_contact": {
            "cfpb": "Consumer Financial Protection Bureau, 1700 G Street NW, Washington DC 20552",
            "cfpb_phone": "1-855-411-2372",
            "cfpb_website": "www.consumerfinance.gov",
        },
    }


# ── Convenience dispatcher ────────────────────────────────────────


def generate_regulatory_report(
    report_type: str,
    audit_results: dict[str, Any],
    job_metadata: dict[str, Any],
    individual_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a regulatory report of the specified type.

    report_type: one of "nyc_ll144", "eu_ai_act", "ecoa_adverse_action"
    """
    if report_type == "nyc_ll144":
        return generate_nyc_ll144_report(audit_results, job_metadata)
    if report_type == "eu_ai_act":
        return generate_eu_ai_act_report(audit_results, job_metadata)
    if report_type == "ecoa_adverse_action":
        return generate_ecoa_adverse_action(individual_result or {}, job_metadata)
    return {
        "error": f"Unknown report_type '{report_type}'. "
                 "Use one of: nyc_ll144, eu_ai_act, ecoa_adverse_action."
    }
