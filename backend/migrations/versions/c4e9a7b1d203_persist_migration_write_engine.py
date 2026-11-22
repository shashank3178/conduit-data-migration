"""Persist the selected PostgreSQL row-write engine on each run.

Revision ID: c4e9a7b1d203
Revises: 802dff8da6ed
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4e9a7b1d203"
down_revision: Union[str, None] = "802dff8da6ed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "migration_runs",
        sa.Column("write_engine", sa.String(length=20), nullable=False, server_default="VALUES"),
    )


def downgrade() -> None:
    op.drop_column("migration_runs", "write_engine")
