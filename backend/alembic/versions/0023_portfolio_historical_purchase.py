"""historical portfolio purchases

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "portfolio_positions" not in inspector.get_table_names():
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("portfolio_positions")
    }
    if "purchase_date" not in columns:
        op.add_column(
            "portfolio_positions",
            sa.Column("purchase_date", sa.Date(), nullable=True),
        )
    if "invested_amount" not in columns:
        op.add_column(
            "portfolio_positions",
            sa.Column("invested_amount", sa.Float(), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "portfolio_positions" not in inspector.get_table_names():
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("portfolio_positions")
    }
    if "invested_amount" in columns:
        op.drop_column("portfolio_positions", "invested_amount")
    if "purchase_date" in columns:
        op.drop_column("portfolio_positions", "purchase_date")
