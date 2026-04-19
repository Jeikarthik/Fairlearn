"""Normalized audit result models — replaces JSON blob storage.

Each result table is independently queryable, indexable, and enforces
referential integrity back to the parent AuditJob.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditMetric(Base):
    """One row per (job × attribute × metric).  Fully indexed."""

    __tablename__ = "audit_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("audit_jobs.id"), nullable=False, index=True)
    attribute: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    conclusive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    best_group: Mapped[str | None] = mapped_column(String(128), nullable=True)
    worst_group: Mapped[str | None] = mapped_column(String(128), nullable=True)
    p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    significant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class ProxyFeature(Base):
    """Proxy features detected during an audit."""

    __tablename__ = "proxy_features"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("audit_jobs.id"), nullable=False, index=True)
    feature: Mapped[str] = mapped_column(String(128), nullable=False)
    correlated_with: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)


class AuditReport(Base):
    """Generated report text with validation metadata."""

    __tablename__ = "audit_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("audit_jobs.id"), nullable=False, index=True)
    executive_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    intersectional_findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxy_warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    validation_issues_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    gemini_model_used: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GroupStat(Base):
    """Per-group statistics for each audited attribute."""

    __tablename__ = "group_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("audit_jobs.id"), nullable=False, index=True)
    attribute: Mapped[str] = mapped_column(String(128), nullable=False)
    group_name: Mapped[str] = mapped_column(String(128), nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    favorable: Mapped[int] = mapped_column(Integer, nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)


class AuditEvent(Base):
    """Immutable compliance audit trail — every action logged."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("audit_jobs.id"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    org_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
