import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MigrationRun(Base):
    __tablename__ = "migration_runs"
    __table_args__ = (Index("ix_migration_runs_project_owner", "project_id", "owner_id"), Index("ix_migration_runs_worker_status", "worker_id", "status"))

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("migration_plans.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    write_strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="INSERT_ONLY")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    total_tables: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_tables: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    migrated_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    mismatch_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MigrationRunTable(Base):
    __tablename__ = "migration_run_tables"
    __table_args__ = (Index("ix_migration_run_tables_run", "run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("migration_runs.id", ondelete="CASCADE"), nullable=False)
    plan_table_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("migration_plan_tables.id", ondelete="CASCADE"), nullable=False)
    source_schema: Mapped[str] = mapped_column(String(128), nullable=False)
    source_table: Mapped[str] = mapped_column(String(128), nullable=False)
    destination_schema: Mapped[str] = mapped_column(String(128), nullable=False)
    destination_table: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    migrated_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_key: Mapped[list | None] = mapped_column(JSONB)
    upper_key: Mapped[list | None] = mapped_column(JSONB)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    mismatch_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)


class MigrationRowError(Base):
    __tablename__ = "migration_row_errors"
    __table_args__ = (Index("ix_migration_row_errors_run", "run_id"), Index("ix_migration_row_errors_table", "run_table_id"))

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("migration_runs.id", ondelete="CASCADE"), nullable=False)
    run_table_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("migration_run_tables.id", ondelete="CASCADE"), nullable=False)
    source_key: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_type: Mapped[str] = mapped_column(String(120), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MigrationRunEvent(Base):
    __tablename__ = "migration_run_events"
    __table_args__ = (Index("ix_migration_run_events_run_created", "run_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("migration_runs.id", ondelete="CASCADE"), nullable=False)
    run_table_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("migration_run_tables.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
