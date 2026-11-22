import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MigrationPlan(Base):
    __tablename__ = "migration_plans"
    __table_args__ = (
        Index("ix_migration_plans_project_owner", "project_id", "owner_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False)
    destination_connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("discovery_snapshots.id", ondelete="CASCADE"), nullable=False)
    destination_snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("discovery_snapshots.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    create_schemas: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MigrationPlanTable(Base):
    __tablename__ = "migration_plan_tables"
    __table_args__ = (
        UniqueConstraint("plan_id", "source_schema", "source_table", name="uq_plan_source_table"),
        Index("ix_migration_plan_tables_plan", "plan_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("migration_plans.id", ondelete="CASCADE"), nullable=False)
    source_table_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    destination_table_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_schema: Mapped[str] = mapped_column(String(128), nullable=False)
    source_table: Mapped[str] = mapped_column(String(128), nullable=False)
    source_table_type: Mapped[str] = mapped_column(String(30), nullable=False)
    destination_schema: Mapped[str] = mapped_column(String(128), nullable=False)
    destination_table: Mapped[str] = mapped_column(String(128), nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    destination_exists: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    estimated_rows: Mapped[int | None] = mapped_column(Integer)
    source_columns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    destination_columns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_primary_key: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class MigrationColumnMapping(Base):
    __tablename__ = "migration_column_mappings"
    __table_args__ = (
        UniqueConstraint("plan_table_id", "source_column", name="uq_plan_source_column"),
        Index("ix_migration_column_mappings_table", "plan_table_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_table_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("migration_plan_tables.id", ondelete="CASCADE"), nullable=False)
    source_column: Mapped[str] = mapped_column(String(128), nullable=False)
    destination_column: Mapped[str | None] = mapped_column(String(128))
    source_type: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_type: Mapped[str | None] = mapped_column(String(255))
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    compatible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    match_strategy: Mapped[str] = mapped_column(String(30), nullable=False, default="unmapped")
