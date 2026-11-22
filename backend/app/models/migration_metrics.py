import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MigrationRunMetric(Base):
    __tablename__ = "migration_run_metrics"
    __table_args__ = (Index("ix_migration_run_metrics_updated", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("migration_runs.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    rows_fetched: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rows_committed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    batches_committed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    logical_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    processing_duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    rows_per_second: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    logical_bytes_per_second: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    source_fetch_duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    destination_write_duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    metadata_commit_duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    source_network_rtt_ms: Mapped[float | None] = mapped_column(Float)
    destination_network_rtt_ms: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class MigrationBatchMetric(Base):
    __tablename__ = "migration_batch_metrics"
    __table_args__ = (
        UniqueConstraint("run_id", "batch_key", name="uq_migration_batch_run_key"),
        Index("ix_migration_batch_run_sequence", "run_id", "sequence"),
        Index("ix_migration_batch_table_created", "run_table_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("migration_runs.id", ondelete="CASCADE"), nullable=False,
    )
    run_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("migration_run_tables.id", ondelete="CASCADE"), nullable=False,
    )
    batch_key: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    logical_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    source_fetch_duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    destination_write_duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    network_rtt_ms: Mapped[float | None] = mapped_column(Float)
    checkpoint_start: Mapped[list | None] = mapped_column(JSONB)
    checkpoint_end: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class MigrationTableMetric(Base):
    __tablename__ = "migration_table_metrics"
    __table_args__ = (UniqueConstraint("run_table_id", name="uq_migration_table_metric_run_table"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("migration_runs.id", ondelete="CASCADE"), nullable=False,
    )
    run_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("migration_run_tables.id", ondelete="CASCADE"), nullable=False,
    )
    rows_fetched: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rows_committed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    batches_committed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    logical_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    source_physical_bytes: Mapped[int | None] = mapped_column(BigInteger)
    destination_physical_bytes: Mapped[int | None] = mapped_column(BigInteger)
    storage_measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MigrationDatabaseMetric(Base):
    __tablename__ = "migration_database_metrics"
    __table_args__ = (
        Index("ix_migration_database_metrics_run_role_time", "run_id", "role", "captured_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("migration_runs.id", ondelete="CASCADE"), nullable=False,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    database_name: Mapped[str] = mapped_column(String(128), nullable=False)
    physical_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    measurement_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="exact")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
