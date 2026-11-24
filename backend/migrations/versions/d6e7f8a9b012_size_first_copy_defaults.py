"""Persist physical relation sizes and make COPY the default writer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b012"
down_revision: str | None = "c4e9a7b1d203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "discovered_tables",
        sa.Column("estimated_size_bytes", sa.BigInteger(), nullable=True),
    )

    op.add_column(
        "migration_plan_tables",
        sa.Column("source_size_bytes", sa.BigInteger(), nullable=True),
    )

    op.alter_column(
        "migration_runs",
        "write_engine",
        existing_type=sa.String(length=20),
        server_default="COPY",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "migration_runs",
        "write_engine",
        existing_type=sa.String(length=20),
        server_default="VALUES",
        existing_nullable=False,
    )

    op.drop_column("migration_plan_tables", "source_size_bytes")
    op.drop_column("discovered_tables", "estimated_size_bytes")
