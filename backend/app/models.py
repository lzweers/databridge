from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utc_now():
    return datetime.now(timezone.utc)


class ImportRun(Base):
    __tablename__ = "import_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unchanged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SupplierOffer(Base):
    __tablename__ = "supplier_offers"
    __table_args__ = (UniqueConstraint("source_name", "external_id", name="uq_source_external"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_import_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id"), nullable=False)


class SourceRow(Base):
    __tablename__ = "source_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class ValidationIssue(Base):
    __tablename__ = "validation_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str] = mapped_column(String(80), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)


class OfferEvent(Base):
    """Immutable per-row decision, linking input data to its resulting offer state.

    Added in v0.3. No historical events are fabricated for earlier imports.
    """
    __tablename__ = "offer_events"
    __table_args__ = (UniqueConstraint("source_row_id", name="uq_offer_event_source_row"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id"), nullable=False, index=True)
    source_row_id: Mapped[int] = mapped_column(ForeignKey("source_rows.id"), nullable=False)
    offer_id: Mapped[int] = mapped_column(ForeignKey("supplier_offers.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PipelineSchedule(Base):
    """One explicitly configured, allowlisted recurring connector per pipeline."""
    __tablename__ = "pipeline_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    connector: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="idle", nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_import_id: Mapped[int | None] = mapped_column(ForeignKey("import_runs.id"))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineExecution(Base):
    """Persistent monitoring record for each attempt, including failed fetches."""
    __tablename__ = "pipeline_executions"
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("pipeline_schedules.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    import_id: Mapped[int | None] = mapped_column(ForeignKey("import_runs.id"))
