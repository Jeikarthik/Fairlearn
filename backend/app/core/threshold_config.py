"""Configurable, versioned threshold system.

Domain presets:
  employment  — EEOC 4/5ths rule baseline (hiring, promotion)
  lending     — ECOA / Fair Housing Act (credit, mortgages)
  healthcare  — CMS access-rate parity (clinical decisions)
  education   — Title VI / disparate impact (admissions, grading)
  general     — Default balanced thresholds

Thresholds are stored as a versioned snapshot with each audit result so
old audits remain reproducible even when defaults change.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import asdict, dataclass
from typing import Any

DOMAIN_PRESETS: dict[str, dict[str, float]] = {
    "employment": {
        "demographic_parity_threshold": 0.10,
        "disparate_impact_threshold": 0.80,  # EEOC 4/5ths rule
        "equal_opportunity_threshold": 0.10,
        "predictive_parity_threshold": 0.10,
        "accuracy_equity_threshold": 0.05,
        "fnr_disparity_threshold": 0.10,
        "proxy_cramers_v_threshold": 0.25,
        "proxy_point_biserial_threshold": 0.20,
        "proxy_pearson_threshold": 0.30,
        "proxy_eta_squared_threshold": 0.20,
    },
    "lending": {
        "demographic_parity_threshold": 0.08,
        "disparate_impact_threshold": 0.80,  # ECOA / Fair Housing 4/5ths
        "equal_opportunity_threshold": 0.08,
        "predictive_parity_threshold": 0.08,
        "accuracy_equity_threshold": 0.05,
        "fnr_disparity_threshold": 0.08,
        "proxy_cramers_v_threshold": 0.20,
        "proxy_point_biserial_threshold": 0.15,
        "proxy_pearson_threshold": 0.25,
        "proxy_eta_squared_threshold": 0.15,
    },
    "healthcare": {
        "demographic_parity_threshold": 0.05,
        "disparate_impact_threshold": 0.85,
        "equal_opportunity_threshold": 0.05,
        "predictive_parity_threshold": 0.05,
        "accuracy_equity_threshold": 0.03,
        "fnr_disparity_threshold": 0.05,
        "proxy_cramers_v_threshold": 0.20,
        "proxy_point_biserial_threshold": 0.15,
        "proxy_pearson_threshold": 0.25,
        "proxy_eta_squared_threshold": 0.15,
    },
    "education": {
        "demographic_parity_threshold": 0.10,
        "disparate_impact_threshold": 0.80,
        "equal_opportunity_threshold": 0.10,
        "predictive_parity_threshold": 0.10,
        "accuracy_equity_threshold": 0.05,
        "fnr_disparity_threshold": 0.10,
        "proxy_cramers_v_threshold": 0.25,
        "proxy_point_biserial_threshold": 0.20,
        "proxy_pearson_threshold": 0.30,
        "proxy_eta_squared_threshold": 0.20,
    },
    "general": {
        "demographic_parity_threshold": 0.10,
        "disparate_impact_threshold": 0.80,
        "equal_opportunity_threshold": 0.10,
        "predictive_parity_threshold": 0.10,
        "accuracy_equity_threshold": 0.05,
        "fnr_disparity_threshold": 0.10,
        "proxy_cramers_v_threshold": 0.30,
        "proxy_point_biserial_threshold": 0.25,
        "proxy_pearson_threshold": 0.30,
        "proxy_eta_squared_threshold": 0.25,
    },
}

_PROXY_METHOD_KEYS = {
    "cramers_v": "proxy_cramers_v_threshold",
    "point_biserial": "proxy_point_biserial_threshold",
    "pearson": "proxy_pearson_threshold",
    "eta_squared": "proxy_eta_squared_threshold",
}


@dataclass
class ThresholdConfig:
    """Immutable threshold snapshot stored verbatim with every audit result.

    Using a dataclass (not a plain dict) so callers get attribute access
    and we can fingerprint the values deterministically.
    """

    domain: str = "general"
    demographic_parity_threshold: float = 0.10
    disparate_impact_threshold: float = 0.80
    equal_opportunity_threshold: float = 0.10
    predictive_parity_threshold: float = 0.10
    accuracy_equity_threshold: float = 0.05
    fnr_disparity_threshold: float = 0.10
    # Per-method proxy correlation thresholds (different statistics need different calibration)
    proxy_cramers_v_threshold: float = 0.30
    proxy_point_biserial_threshold: float = 0.25
    proxy_pearson_threshold: float = 0.30
    proxy_eta_squared_threshold: float = 0.25

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def fingerprint(self) -> str:
        """16-hex-char SHA-256 of threshold values for reproducibility tracking."""
        canonical = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def proxy_threshold_for(self, method: str) -> float:
        """Return the calibrated proxy threshold for the given correlation method."""
        key = _PROXY_METHOD_KEYS.get(method)
        if key:
            return float(getattr(self, key))
        return self.proxy_cramers_v_threshold  # safe fallback


def build_threshold_config(config: dict[str, Any]) -> ThresholdConfig:
    """Construct a ThresholdConfig from an audit config dict.

    Priority (highest → lowest):
      1. config["thresholds"][key]   — explicit per-audit overrides
      2. DOMAIN_PRESETS[domain][key] — domain-specific preset
      3. ThresholdConfig defaults    — general fallback
    """
    domain = config.get("domain", "general")
    preset = DOMAIN_PRESETS.get(domain, DOMAIN_PRESETS["general"]).copy()

    overrides = config.get("thresholds", {})
    for key, value in overrides.items():
        if key in preset:
            preset[key] = float(value)

    return ThresholdConfig(domain=domain, **preset)


def algorithm_fingerprint() -> str:
    """SHA-256 of core metric functions — changes when the math changes.

    Store this with every audit result so old audits can be reproduced
    against the exact algorithm version that produced them.
    """
    try:
        from app.services.audit_engine import _audit_attribute, wilson_ci
        from app.services.advanced_statistics import newcombe_ci_diff

        code = (
            inspect.getsource(_audit_attribute)
            + inspect.getsource(wilson_ci)
            + inspect.getsource(newcombe_ci_diff)
        )
        return hashlib.sha256(code.encode()).hexdigest()[:16]
    except Exception:
        return "unavailable"
