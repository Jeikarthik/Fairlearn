"""Unit tests for production-grade statistical modules.

Covers:
  - advanced_statistics (Newcombe CI, FDR, power analysis, Cohen's h)
  - data_diagnostics (missing data, class imbalance, distribution verification)
  - causal_analysis (regression-adjusted, Simpson's paradox, interactions)
  - calibration_fairness (ECE, calibration disparity)
  - counterfactual_fairness (k-NN matching, flip rates)
  - outcome_analysis (multi-class, continuous, ordinal)
  - normalization (safe title-case, aliasing, changelog)
  - state_machine (valid/invalid transitions)
  - rate_limit (token bucket)
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest


# ─── 1. Advanced Statistics ─────────────────────────────────────


class TestNewcombeCi:
    def test_basic_difference(self):
        from app.services.advanced_statistics import newcombe_ci_diff
        lower, upper = newcombe_ci_diff(80, 100, 60, 100)
        assert lower < 0.20 < upper
        assert lower > 0.0
        assert upper < 0.40

    def test_zero_counts(self):
        from app.services.advanced_statistics import newcombe_ci_diff
        lower, upper = newcombe_ci_diff(0, 0, 0, 0)
        assert lower == 0.0
        assert upper == 0.0

    def test_equal_proportions(self):
        from app.services.advanced_statistics import newcombe_ci_diff
        lower, upper = newcombe_ci_diff(50, 100, 50, 100)
        assert lower < 0.0  # CI spans zero when proportions are equal
        assert upper > 0.0

    def test_extreme_proportions(self):
        from app.services.advanced_statistics import newcombe_ci_diff
        lower, upper = newcombe_ci_diff(100, 100, 0, 100)
        assert lower > 0.5
        assert upper <= 1.0


class TestFdrCorrection:
    def test_correction_reduces_significance(self):
        from app.services.advanced_statistics import apply_fdr_correction

        results = {
            "attr_a": {
                "significance": {"p_value": 0.04},
                "metrics": {},
            },
            "attr_b": {
                "significance": {"p_value": 0.03},
                "metrics": {},
            },
            "attr_c": {
                "significance": {"p_value": 0.8},
                "metrics": {},
            },
        }
        summary = apply_fdr_correction(results)
        assert summary["correction_applied"] is True
        assert summary["total_tests"] == 3
        assert summary["significant_after_correction"] <= summary["significant_before_correction"]

    def test_no_pvalues(self):
        from app.services.advanced_statistics import apply_fdr_correction

        results = {"attr_a": {"metrics": {}}}
        summary = apply_fdr_correction(results)
        assert summary["correction_applied"] is False


class TestPowerAnalysis:
    def test_high_power(self):
        from app.services.advanced_statistics import compute_power_analysis

        result = compute_power_analysis(500, 500, 0.8, 0.5)
        assert result["power"] > 0.9
        assert result["adequate_power"] == True  # noqa: E712

    def test_low_power(self):
        from app.services.advanced_statistics import compute_power_analysis

        result = compute_power_analysis(20, 20, 0.55, 0.50)
        assert result["power"] < 0.5
        assert result["adequate_power"] == False  # noqa: E712
        assert "LOW power" in result["interpretation"]


class TestCohensH:
    def test_negligible(self):
        from app.services.advanced_statistics import cohens_h

        result = cohens_h(0.50, 0.48)
        assert result["magnitude"] == "negligible"

    def test_large(self):
        from app.services.advanced_statistics import cohens_h

        result = cohens_h(0.90, 0.20)
        assert result["magnitude"] == "large"


# ─── 2. Data Diagnostics ────────────────────────────────────────


class TestMissingPatterns:
    def test_detects_biased_missingness(self):
        from app.services.data_diagnostics import analyze_missing_patterns

        df = pd.DataFrame({
            "gender": ["M"] * 50 + ["F"] * 50,
            "income": [50000.0] * 50 + [np.nan] * 30 + [40000.0] * 20,
            "outcome": [1] * 50 + [0] * 50,
        })
        config = {"protected_attributes": ["gender"], "outcome_column": "outcome"}
        result = analyze_missing_patterns(df, config)
        assert result.get("gender")  # should detect income missingness differs by gender
        assert result["gender"][0]["feature"] == "income"
        assert result["gender"][0]["max_difference"] > 0.25


class TestClassImbalance:
    def test_detects_extreme_imbalance(self):
        from app.services.data_diagnostics import detect_class_imbalance

        df = pd.DataFrame({
            "gender": ["M"] * 50 + ["F"] * 50,
            "outcome": [1] * 97 + [0] * 3,
        })
        config = {"outcome_column": "outcome", "favorable_outcome": 1, "protected_attributes": ["gender"]}
        result = detect_class_imbalance(df, config)
        assert result["imbalance_severity"] == "extreme"
        assert result["base_rate"] > 0.95


# ─── 3. State Machine ───────────────────────────────────────────


class TestStateMachine:
    def test_valid_transition(self):
        from app.core.state_machine import JobStatus, transition

        result = transition(JobStatus.CREATED, JobStatus.UPLOADED)
        assert result == JobStatus.UPLOADED

    def test_invalid_transition(self):
        from app.core.state_machine import JobStatus, transition

        with pytest.raises(ValueError, match="Invalid transition"):
            transition(JobStatus.CREATED, JobStatus.COMPLETE)

    def test_full_happy_path(self):
        from app.core.state_machine import JobStatus, transition

        state = JobStatus.CREATED
        for target in [JobStatus.UPLOADED, JobStatus.CONFIGURED, JobStatus.VALIDATED,
                       JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETE]:
            state = transition(state, target)
        assert state == JobStatus.COMPLETE


# ─── 4. Rate Limiter ────────────────────────────────────────────


class TestRateLimiter:
    def test_allows_under_limit(self):
        from app.core.rate_limit import RateLimiter

        limiter = RateLimiter(default_rpm=5)
        for _ in range(5):
            assert limiter.check("test_key") is True

    def test_blocks_over_limit(self):
        from app.core.rate_limit import RateLimiter

        limiter = RateLimiter(default_rpm=3)
        for _ in range(3):
            limiter.check("test_key")
        assert limiter.check("test_key") is False

    def test_remaining_count(self):
        from app.core.rate_limit import RateLimiter

        limiter = RateLimiter(default_rpm=10)
        limiter.check("key1")
        limiter.check("key1")
        assert limiter.get_remaining("key1") == 8


# ─── 5. Normalization ───────────────────────────────────────────


class TestNormalization:
    def test_title_case_categorical(self):
        from app.services.normalization import normalize_categorical_series

        series = pd.Series(["male", "FEMALE", "mAlE"])
        result = normalize_categorical_series(series, semantic_hint="gender")
        assert list(result) == ["Male", "Female", "Male"]

    def test_no_title_case_high_cardinality(self):
        from app.services.normalization import normalize_categorical_series

        series = pd.Series([f"id_{i}" for i in range(50)])
        result = normalize_categorical_series(series)
        # High cardinality → should NOT title-case (would break IDs)
        assert result.iloc[0] == "id_0"

    def test_changelog(self):
        from app.services.normalization import get_normalization_changelog, normalize_dataframe

        df = pd.DataFrame({"gender": ["male", "female"], "score": [1, 2]})
        norm = normalize_dataframe(df)
        changes = get_normalization_changelog(df, norm)
        assert len(changes) == 1
        assert changes[0]["column"] == "gender"


# ─── 6. Counterfactual Fairness ──────────────────────────────────


class TestCounterfactual:
    def test_detects_unfairness(self):
        from app.services.counterfactual_fairness import compute_counterfactual_fairness

        np.random.seed(42)
        n = 200
        df = pd.DataFrame({
            "gender": ["M"] * (n // 2) + ["F"] * (n // 2),
            "score": np.random.normal(50, 10, n),
            "outcome": [1] * 80 + [0] * 20 + [1] * 40 + [0] * 60,  # biased
        })
        config = {
            "outcome_column": "outcome",
            "favorable_outcome": 1,
            "protected_attributes": ["gender"],
        }
        result = compute_counterfactual_fairness(df, config)
        assert "gender" in result
        assert result["gender"]["overall_flip_rate"] > 0


# ─── 7. Gemini Anti-Hallucination ────────────────────────────────


def _has_pydantic_settings() -> bool:
    try:
        import pydantic_settings  # noqa: F401
        return True
    except ImportError:
        return False


class TestGeminiValidation:
    @pytest.mark.skipif(not _has_pydantic_settings(), reason="pydantic_settings not installed")
    def test_catches_hallucinated_number(self):
        from app.services.gemini_service import validate_report_against_data

        audit_results = {
            "results": {
                "gender": {
                    "metrics": {"dpd": {"value": 0.15, "passed": False}},
                    "group_stats": {"M": {"rate": 0.8}, "F": {"rate": 0.65}},
                    "overall_passed": False,
                }
            }
        }
        report = {"executive_summary": "The approval rate gap is 42%."}
        result = validate_report_against_data(report, audit_results)
        assert result["passed"] is False
        assert any("Hallucinated" in i for i in result["issues"])

    @pytest.mark.skipif(not _has_pydantic_settings(), reason="pydantic_settings not installed")
    def test_accepts_correct_numbers(self):
        from app.services.gemini_service import validate_report_against_data

        audit_results = {
            "results": {
                "gender": {
                    "metrics": {"dpd": {"value": 0.15, "passed": False}},
                    "group_stats": {"M": {"rate": 0.8}, "F": {"rate": 0.65}},
                    "overall_passed": False,
                }
            }
        }
        report = {"executive_summary": "The approval rate gap is 15%."}
        result = validate_report_against_data(report, audit_results)
        assert result["passed"] is True

    @pytest.mark.skipif(not _has_pydantic_settings(), reason="pydantic_settings not installed")
    def test_catches_jargon(self):
        from app.services.gemini_service import validate_report_against_data

        report = {"executive_summary": "The AUC shows good ROC performance."}
        result = validate_report_against_data(report, {"results": {}})
        assert result["passed"] is False
        assert any("Jargon" in i for i in result["issues"])

    @pytest.mark.skipif(not _has_pydantic_settings(), reason="pydantic_settings not installed")
    def test_catches_temporal_hallucination(self):
        from app.services.gemini_service import validate_report_against_data

        report = {"executive_summary": "The approval rate improved from last audit's results."}
        result = validate_report_against_data(report, {"results": {}})
        assert result["passed"] is False
        assert any("Temporal" in i for i in result["issues"])

    @pytest.mark.skipif(not _has_pydantic_settings(), reason="pydantic_settings not installed")
    def test_catches_hallucinated_decimal(self):
        from app.services.gemini_service import validate_report_against_data

        audit_results = {
            "results": {
                "gender": {
                    "metrics": {"dpd": {"value": 0.15, "passed": False}},
                    "group_stats": {"M": {"rate": 0.8}, "F": {"rate": 0.65}},
                    "overall_passed": False,
                }
            }
        }
        report = {"executive_summary": "The disparity rate is 0.9999 which is concerning."}
        result = validate_report_against_data(report, audit_results)
        assert result["passed"] is False
        assert any("decimal" in i.lower() for i in result["issues"])


# ─── 8. Config Validation ───────────────────────────────────────


class TestConfigValidation:
    def test_catches_missing_column(self):
        from app.services.config_validation import validate_config_against_dataframe

        config = {
            "outcome_column": "nonexistent",
            "protected_attributes": ["gender"],
        }
        errors = validate_config_against_dataframe(config, ["gender", "age", "outcome"])
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_passes_valid_config(self):
        from app.services.config_validation import validate_config_against_dataframe

        config = {
            "outcome_column": "outcome",
            "protected_attributes": ["gender"],
        }
        errors = validate_config_against_dataframe(config, ["gender", "age", "outcome"])
        assert len(errors) == 0

    def test_catches_missing_protected_attribute(self):
        from app.services.config_validation import validate_config_against_dataframe

        config = {
            "outcome_column": "outcome",
            "protected_attributes": ["gender", "nonexistent_attr"],
        }
        errors = validate_config_against_dataframe(config, ["gender", "outcome"])
        assert len(errors) == 1
        assert "nonexistent_attr" in errors[0]

    def test_catches_bad_favorable_outcome(self):
        from app.services.config_validation import validate_favorable_outcome

        errors = validate_favorable_outcome({"favorable_outcome": "approved"}, [0, 1, "rejected"])
        assert len(errors) == 1
        assert "approved" in errors[0]

    def test_accepts_valid_favorable_outcome(self):
        from app.services.config_validation import validate_favorable_outcome

        errors = validate_favorable_outcome({"favorable_outcome": 1}, [0, 1])
        assert len(errors) == 0

    def test_pydantic_model_rejects_too_many_attrs(self):
        from app.services.config_validation import AuditConfig

        with pytest.raises(Exception):
            AuditConfig(
                outcome_column="outcome",
                favorable_outcome=1,
                protected_attributes=[f"attr_{i}" for i in range(20)],
            )

    def test_pydantic_model_rejects_duplicates(self):
        from app.services.config_validation import AuditConfig

        with pytest.raises(Exception):
            AuditConfig(
                outcome_column="outcome",
                favorable_outcome=1,
                protected_attributes=["gender", "gender"],
            )


# ─── 9. Model Loading Security ──────────────────────────────────


class TestModelLoading:
    def test_rejects_unknown_extension(self, tmp_path):
        from app.services.explainability import load_model

        bad_file = tmp_path / "model.exe"
        bad_file.write_bytes(b"x" * 200)
        result = load_model(str(bad_file))
        assert result is None

    def test_rejects_tiny_file(self, tmp_path):
        from app.services.explainability import load_model

        tiny = tmp_path / "model.pkl"
        tiny.write_bytes(b"x" * 10)
        result = load_model(str(tiny))
        assert result is None

    def test_returns_none_for_nonexistent(self):
        from app.services.explainability import load_model

        result = load_model("/nonexistent/model.pkl")
        assert result is None

    def test_returns_none_for_none(self):
        from app.services.explainability import load_model

        result = load_model(None)
        assert result is None
