from __future__ import annotations

from typing import Any

import pandas as pd
from fairlearn.postprocessing import ThresholdOptimizer
from fairlearn.reductions import DemographicParity, EqualizedOdds, ExponentiatedGradient
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.constants import DEMOGRAPHIC_PARITY_THRESHOLD, DISPARATE_IMPACT_THRESHOLD


def simulate_tradeoffs(df: pd.DataFrame, config: dict[str, Any], attribute: str) -> list[dict[str, Any]]:
    outcome_column = config.get("outcome_column")
    if outcome_column not in df.columns or attribute not in df.columns:
        return []

    feature_columns = [
        column
        for column in df.columns
        if column not in {outcome_column, config.get("prediction_column"), *config.get("protected_attributes", [])}
    ]
    if not feature_columns:
        return []

    work = df[feature_columns + [outcome_column, attribute]].dropna().copy()
    if work.empty or work[attribute].nunique(dropna=True) < 2 or work[outcome_column].nunique(dropna=True) != 2:
        return []

    X = work[feature_columns]
    y = work[outcome_column]
    sensitive = work[attribute].astype(str)

    estimator = _make_pipeline(X)
    try:
        estimator.fit(X, y)
        options = [
            _make_option("Current baseline", estimator.predict(X), y, sensitive, "Current model behavior without fairness adjustment."),
        ]

        try:
            threshold = ThresholdOptimizer(
                estimator=estimator,
                constraints="demographic_parity",
                objective="accuracy_score",
                predict_method="predict_proba",
            )
            threshold.fit(X, y, sensitive_features=sensitive)
            options.append(
                _make_option(
                    "Threshold adjustment",
                    threshold.predict(X, sensitive_features=sensitive),
                    y,
                    sensitive,
                    "Adjusts decision thresholds by group to reduce uneven outcomes.",
                )
            )
        except Exception:  # noqa: BLE001
            pass

        for label, constraint in [
            ("Fairness-constrained retraining", DemographicParity()),
            ("Equal opportunity focused retraining", EqualizedOdds()),
        ]:
            try:
                mitigated = ExponentiatedGradient(estimator=_make_pipeline(X), constraints=constraint)
                mitigated.fit(X, y, sensitive_features=sensitive)
                options.append(
                    _make_option(
                        label,
                        mitigated.predict(X),
                        y,
                        sensitive,
                        "Retrains a surrogate model with fairness constraints to reduce the gap.",
                    )
                )
            except Exception:  # noqa: BLE001
                continue

        deduped = []
        seen = set()
        for option in options:
            if option["label"] in seen:
                continue
            seen.add(option["label"])
            deduped.append(option)
        return deduped
    except Exception:  # noqa: BLE001
        return []


def _make_pipeline(X: pd.DataFrame) -> Pipeline:
    numeric_columns = [column for column in X.columns if pd.api.types.is_numeric_dtype(X[column])]
    categorical_columns = [column for column in X.columns if column not in numeric_columns]
    transformer = ColumnTransformer(
        transformers=[
            ("numeric", StandardScaler(), numeric_columns),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical_columns),
        ],
        remainder="drop",
    )
    return Pipeline([("transformer", transformer), ("model", LogisticRegression(max_iter=1000))])


def _make_option(label: str, predictions: Any, y: pd.Series, sensitive: pd.Series, summary: str) -> dict[str, Any]:
    predicted = pd.Series(predictions, index=y.index)
    accuracy = float((predicted == y).mean())
    group_rates = predicted.groupby(sensitive).mean()
    if len(group_rates) >= 2:
        dp_gap = float(group_rates.max() - group_rates.min())
        di = float(group_rates.min() / group_rates.max()) if group_rates.max() > 0 else 1.0
    else:
        dp_gap = 0.0
        di = 1.0
    return {
        "label": label,
        "projected_accuracy": round(accuracy, 4),
        "projected_disparate_impact": round(di, 4),
        "projected_demographic_parity_gap": round(dp_gap, 4),
        "summary": (
            f"{summary} Approval-rate gap {'passes' if dp_gap <= DEMOGRAPHIC_PARITY_THRESHOLD else 'misses'} "
            f"the guardrail and the fairness ratio {'passes' if di >= DISPARATE_IMPACT_THRESHOLD else 'misses'} the 80% rule."
        ),
    }
