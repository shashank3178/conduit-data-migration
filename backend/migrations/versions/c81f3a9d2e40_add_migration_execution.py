"""add migration run and per-table execution progress

Revision ID: c81f3a9d2e40
Revises: b7a4c2d9e610
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c81f3a9d2e40"
down_revision: Union[str, None] = "b7a4c2d9e610"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("migration_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("total_tables", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_tables", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("migrated_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["migration_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_migration_runs_project_owner", "migration_runs", ["project_id", "owner_id"])
    op.create_table("migration_run_tables",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_table_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_schema", sa.String(128), nullable=False),
        sa.Column("source_table", sa.String(128), nullable=False),
        sa.Column("destination_schema", sa.String(128), nullable=False),
        sa.Column("destination_table", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("migrated_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_table_id"], ["migration_plan_tables.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_migration_run_tables_run", "migration_run_tables", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_migration_run_tables_run", table_name="migration_run_tables")
    op.drop_table("migration_run_tables")
    op.drop_index("ix_migration_runs_project_owner", table_name="migration_runs")
    op.drop_table("migration_runs")
