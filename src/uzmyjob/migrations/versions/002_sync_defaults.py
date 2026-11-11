"""Ensure users.telegram_id is BigInteger and sources.error_count has server_default.

Revision ID: 002_sync_defaults
Revises: 001_initial
Create Date: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op

revision = "002_sync_defaults"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "users",
            "telegram_id",
            existing_type=sa.BigInteger(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )
        op.alter_column(
            "sources",
            "error_count",
            existing_type=sa.Integer(),
            server_default="0",
            existing_nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "sources",
            "error_count",
            existing_type=sa.Integer(),
            server_default=None,
            existing_nullable=True,
        )
