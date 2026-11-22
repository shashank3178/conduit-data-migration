import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiscoverySnapshot(Base):
    __tablename__ = "discovery_snapshots"
    __table_args__ = (UniqueConstraint("connection_id", name="uq_discovery_connection"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    database_name: Mapped[str] = mapped_column(String(128), nullable=False)
    server_version: Mapped[str | None] = mapped_column(String(255))
    schema_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class DiscoveredSchema(Base):
    __tablename__ = "discovered_schemas"
    __table_args__ = (UniqueConstraint("snapshot_id", "name", name="uq_discovered_schema_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("discovery_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_system: Mapped[bool] = mapped_column(nullable=False, default=False)


class DiscoveredTable(Base):
    __tablename__ = "discovered_tables"
    __table_args__ = (UniqueConstraint("schema_id", "name", name="uq_discovered_table_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schema_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("discovered_schemas.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    table_type: Mapped[str] = mapped_column(String(30), nullable=False, default="table")
    estimated_rows: Mapped[int | None] = mapped_column(Integer)  # diagnostic estimate only
    estimated_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    columns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    primary_key: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    foreign_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    unique_constraints: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    check_constraints: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    indexes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    comment: Mapped[str | None] = mapped_column(Text)
