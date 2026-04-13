from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

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
        attribute_breakdowns.append({"attribute": attribute, "paragraph": paragraph})

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

    proxy_features = audit_results.get("proxy_features", [])
    proxy_warnings = (
        "Potential proxy features were found: "
        + ", ".join(f"{item['feature']} -> {item['correlated_with']}" for item in proxy_features[:5])
        if proxy_features
        else "No strong proxy feature warning crossed the configured threshold."
    )

    cards = build_mitigation_cards(audit_results)
    priority_action = cards[0]["action"] if cards else "Keep monitoring and rerun the audit after changes."

    return {
        "executive_summary": executive_summary,
        "attribute_breakdowns": attribute_breakdowns,
        "intersectional_findings": intersectional_findings,
        "proxy_warnings": proxy_warnings,
        "priority_action": priority_action,
        "mitigation_cards": cards,
    }


def build_pdf_bytes(report: dict[str, Any], *, title: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50

    for line in [title, "", "Executive Summary", report["executive_summary"], "", "Priority Action", report["priority_action"]]:
        if y < 80:
            pdf.showPage()
            y = height - 50
        pdf.drawString(40, y, _sanitize(line))
        y -= 18

    pdf.showPage()
    y = height - 50
    pdf.drawString(40, y, "Attribute Breakdown")
    y -= 24
    for item in report["attribute_breakdowns"]:
        for line in [f"{item['attribute']}:", item["paragraph"], ""]:
            if y < 80:
                pdf.showPage()
                y = height - 50
            pdf.drawString(40, y, _sanitize(line))
            y -= 18

    pdf.save()
    return buffer.getvalue()


def _sanitize(text: str) -> str:
    return text.encode("ascii", "ignore").decode("ascii")[:120]
