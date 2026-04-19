"""Report generation — template-based report + professional PDF.

Includes all 12 analysis modules in the report output.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.file_parser import read_tabular_file
from app.services.mitigation import build_mitigation_cards


def build_report(job: dict[str, Any], audit_results: dict[str, Any]) -> dict[str, Any]:
    org_name = job.get("org_name") or "This organization"
    model_name = job.get("model_name") or "the audited system"
    domain = job.get("domain") or "the selected domain"
    failing_attributes = [name for name, item in audit_results.get("results", {}).items() if not item["overall_passed"]]
    passing_attributes = [name for name, item in audit_results.get("results", {}).items() if item["overall_passed"]]

    executive_summary = (
        f"{org_name}'s {model_name} was audited for fairness in {domain}. "
        + (
            f"FairLens found uneven treatment across {', '.join(failing_attributes)}."
            if failing_attributes
            else "FairLens did not find major fairness failures in the audited attributes."
        )
    )

    # Completeness note
    comp = audit_results.get("_completeness", {})
    if comp.get("score") and comp["score"] < 1.0:
        executive_summary += (
            f" Note: {comp.get('failed', 0)} of {comp.get('total_modules', 0)} "
            "advanced analysis modules could not run on this dataset."
        )

    attribute_breakdowns = []
    for attribute, payload in audit_results.get("results", {}).items():
        failed = [name for name, metric in payload["metrics"].items() if metric.get("passed") is False]
        if failed:
            paragraph = (
                f"For {attribute}, the main issues were {', '.join(failed)}. "
                "The affected groups should be reviewed before the next model or policy release."
            )
        else:
            paragraph = f"For {attribute}, the checked fairness measures stayed within the current thresholds."

        # Add power analysis note if available
        adv = audit_results.get("advanced_statistics", {})
        attr_adv = adv.get(attribute, {}) if isinstance(adv, dict) else {}
        power = attr_adv.get("power_analysis", {})
        if power.get("adequate_power") is False:
            paragraph += (
                f" ⚠️ Statistical power is low ({power.get('power', 0):.0%}) — "
                f"the sample may be too small to detect gaps below {power.get('min_detectable_effect', 0):.1%}."
            )

        effect = attr_adv.get("effect_size", {})
        if effect.get("magnitude") in ("medium", "large"):
            paragraph += f" The effect size is {effect['magnitude']} (Cohen's h = {effect.get('cohens_h', 0):.3f})."

        attribute_breakdowns.append({"attribute": attribute, "paragraph": paragraph})

    # Intersectional findings
    intersectional = audit_results.get("intersectional", {})
    if intersectional:
        highlighted = []
        for key, values in intersectional.items():
            for group_name, group_payload in values.items():
                if not group_payload.get("reliable", True):
                    continue
                if group_payload.get("disparity_vs_best", 1.0) < 0.8:
                    highlighted.append(f"{group_name} in {key}")
        intersectional_findings = (
            "FairLens found compound group patterns affecting " + ", ".join(highlighted[:3]) + "."
            if highlighted
            else "No major intersectional fairness warning crossed the current threshold."
        )
    else:
        intersectional_findings = "No intersectional analysis was available for this audit."

    # Proxy warnings
    proxy_features = audit_results.get("proxy_features", [])
    proxy_warnings = (
        "Potential proxy features were found: "
        + ", ".join(f"{item['feature']} -> {item['correlated_with']}" for item in proxy_features[:5])
        if proxy_features
        else "No strong proxy feature warning crossed the configured threshold."
    )

    # Causal findings
    causal = audit_results.get("causal_analysis", {})
    causal_findings = ""
    if isinstance(causal, dict):
        adj = causal.get("adjusted_metrics", {})
        if isinstance(adj, dict):
            for attr, data in adj.items():
                if isinstance(data, dict) and "interpretation" in data:
                    causal_findings += data["interpretation"] + " "
        sp = causal.get("simpsons_paradox", {})
        if isinstance(sp, dict):
            for attr, data in sp.items():
                if isinstance(data, dict) and data.get("paradoxes_found"):
                    causal_findings += f"Simpson's paradox detected for {attr}. "
    if not causal_findings:
        causal_findings = "No regression-adjusted or Simpson's paradox analysis was available."

    # Counterfactual findings
    cf = audit_results.get("counterfactual_fairness", {})
    counterfactual_findings = ""
    if isinstance(cf, dict):
        for attr, data in cf.items():
            if isinstance(data, dict) and "interpretation" in data:
                counterfactual_findings += data["interpretation"] + " "
    if not counterfactual_findings:
        counterfactual_findings = "Counterfactual analysis was not available for this audit."

    # Data quality notes
    diag = audit_results.get("data_diagnostics", {})
    data_quality = ""
    if isinstance(diag, dict):
        imb = diag.get("class_imbalance", {})
        if isinstance(imb, dict) and imb.get("imbalance_warning"):
            data_quality += imb["imbalance_warning"] + " "
        miss = diag.get("missing_data", {})
        if isinstance(miss, dict) and miss.get("overall_missing_rate", 0) > 0.05:
            data_quality += f"Overall missing data rate: {miss['overall_missing_rate']:.1%}. "
    if not data_quality:
        data_quality = "No significant data quality concerns detected."

    df = None
    if job.get("mode") != "aggregate" and job.get("job_file_path"):
        try:
            df = read_tabular_file(Path(job["job_file_path"]))
        except Exception:  # noqa: BLE001
            df = None
    cards = build_mitigation_cards(audit_results, df=df, config=job)
    priority_action = cards[0]["action"] if cards else "Keep monitoring and rerun the audit after changes."

    return {
        "executive_summary": executive_summary,
        "attribute_breakdowns": attribute_breakdowns,
        "intersectional_findings": intersectional_findings,
        "proxy_warnings": proxy_warnings,
        "causal_findings": causal_findings,
        "counterfactual_findings": counterfactual_findings,
        "data_quality_notes": data_quality,
        "priority_action": priority_action,
        "mitigation_cards": cards,
    }


def build_pdf_bytes(report: dict[str, Any], *, title: str) -> bytes:
    """Build a professional PDF report using Platypus (table-aware layout)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=colors.HexColor("#1a1a2e"),
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#16213e"),
        spaceBefore=18,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyText",
        parent=styles["BodyText"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#333333"),
    )
    badge_pass = ParagraphStyle("BadgePass", parent=body_style, textColor=colors.HexColor("#27ae60"))
    badge_fail = ParagraphStyle("BadgeFail", parent=body_style, textColor=colors.HexColor("#e74c3c"))

    elements: list = []

    # Title
    elements.append(Paragraph(title, title_style))
    elements.append(Paragraph("FairLens AI Fairness Audit Report", styles["Heading3"]))
    elements.append(Spacer(1, 12))

    # Executive Summary
    elements.append(Paragraph("Executive Summary", heading_style))
    elements.append(Paragraph(_safe_text(report.get("executive_summary", "")), body_style))
    elements.append(Spacer(1, 8))

    # Priority Action
    elements.append(Paragraph("Priority Action", heading_style))
    elements.append(Paragraph(_safe_text(report.get("priority_action", "")), badge_fail))
    elements.append(Spacer(1, 8))

    # Attribute Breakdowns
    elements.append(Paragraph("Attribute Analysis", heading_style))
    for item in report.get("attribute_breakdowns", []):
        elements.append(Paragraph(f"<b>{_safe_text(item['attribute'])}</b>", body_style))
        elements.append(Paragraph(_safe_text(item["paragraph"]), body_style))
        elements.append(Spacer(1, 4))

    # Intersectional Findings
    elements.append(Paragraph("Intersectional Analysis", heading_style))
    elements.append(Paragraph(_safe_text(report.get("intersectional_findings", "")), body_style))

    # Proxy Warnings
    elements.append(Paragraph("Proxy Feature Warnings", heading_style))
    elements.append(Paragraph(_safe_text(report.get("proxy_warnings", "")), body_style))

    # Causal Findings
    if report.get("causal_findings"):
        elements.append(Paragraph("Causal Analysis", heading_style))
        elements.append(Paragraph(_safe_text(report["causal_findings"]), body_style))

    # Counterfactual
    if report.get("counterfactual_findings"):
        elements.append(Paragraph("Counterfactual Fairness", heading_style))
        elements.append(Paragraph(_safe_text(report["counterfactual_findings"]), body_style))

    # Data Quality
    if report.get("data_quality_notes"):
        elements.append(Paragraph("Data Quality Notes", heading_style))
        elements.append(Paragraph(_safe_text(report["data_quality_notes"]), body_style))

    # Mitigation Table
    cards = report.get("mitigation_cards", [])
    if cards:
        elements.append(Paragraph("Mitigation Recommendations", heading_style))
        table_data = [["Priority", "Attribute", "Action"]]
        for i, card in enumerate(cards[:10], 1):
            table_data.append([
                str(i),
                _safe_text(card.get("attribute", "")),
                _safe_text(card.get("action", ""))[:100],
            ])
        t = Table(table_data, colWidths=[40, 100, 320])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8f9fa"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elements.append(t)

    # Footer
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        "Generated by FairLens v1.0 | AI Fairness Audit Platform",
        ParagraphStyle("Footer", parent=body_style, fontSize=8, textColor=colors.grey),
    ))

    doc.build(elements)
    return buffer.getvalue()


def _safe_text(text: str) -> str:
    """Escape XML-unsafe characters for ReportLab Paragraph."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
