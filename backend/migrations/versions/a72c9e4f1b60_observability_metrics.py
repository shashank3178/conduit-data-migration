"""Persist database storage and batch telemetry metrics.

Revision ID: a72c9e4f1b60
Revises: f6a1b2c3d4e5
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a72c9e4f1b60"
down_revision: Union[str, None] = "f6a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("discovery_snapshots", sa.Column("database_size_bytes", sa.BigInteger(), nullable=False, server_default="0"))
    for name in ("total_size_bytes", "table_size_bytes", "index_size_bytes"):
        op.add_column("discovered_tables", sa.Column(name, sa.BigInteger(), nullable=False, server_default="0"))
    op.create_table(
        "migration_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("run_table_id", sa.Uuid(), nullable=False),
        sa.Column("batch_number", sa.Integer(), nullable=False),
        sa.Column("rows_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("committed_payload_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("throughput_bytes_per_second", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["migration_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_table_id"], ["migration_run_tables.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_migration_batches_run_table_number", "migration_batches", ["run_table_id", "batch_number"])
    op.create_index("ix_migration_batches_run_created", "migration_batches", ["run_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_migration_batches_run_created", table_name="migration_batches")
    op.drop_index("ix_migration_batches_run_table_number", table_name="migration_batches")
    op.drop_table("migration_batches")
    for name in ("index_size_bytes", "table_size_bytes", "total_size_bytes"):
        op.drop_column("discovered_tables", name)
    op.drop_column("discovery_snapshots", "database_size_bytes")
