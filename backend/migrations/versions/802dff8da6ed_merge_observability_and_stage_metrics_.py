"""merge observability and stage metrics migrations

Revision ID: 802dff8da6ed
Revises: a9d3c7e1f502, f7b8c9d0e1f2
Create Date: 2026-11-22 15:06:48.111321

"""
from collections.abc import Sequence

# revision identifiers, used by other data.
revision: str = '802dff8da6ed'
down_revision: str | None = ('a9d3c7e1f502', 'f7b8c9d0e1f2')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass