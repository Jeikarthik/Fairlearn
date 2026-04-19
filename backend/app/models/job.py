"""AuditJob model — production-grade with indexes, composite indexes, and schema v3."""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditJob(Base):
    __tablename__ = "audit_jobs"

    # ── Primary key ──────────────────────────────────
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # ── Core fields ──────────────────────────────────
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Multi-tenancy ────────────────────────────────
    org_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # ── Schema versioning ────────────────────────────
    schema_version: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # ── JSON data (TEXT for SQLite, will work as JSONB on Postgres via Alembic) ──
    upload_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    results_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Timestamps ───────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # ── Composite indexes for common query patterns ──
    __table_args__ = (
        Index("ix_jobs_org_status", "org_id", "status"),           # Dashboard: "my org's running jobs"
        Index("ix_jobs_org_created", "org_id", "created_at"),      # History: "my org's recent audits"
        Index("ix_jobs_user_created", "user_id", "created_at"),    # User: "my recent audits"
        Index("ix_jobs_status_created", "status", "created_at"),   # Admin: "all queued jobs, oldest first"
    )
