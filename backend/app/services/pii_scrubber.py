"""PII Scrubbing Service — Strategy Pattern for easy backend swapping.

Architecture:
    BasePIIScrubber (abstract)  ←  RegexPIIScrubber (current, lightweight)
                                ←  PresidioPIIScrubber (future, NLP-grade)

Swapping to a production scrubber later requires only:
    1. pip install presidio-analyzer presidio-anonymizer
    2. Implement PresidioPIIScrubber(BasePIIScrubber)
    3. Change get_scrubber() to return the new class

No routing or audit logic changes needed.
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger("fairlens")


# ── Scan Report ──────────────────────────────────────────


@dataclass
class PIIFinding:
    """A single PII detection in a specific column."""
    column: str
    pii_type: str
    count: int
    sample_indices: list[int] = field(default_factory=list)


@dataclass
class PIIScanReport:
    """Summary of all PII found or redacted in a DataFrame."""
    total_cells_scanned: int = 0
    total_pii_found: int = 0
    findings: list[PIIFinding] = field(default_factory=list)
    columns_affected: list[str] = field(default_factory=list)
    scrubbed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cells_scanned": self.total_cells_scanned,
            "total_pii_found": self.total_pii_found,
            "columns_affected": self.columns_affected,
            "scrubbed": self.scrubbed,
            "findings": [
                {
                    "column": f.column,
                    "pii_type": f.pii_type,
                    "count": f.count,
                    "sample_indices": f.sample_indices[:5],
                }
                for f in self.findings
            ],
        }


# ── Abstract Base ────────────────────────────────────────


class BasePIIScrubber(ABC):
    """Contract for PII scrubbing implementations.

    Implement this interface to swap between lightweight regex
    and production-grade NLP scrubbers without touching routes.
    """

    @abstractmethod
    def scan_dataframe(self, df: pd.DataFrame) -> PIIScanReport:
        """Non-destructive scan — returns what PII was detected."""
        ...

    @abstractmethod
    def scrub_dataframe(self, df: pd.DataFrame) -> tuple[pd.DataFrame, PIIScanReport]:
        """Destructive scrub — returns cleaned df + report of what was redacted."""
        ...


# ── Regex Implementation ─────────────────────────────────


# Pre-compiled patterns for performance
_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    ),
    "phone": re.compile(
        r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    "ssn": re.compile(
        r"\b\d{3}-\d{2}-\d{4}\b"
    ),
    "credit_card": re.compile(
        r"\b(?:\d[ -]*?){13,19}\b"
    ),
    "ipv4": re.compile(
        r"\b(?:25[0-5]|2[0-4]\d|[01]?\d\d?)(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)){3}\b"
    ),
}

_REDACTION_LABELS: dict[str, str] = {
    "email": "[EMAIL_REDACTED]",
    "phone": "[PHONE_REDACTED]",
    "ssn": "[SSN_REDACTED]",
    "credit_card": "[CC_REDACTED]",
    "ipv4": "[IP_REDACTED]",
}


class RegexPIIScrubber(BasePIIScrubber):
    """Lightweight regex-based PII scrubber.

    Detects and redacts: emails, phone numbers, SSNs,
    credit card numbers, and IPv4 addresses.

    Trade-offs vs NLP scrubbers:
        + Zero extra dependencies, fast, low RAM
        - Cannot detect names, addresses, or contextual PII
    """

    def scan_dataframe(self, df: pd.DataFrame) -> PIIScanReport:
        """Scan without modifying data."""
        report = PIIScanReport(total_cells_scanned=0)
        columns_affected: set[str] = set()

        for col in df.columns:
            if df[col].dtype != object:
                continue
            series = df[col].astype(str)
            report.total_cells_scanned += len(series)

            for pii_type, pattern in _PATTERNS.items():
                matches = series.apply(lambda val, p=pattern: bool(p.search(str(val))))
                match_count = int(matches.sum())
                if match_count > 0:
                    report.total_pii_found += match_count
                    columns_affected.add(col)
                    indices = matches[matches].index.tolist()
                    report.findings.append(
                        PIIFinding(
                            column=col,
                            pii_type=pii_type,
                            count=match_count,
                            sample_indices=indices[:5],
                        )
                    )

        report.columns_affected = sorted(columns_affected)
        return report

    def scrub_dataframe(self, df: pd.DataFrame) -> tuple[pd.DataFrame, PIIScanReport]:
        """Redact PII in-place and return the cleaned DataFrame + report."""
        df_clean = df.copy()
        report = PIIScanReport(total_cells_scanned=0, scrubbed=True)
        columns_affected: set[str] = set()

        for col in df_clean.columns:
            if df_clean[col].dtype != object:
                continue
            series = df_clean[col].astype(str)
            report.total_cells_scanned += len(series)

            for pii_type, pattern in _PATTERNS.items():
                matches = series.apply(lambda val, p=pattern: bool(p.search(str(val))))
                match_count = int(matches.sum())

                if match_count > 0:
                    report.total_pii_found += match_count
                    columns_affected.add(col)
                    indices = matches[matches].index.tolist()
                    report.findings.append(
                        PIIFinding(
                            column=col,
                            pii_type=pii_type,
                            count=match_count,
                            sample_indices=indices[:5],
                        )
                    )
                    # Perform the actual redaction
                    label = _REDACTION_LABELS[pii_type]
                    df_clean[col] = df_clean[col].astype(str).apply(
                        lambda val, p=pattern, lb=label: p.sub(lb, str(val))
                    )

        report.columns_affected = sorted(columns_affected)

        if report.total_pii_found > 0:
            logger.info(
                "pii.scrubbed",
                extra={
                    "cells_scanned": report.total_cells_scanned,
                    "pii_found": report.total_pii_found,
                    "columns": report.columns_affected,
                },
            )

        return df_clean, report


# ── Factory ──────────────────────────────────────────────


def get_scrubber() -> BasePIIScrubber:
    """Return the active PII scrubber implementation.

    To upgrade to Presidio, change this function to return
    PresidioPIIScrubber() and install the presidio packages.
    """
    return RegexPIIScrubber()
