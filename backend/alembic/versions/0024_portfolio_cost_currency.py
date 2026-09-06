"""portfolio cost currency

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "portfolio_positions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("portfolio_positions")}
    if "cost_currency" not in columns:
        # Existing rows remain NULL and are recognized as legacy source-currency costs.
        op.add_column(
            "portfolio_positions",
            sa.Column("cost_currency", sa.String(length=8), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "portfolio_positions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("portfolio_positions")}
    if "cost_currency" in columns:
        op.drop_column("portfolio_positions", "cost_currency")
