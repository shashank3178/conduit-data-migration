"""persist PostgreSQL discovery snapshots and metadata

Revision ID: 4f1a7c2d9b30
Revises: 8a42c1d9f301
Create Date: 2026-11-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "4f1a7c2d9b30"
down_revision: Union[str, None] = "8a42c1d9f301"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("discovery_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("database_name", sa.String(128), nullable=False),
        sa.Column("server_version", sa.String(255)),
        sa.Column("schema_count", sa.Integer(), nullable=False),
        sa.Column("table_count", sa.Integer(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["database_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", name="uq_discovery_connection"))
    op.create_index("ix_discovery_snapshots_project_id", "discovery_snapshots", ["project_id"])
    op.create_index("ix_discovery_snapshots_connection_id", "discovery_snapshots", ["connection_id"])
    op.create_table("discovered_schemas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["discovery_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", "name", name="uq_discovered_schema_name"))
    op.create_index("ix_discovered_schemas_snapshot_id", "discovered_schemas", ["snapshot_id"])
    op.create_table("discovered_tables",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("table_type", sa.String(30), nullable=False),
        sa.Column("estimated_rows", sa.Integer()),
        sa.Column("columns", postgresql.JSONB(), nullable=False),
        sa.Column("primary_key", postgresql.JSONB(), nullable=False),
        sa.Column("foreign_keys", postgresql.JSONB(), nullable=False),
        sa.Column("unique_constraints", postgresql.JSONB(), nullable=False),
        sa.Column("check_constraints", postgresql.JSONB(), nullable=False),
        sa.Column("indexes", postgresql.JSONB(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.ForeignKeyConstraint(["schema_id"], ["discovered_schemas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schema_id", "name", name="uq_discovered_table_name"))
    op.create_index("ix_discovered_tables_schema_id", "discovered_tables", ["schema_id"])


def downgrade() -> None:
    op.drop_index("ix_discovered_tables_schema_id", table_name="discovered_tables")
    op.drop_table("discovered_tables")
    op.drop_index("ix_discovered_schemas_snapshot_id", table_name="discovered_schemas")
    op.drop_table("discovered_schemas")
    op.drop_index("ix_discovery_snapshots_connection_id", table_name="discovery_snapshots")
    op.drop_index("ix_discovery_snapshots_project_id", table_name="discovery_snapshots")
    op.drop_table("discovery_snapshots")
