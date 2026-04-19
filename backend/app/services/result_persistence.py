"""Persist audit results into normalized database tables.

This module takes the JSON dict returned by run_audit() and fans it out
into the AuditMetric, ProxyFeature, GroupStat tables so results are
queryable with standard SQL.

The original JSON blob is kept in AuditJob.results_json for backward
compatibility — this module adds the normalized copy.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.audit_results import AuditEvent, AuditMetric, GroupStat, ProxyFeature


def persist_audit_results(db: Session, job_id: str, results: dict[str, Any]) -> None:
    """Fan out audit results into normalized tables — idempotent (safe to call multiple times)."""
    from sqlalchemy import delete

    # Delete stale rows first so re-runs don't create duplicates
    db.execute(delete(AuditMetric).where(AuditMetric.job_id == job_id))
    db.execute(delete(GroupStat).where(GroupStat.job_id == job_id))
    db.execute(delete(ProxyFeature).where(ProxyFeature.job_id == job_id))
    db.flush()

    _persist_metrics(db, job_id, results)
    _persist_group_stats(db, job_id, results)
    _persist_proxy_features(db, job_id, results)
    _log_event(db, job_id, "audit.results_persisted", {"status": results.get("status")})
    db.commit()


def _persist_metrics(db: Session, job_id: str, results: dict[str, Any]) -> None:
    for attribute, attr_data in results.get("results", {}).items():
        significance = attr_data.get("significance", {})
        for metric_name, metric_data in attr_data.get("metrics", {}).items():
            db.add(
                AuditMetric(
                    id=str(uuid4()),
                    job_id=job_id,
                    attribute=attribute,
                    metric_name=metric_name,
                    value=metric_data.get("value"),
                    ci_lower=metric_data.get("ci_lower"),
                    ci_upper=metric_data.get("ci_upper"),
                    threshold=metric_data.get("threshold"),
                    passed=metric_data.get("passed"),
                    conclusive=metric_data.get("conclusive"),
                    best_group=metric_data.get("best_group"),
                    worst_group=metric_data.get("worst_group"),
                    p_value=significance.get("p_value"),
                    significant=significance.get("significant"),
                )
            )


def _persist_group_stats(db: Session, job_id: str, results: dict[str, Any]) -> None:
    for attribute, attr_data in results.get("results", {}).items():
        for group_name, stat_data in attr_data.get("group_stats", {}).items():
            db.add(
                GroupStat(
                    id=str(uuid4()),
                    job_id=job_id,
                    attribute=attribute,
                    group_name=group_name,
                    total=stat_data.get("total", 0),
                    favorable=stat_data.get("favorable", 0),
                    rate=stat_data.get("rate", 0.0),
                )
            )


def _persist_proxy_features(db: Session, job_id: str, results: dict[str, Any]) -> None:
    for proxy in results.get("proxy_features", []):
        db.add(
            ProxyFeature(
                id=str(uuid4()),
                job_id=job_id,
                feature=proxy.get("feature", ""),
                correlated_with=proxy.get("correlated_with", ""),
                correlation=proxy.get("correlation", 0.0),
                method=proxy.get("method", ""),
            )
        )


def log_audit_event(
    db: Session,
    *,
    job_id: str | None = None,
    user_id: str | None = None,
    org_id: str | None = None,
    event_type: str,
    event_data: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Write an immutable audit trail event."""
    db.add(
        AuditEvent(
            id=str(uuid4()),
            job_id=job_id,
            user_id=user_id,
            org_id=org_id,
            event_type=event_type,
            event_data_json=json.dumps(event_data) if event_data else None,
            ip_address=ip_address,
        )
    )
    db.commit()


def _log_event(db: Session, job_id: str, event_type: str, data: dict[str, Any]) -> None:
    log_audit_event(db, job_id=job_id, event_type=event_type, event_data=data)
