from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def load_model(model_path: str | None) -> Any | None:
    if not model_path:
        return None
    path = Path(model_path)
    if not path.exists():
        return None
    with path.open("rb") as handle:
        return pickle.load(handle)


def generate_root_cause_analysis(
    df: pd.DataFrame,
    config: dict[str, Any],
    audit_results: dict[str, Any],
    model_path: str | None,
) -> dict[str, list[dict[str, Any]]]:
    model = load_model(model_path)
    prediction_column = config.get("prediction_column")
    outcome_column = config.get("outcome_column")
    protected_attributes = config.get("protected_attributes", [])
    favorable_outcome = config.get("favorable_outcome")

    feature_columns = [
        column
        for column in df.columns
        if column not in {prediction_column, outcome_column, *protected_attributes}
    ]
    if not feature_columns:
        return {}

    explanations: dict[str, list[dict[str, Any]]] = {}
    for attribute in protected_attributes:
        result = audit_results.get("results", {}).get(attribute)
        if not result or result.get("overall_passed", True):
            continue
        group_stats = result.get("group_stats", {})
        if len(group_stats) < 2:
            continue
        best_group = max(group_stats, key=lambda group: group_stats[group]["rate"])
        worst_group = min(group_stats, key=lambda group: group_stats[group]["rate"])

        subset = df[df[attribute].isin([best_group, worst_group])].copy()
        feature_scores = _compute_feature_scores(subset, feature_columns, attribute, best_group, worst_group, model)
        explanations[attribute] = [
            {
                "feature": name,
                "contribution": round(score, 4),
                "explanation": (
                    f"{name} differs most between {best_group} and {worst_group} and is a likely driver of the observed gap."
                ),
            }
            for name, score in feature_scores[:5]
        ]
    return explanations


def _compute_feature_scores(
    df: pd.DataFrame,
    features: list[str],
    attribute: str,
    best_group: str,
    worst_group: str,
    model: Any | None,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    numeric_features = [feature for feature in features if pd.api.types.is_numeric_dtype(df[feature])]
    categorical_features = [feature for feature in features if feature not in numeric_features]

    if numeric_features:
        group_means = df.groupby(attribute)[numeric_features].mean(numeric_only=True)
        for feature in numeric_features:
            scores[feature] = abs(float(group_means.loc[best_group, feature] - group_means.loc[worst_group, feature]))

    for feature in categorical_features:
        table = pd.crosstab(df[attribute], df[feature], normalize="index")
        if best_group not in table.index or worst_group not in table.index:
            continue
        aligned = table.loc[[best_group, worst_group]].fillna(0.0)
        scores[feature] = float((aligned.loc[best_group] - aligned.loc[worst_group]).abs().sum() / 2)

    if model is not None and hasattr(model, "feature_importances_"):
        importances = list(getattr(model, "feature_importances_"))
        model_scores = {
            feature: abs(scores[feature]) * float(importances[index])
            for index, feature in enumerate(features[: len(importances)])
        }
        scores.update(model_scores)

    elif model is not None and hasattr(model, "coef_"):
        coefficients = np.ravel(getattr(model, "coef_"))
        coef_scores = {
            feature: abs(scores[feature]) * abs(float(coefficients[index]))
            for index, feature in enumerate(features[: len(coefficients)])
        }
        scores.update(coef_scores)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    total = sum(score for _, score in ranked) or 1.0
    return [(name, score / total) for name, score in ranked]
