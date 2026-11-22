"""Add detailed batch stage and database network latency metrics.

Revision ID: f7b8c9d0e1f2
Revises: f6a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("migration_run_metrics", sa.Column("source_fetch_duration_ms", sa.Float(), nullable=False, server_default="0"))
    op.add_column("migration_run_metrics", sa.Column("destination_write_duration_ms", sa.Float(), nullable=False, server_default="0"))
    op.add_column("migration_run_metrics", sa.Column("source_network_rtt_ms", sa.Float(), nullable=True))
    op.add_column("migration_run_metrics", sa.Column("destination_network_rtt_ms", sa.Float(), nullable=True))
    op.add_column("migration_batch_metrics", sa.Column("source_fetch_duration_ms", sa.Float(), nullable=False, server_default="0"))
    op.add_column("migration_batch_metrics", sa.Column("destination_write_duration_ms", sa.Float(), nullable=False, server_default="0"))
    op.add_column("migration_batch_metrics", sa.Column("network_rtt_ms", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("migration_batch_metrics", "network_rtt_ms")
    op.drop_column("migration_batch_metrics", "destination_write_duration_ms")
    op.drop_column("migration_batch_metrics", "source_fetch_duration_ms")
    op.drop_column("migration_run_metrics", "destination_network_rtt_ms")
    op.drop_column("migration_run_metrics", "source_network_rtt_ms")
    op.drop_column("migration_run_metrics", "destination_write_duration_ms")
    op.drop_column("migration_run_metrics", "source_fetch_duration_ms")
