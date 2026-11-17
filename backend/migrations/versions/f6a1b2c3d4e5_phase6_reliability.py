"""Phase 6 execution accounting, resumable keyset checkpoints and row errors.

Revision ID: f6a1b2c3d4e5
Revises: c81f3a9d2e40
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f6a1b2c3d4e5"
down_revision: Union[str, None] = "c81f3a9d2e40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("migration_runs", sa.Column("write_strategy", sa.String(20), nullable=False, server_default="INSERT_ONLY"))
    op.add_column("migration_runs", sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"))
    for name in ("inserted_rows", "updated_rows", "skipped_rows"):
        op.add_column("migration_runs", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("migration_runs", sa.Column("validation_status", sa.String(24), nullable=False, server_default="pending"))
    op.add_column("migration_runs", sa.Column("mismatch_rows", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("migration_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))

    for name in ("inserted_rows", "updated_rows", "skipped_rows"):
        op.add_column("migration_run_tables", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("migration_run_tables", sa.Column("last_key", postgresql.JSONB(astext_type=sa.Text())))
    op.add_column("migration_run_tables", sa.Column("upper_key", postgresql.JSONB(astext_type=sa.Text())))
    op.add_column("migration_run_tables", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("migration_run_tables", sa.Column("validation_status", sa.String(24), nullable=False, server_default="pending"))
    op.add_column("migration_run_tables", sa.Column("mismatch_rows", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "migration_row_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_table_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_key", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_type", sa.String(120), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_table_id"], ["migration_run_tables.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_migration_row_errors_run", "migration_row_errors", ["run_id"])
    op.create_index("ix_migration_row_errors_table", "migration_row_errors", ["run_table_id"])
    op.create_table(
        "migration_run_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_table_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("CAST('{}' AS jsonb)")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_table_id"], ["migration_run_tables.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_migration_run_events_run_created", "migration_run_events", ["run_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_migration_run_events_run_created", table_name="migration_run_events")
    op.drop_table("migration_run_events")
    op.drop_index("ix_migration_row_errors_table", table_name="migration_row_errors")
    op.drop_index("ix_migration_row_errors_run", table_name="migration_row_errors")
    op.drop_table("migration_row_errors")
    for name in ("mismatch_rows", "validation_status", "retry_count", "upper_key", "last_key",
                 "skipped_rows", "updated_rows", "inserted_rows"):
        op.drop_column("migration_run_tables", name)
    for name in ("heartbeat_at", "mismatch_rows", "validation_status", "skipped_rows",
                 "updated_rows", "inserted_rows", "max_retries", "write_strategy"):
        op.drop_column("migration_runs", name)
