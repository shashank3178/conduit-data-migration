"""add migration planning configurations, selections, and mappings

Revision ID: b7a4c2d9e610
Revises: 4f1a7c2d9b30
Create Date: 2026-11-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b7a4c2d9e610"
down_revision: Union[str, None] = "4f1a7c2d9b30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "migration_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("destination_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("destination_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("create_schemas", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_connection_id"], ["database_connections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["destination_connection_id"], ["database_connections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_snapshot_id"], ["discovery_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["destination_snapshot_id"], ["discovery_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_migration_plans_project_owner", "migration_plans", ["project_id", "owner_id"])

    op.create_table(
        "migration_plan_tables",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_table_id", postgresql.UUID(as_uuid=True)),
        sa.Column("destination_table_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_schema", sa.String(128), nullable=False),
        sa.Column("source_table", sa.String(128), nullable=False),
        sa.Column("source_table_type", sa.String(30), nullable=False),
        sa.Column("destination_schema", sa.String(128), nullable=False),
        sa.Column("destination_table", sa.String(128), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("destination_exists", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("estimated_rows", sa.Integer()),
        sa.Column("source_columns", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("destination_columns", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("source_primary_key", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["plan_id"], ["migration_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "source_schema", "source_table", name="uq_plan_source_table"),
    )
    op.create_index("ix_migration_plan_tables_plan", "migration_plan_tables", ["plan_id"])

    op.create_table(
        "migration_column_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_table_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_column", sa.String(128), nullable=False),
        sa.Column("destination_column", sa.String(128)),
        sa.Column("source_type", sa.String(255), nullable=False),
        sa.Column("destination_type", sa.String(255)),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("compatible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("match_strategy", sa.String(30), nullable=False, server_default="unmapped"),
        sa.ForeignKeyConstraint(["plan_table_id"], ["migration_plan_tables.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_table_id", "source_column", name="uq_plan_source_column"),
    )
    op.create_index("ix_migration_column_mappings_table", "migration_column_mappings", ["plan_table_id"])


def downgrade() -> None:
    op.drop_index("ix_migration_column_mappings_table", table_name="migration_column_mappings")
    op.drop_table("migration_column_mappings")
    op.drop_index("ix_migration_plan_tables_plan", table_name="migration_plan_tables")
    op.drop_table("migration_plan_tables")
    op.drop_index("ix_migration_plans_project_owner", table_name="migration_plans")
    op.drop_table("migration_plans")
