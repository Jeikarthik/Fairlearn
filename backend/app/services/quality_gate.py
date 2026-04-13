from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from app.constants import MIN_GROUP_SIZE, MIN_TOTAL_ROWS
from app.schemas.quality import QualityCheckItem
from app.services.normalization import normalize_dataframe


def run_quality_gate(df: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    checks: list[QualityCheckItem] = []
    normalized = normalize_dataframe(df)

    outcome_column = str(config["outcome_column"])
    prediction_column = config.get("prediction_column")
    protected_attributes = list(config.get("protected_attributes", []))
    favorable_outcome = config.get("favorable_outcome")

    total_rows = int(len(normalized.index))
    if total_rows < MIN_TOTAL_ROWS:
        checks.append(
            QualityCheckItem(
                check="minimum_total_rows",
                status="fail",
                value=total_rows,
                message=f"Only {total_rows} rows available. Minimum {MIN_TOTAL_ROWS} required for a reliable audit.",
            )
        )
    else:
        checks.append(
            QualityCheckItem(
                check="minimum_total_rows",
                status="pass",
                value=total_rows,
                message=f"Dataset contains {total_rows} rows.",
            )
        )

    if outcome_column in protected_attributes:
        checks.append(
            QualityCheckItem(
                check="invalid_configuration",
                status="fail",
                attribute=outcome_column,
                message="Outcome column cannot also be a protected attribute.",
            )
        )

    for column in normalized.columns:
        missing = int(normalized[column].isna().sum())
        if missing:
            checks.append(
                QualityCheckItem(
                    check="missing_values",
                    status="info",
                    column=str(column),
                    value=missing,
                    message=f"{missing} missing values found in '{column}'.",
                )
            )
        unique_count = int(normalized[column].nunique(dropna=True))
        if unique_count <= 1:
            checks.append(
                QualityCheckItem(
                    check="single_value_column",
                    status="warning",
                    column=str(column),
                    value=unique_count,
                    message=f"Column '{column}' has only one distinct value and cannot support comparisons.",
                )
            )

    outcome_series = normalized[outcome_column]
    positive_rate = _compute_positive_rate(outcome_series, favorable_outcome)
    if positive_rate is None:
        checks.append(
            QualityCheckItem(
                check="continuous_outcome",
                status="warning",
                column=outcome_column,
                message=(
                    f"Outcome column '{outcome_column}' has more than two distinct values. "
                    "Add a cutoff step before running fairness metrics."
                ),
            )
        )
    else:
        status = "warning" if positive_rate < 0.1 or positive_rate > 0.9 else "pass"
        message = (
            f"Positive outcome rate is {positive_rate:.1%}. "
            + ("This is highly imbalanced." if status == "warning" else "Outcome balance looks reasonable.")
        )
        checks.append(
            QualityCheckItem(
                check="outcome_balance",
                status=status,  # type: ignore[arg-type]
                column=outcome_column,
                value=round(positive_rate, 4),
                message=message,
            )
        )

    if prediction_column:
        if prediction_column not in normalized.columns:
            checks.append(
                QualityCheckItem(
                    check="prediction_column_missing",
                    status="fail",
                    column=str(prediction_column),
                    message=f"Prediction column '{prediction_column}' was not found in the uploaded file.",
                )
            )
        elif normalized[outcome_column].equals(normalized[prediction_column]):
            checks.append(
                QualityCheckItem(
                    check="ground_truth_equals_prediction",
                    status="warning",
                    message=(
                        "Outcome and prediction columns match exactly. "
                        "If this is a pre-training dataset, use dataset readiness mode instead."
                    ),
                )
            )

    for attribute in protected_attributes:
        if attribute not in normalized.columns:
            checks.append(
                QualityCheckItem(
                    check="protected_attribute_missing",
                    status="fail",
                    attribute=attribute,
                    message=f"Protected attribute '{attribute}' was not found in the uploaded file.",
                )
            )
            continue

        series = normalized[attribute]
        if pd.api.types.is_numeric_dtype(series) and series.nunique(dropna=True) > 10:
            checks.append(
                QualityCheckItem(
                    check="continuous_protected_attribute",
                    status="warning",
                    attribute=attribute,
                    message=f"Protected attribute '{attribute}' looks continuous and should be bucketed before auditing.",
                )
            )

        group_counts = Counter(series.dropna().astype(str))
        for group, count in group_counts.items():
            if count < MIN_GROUP_SIZE or count / max(total_rows, 1) < 0.1:
                checks.append(
                    QualityCheckItem(
                        check="group_size",
                        status="warning",
                        attribute=attribute,
                        group=group,
                        value=count,
                        message=f"Group '{group}' in '{attribute}' only has {count} rows. Results may be unreliable.",
                    )
                )
            else:
                checks.append(
                    QualityCheckItem(
                        check="group_size",
                        status="pass",
                        attribute=attribute,
                        group=group,
                        value=count,
                        message=f"Group '{group}' in '{attribute}' has {count} rows.",
                    )
                )

        reliability_check = _ground_truth_reliability(
            normalized,
            attribute=attribute,
            outcome_column=outcome_column,
            favorable_outcome=favorable_outcome,
        )
        if reliability_check is not None:
            checks.append(reliability_check)

    overall_status = _resolve_overall_status(checks)
    return {
        "overall_status": overall_status,
        "checks": [item.model_dump() for item in checks],
    }


def _compute_positive_rate(series: pd.Series, favorable_outcome: Any) -> float | None:
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    unique_values = cleaned.nunique(dropna=True)
    if unique_values > 2:
        return None
    return float((cleaned == favorable_outcome).mean())


def _ground_truth_reliability(
    df: pd.DataFrame,
    *,
    attribute: str,
    outcome_column: str,
    favorable_outcome: Any,
) -> QualityCheckItem | None:
    subset = df[[attribute, outcome_column]].dropna()
    if subset.empty or subset[attribute].nunique(dropna=True) < 2:
        return None

    rate_by_group = (
        subset.groupby(attribute)[outcome_column]
        .apply(lambda values: float((values == favorable_outcome).mean()))
        .sort_values(ascending=False)
    )
    if len(rate_by_group) < 2:
        return None

    gap = float(rate_by_group.iloc[0] - rate_by_group.iloc[-1])
    if gap <= 0.20:
        return None

    return QualityCheckItem(
        check="ground_truth_reliability",
        status="warning",
        attribute=attribute,
        value=round(gap, 4),
        details={"group_rates": {str(key): round(value, 4) for key, value in rate_by_group.items()}},
        message=(
            f"Historical outcomes for '{attribute}' already differ by {gap:.1%}. "
            "The benchmark may reflect pre-existing bias."
        ),
    )


def _resolve_overall_status(checks: list[QualityCheckItem]) -> str:
    if any(item.status == "fail" for item in checks):
        return "fail"
    if any(item.status == "warning" for item in checks):
        return "pass_with_warnings"
    return "pass"
