"""merge observability and stage metrics migrations

Revision ID: 802dff8da6ed
Revises: a9d3c7e1f502, f7b8c9d0e1f2
Create Date: 2026-11-22 15:06:48.111321

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by other data.
revision: str = '802dff8da6ed'
down_revision: Union[str, None] = ('a9d3c7e1f502', 'f7b8c9d0e1f2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass