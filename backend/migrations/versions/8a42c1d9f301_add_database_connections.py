"""add encrypted PostgreSQL connection records

Revision ID: 8a42c1d9f301
Revises: 3eb20b475e6f
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8a42c1d9f301"
down_revision: str | None = "3eb20b475e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "database_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("database", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_encrypted", sa.String(length=2048), nullable=False),
        sa.Column("sslmode", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('source', 'destination')", name="ck_connection_role"),
        sa.CheckConstraint(
            "sslmode IN ('disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full')",
            name="ck_connection_sslmode",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_connections_project_owner",
        "database_connections",
        ["project_id", "owner_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_connections_project_owner", table_name="database_connections")
    op.drop_table("database_connections")
