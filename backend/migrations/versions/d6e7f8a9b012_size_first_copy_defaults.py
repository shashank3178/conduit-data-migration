"""Persist physical relation sizes and make COPY the default writer."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d6e7f8a9b012"
down_revision: Union[str, None] = "c4e9a7b1d203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("discovered_tables", sa.Column("estimated_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("migration_plan_tables", sa.Column("source_size_bytes", sa.BigInteger(), nullable=True))
    op.alter_column("migration_runs", "write_engine", existing_type=sa.String(length=20), server_default="COPY")


def downgrade() -> None:
    op.alter_column("migration_runs", "write_engine", existing_type=sa.String(length=20), server_default="VALUES")
    op.drop_column("migration_plan_tables", "source_size_bytes")
    op.drop_column("discovered_tables", "estimated_size_bytes")
