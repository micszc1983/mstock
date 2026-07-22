"""paper trading and backtest portfolio metrics

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    cols = {c["name"] for c in inspector.get_columns("intraday_backtests")}
    if "initial_capital" not in cols:
        op.add_column("intraday_backtests", sa.Column("initial_capital", sa.Float(), nullable=False, server_default="10000"))
    if "metrics_json" not in cols:
        op.add_column("intraday_backtests", sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"))

    if "paper_accounts" not in tables:
        op.create_table("paper_accounts",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(128), nullable=False, unique=True),
            sa.Column("currency", sa.String(8), nullable=False), sa.Column("initial_cash", sa.Float(), nullable=False),
            sa.Column("cash", sa.Float(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    if "paper_positions" not in tables:
        op.create_table("paper_positions",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("account_id", sa.Integer(), sa.ForeignKey("paper_accounts.id"), nullable=False, index=True),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
            sa.Column("quantity", sa.Float(), nullable=False), sa.Column("avg_price", sa.Float(), nullable=False),
            sa.Column("realized_pnl", sa.Float(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("account_id", "asset_id", name="uq_paper_position"))
    if "paper_orders" not in tables:
        op.create_table("paper_orders",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("account_id", sa.Integer(), sa.ForeignKey("paper_accounts.id"), nullable=False, index=True),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
            sa.Column("side", sa.String(8), nullable=False, index=True), sa.Column("order_type", sa.String(16), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False), sa.Column("status", sa.String(16), nullable=False, index=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, index=True), sa.Column("filled_at", sa.DateTime(timezone=True)),
            sa.Column("reference_price", sa.Float()), sa.Column("fill_price", sa.Float()),
            sa.Column("commission", sa.Float(), nullable=False), sa.Column("slippage", sa.Float(), nullable=False), sa.Column("note", sa.Text(), nullable=False))
    if "paper_trades" not in tables:
        op.create_table("paper_trades",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("order_id", sa.Integer(), sa.ForeignKey("paper_orders.id"), nullable=False, unique=True, index=True),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("paper_accounts.id"), nullable=False, index=True),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
            sa.Column("side", sa.String(8), nullable=False), sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("price", sa.Float(), nullable=False), sa.Column("gross_value", sa.Float(), nullable=False),
            sa.Column("costs", sa.Float(), nullable=False), sa.Column("realized_pnl", sa.Float(), nullable=False),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False, index=True))


def downgrade() -> None:
    for table in ("paper_trades", "paper_orders", "paper_positions", "paper_accounts"):
        op.drop_table(table)
