"""Durable metrics, database measurements, and worker ownership.

Revision ID: a9d3c7e1f502
Revises: f6a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a9d3c7e1f502"
down_revision: Union[str, None] = "f6a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("migration_runs", sa.Column("worker_id", sa.String(128), nullable=True))
    op.create_index("ix_migration_runs_worker_status", "migration_runs", ["worker_id", "status"])

    op.create_table(
        "migration_run_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("migration_runs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("rows_fetched", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("rows_committed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("batches_committed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("logical_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("processing_duration_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rows_per_second", sa.Float(), nullable=False, server_default="0"),
        sa.Column("logical_bytes_per_second", sa.Float(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_migration_run_metrics_updated", "migration_run_metrics", ["updated_at"])

    op.create_table(
        "migration_batch_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("migration_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_table_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("migration_run_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_key", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("rows_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("logical_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("checkpoint_start", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("checkpoint_end", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("run_id", "batch_key", name="uq_migration_batch_run_key"),
    )
    op.create_index("ix_migration_batch_run_sequence", "migration_batch_metrics", ["run_id", "sequence"])
    op.create_index("ix_migration_batch_table_created", "migration_batch_metrics", ["run_table_id", "created_at"])

    op.create_table(
        "migration_table_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("migration_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_table_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("migration_run_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rows_fetched", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("rows_committed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("batches_committed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("logical_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("source_physical_bytes", sa.BigInteger()),
        sa.Column("destination_physical_bytes", sa.BigInteger()),
        sa.Column("storage_measured_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_table_id", name="uq_migration_table_metric_run_table"),
    )

    op.create_table(
        "migration_database_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("migration_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("database_name", sa.String(128), nullable=False),
        sa.Column("physical_bytes", sa.BigInteger(), nullable=False),
        sa.Column("measurement_kind", sa.String(20), nullable=False, server_default="exact"),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_migration_database_metrics_run_role_time", "migration_database_metrics", ["run_id", "role", "captured_at"])


def downgrade() -> None:
    op.drop_index("ix_migration_database_metrics_run_role_time", table_name="migration_database_metrics")
    op.drop_table("migration_database_metrics")
    op.drop_table("migration_table_metrics")
    op.drop_index("ix_migration_batch_table_created", table_name="migration_batch_metrics")
    op.drop_index("ix_migration_batch_run_sequence", table_name="migration_batch_metrics")
    op.drop_table("migration_batch_metrics")
    op.drop_index("ix_migration_run_metrics_updated", table_name="migration_run_metrics")
    op.drop_table("migration_run_metrics")
    op.drop_index("ix_migration_runs_worker_status", table_name="migration_runs")
    op.drop_column("migration_runs", "worker_id")
