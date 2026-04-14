from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shap
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler


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

    shap_explanations = _generate_shap_explanations(df, feature_columns, protected_attributes, audit_results, model)
    if shap_explanations:
        return shap_explanations

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
                "method": "heuristic",
                "explanation": (
                    f"{name} differs most between {best_group} and {worst_group} and is a likely driver of the observed gap."
                ),
            }
            for name, score in feature_scores[:5]
        ]
    return explanations


def _generate_shap_explanations(
    df: pd.DataFrame,
    feature_columns: list[str],
    protected_attributes: list[str],
    audit_results: dict[str, Any],
    model: Any | None,
) -> dict[str, list[dict[str, Any]]]:
    if model is None:
        return {}
    try:
        prepared_X, prepared_feature_names = _prepare_features_for_shap(df[feature_columns].copy(), model)
        if prepared_X is None or prepared_X.empty:
            return {}

        explainer = _build_explainer(model, prepared_X)
        shap_values = explainer(prepared_X)
        values = shap_values.values
        if values.ndim == 3:
            values = values[:, :, -1]
        shap_frame = pd.DataFrame(values, columns=prepared_feature_names, index=prepared_X.index)

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
            best_idx = df[df[attribute] == best_group].index.intersection(shap_frame.index)
            worst_idx = df[df[attribute] == worst_group].index.intersection(shap_frame.index)
            if len(best_idx) == 0 or len(worst_idx) == 0:
                continue
            best_scores = shap_frame.loc[best_idx].abs().mean()
            worst_scores = shap_frame.loc[worst_idx].abs().mean()
            delta = (best_scores - worst_scores).abs().sort_values(ascending=False)
            explanations[attribute] = [
                {
                    "feature": feature,
                    "contribution": round(float(score / (delta.sum() or 1.0)), 4),
                    "method": "shap",
                    "explanation": f"{feature} shows the largest SHAP contribution shift between {best_group} and {worst_group}.",
                }
                for feature, score in delta.head(5).items()
            ]
        return explanations
    except Exception:  # noqa: BLE001
        return {}


def _prepare_features_for_shap(X: pd.DataFrame, model: Any) -> tuple[pd.DataFrame | None, list[str]]:
    if hasattr(model, "feature_names_in_"):
        feature_names = list(getattr(model, "feature_names_in_"))
        if any(name not in X.columns for name in feature_names):
            return None, []
        return X[feature_names].copy(), feature_names

    numeric_columns = [column for column in X.columns if pd.api.types.is_numeric_dtype(X[column])]
    categorical_columns = [column for column in X.columns if column not in numeric_columns]
    if not categorical_columns:
        return X.copy(), list(X.columns)

    transformer = ColumnTransformer(
        transformers=[
            ("numeric", StandardScaler(), numeric_columns),
            ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical_columns),
        ],
        remainder="drop",
    )
    matrix = transformer.fit_transform(X)
    feature_names = list(transformer.get_feature_names_out())
    return pd.DataFrame(matrix, columns=feature_names, index=X.index), feature_names


def _build_explainer(model: Any, X: pd.DataFrame) -> Any:
    if hasattr(model, "predict_proba"):
        return shap.Explainer(model.predict_proba, X)
    return shap.Explainer(model, X)


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
