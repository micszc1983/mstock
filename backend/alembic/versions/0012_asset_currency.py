"""add currency column to assets

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("currency", sa.String(8), nullable=False, server_default="USD"))

    # Backfill: aktywa z .WA (GPW) → PLN, reszta pozostaje USD
    op.execute(
        "UPDATE assets SET currency = 'PLN' WHERE price_symbol LIKE '%.WA'"
    )


def downgrade() -> None:
    op.drop_column("assets", "currency")
