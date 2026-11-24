"""Persist PostgreSQL write engine selection."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e9a7b1d203"
down_revision: str | None = "802dff8da6ed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "migration_runs",
        sa.Column(
            "write_engine",
            sa.String(length=20),
            nullable=False,
            server_default="VALUES",
        ),
    )


def downgrade() -> None:
    op.drop_column("migration_runs", "write_engine")
