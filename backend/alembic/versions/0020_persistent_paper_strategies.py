"""persistent automatic paper-trading strategies

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "paper_strategies" not in inspector.get_table_names():
        op.create_table(
            "paper_strategies",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("paper_accounts.id"), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_message", sa.Text(), nullable=False, server_default=""),
            sa.UniqueConstraint("account_id", name="uq_paper_strategy_account"),
        )
        op.create_index("ix_paper_strategies_account_id", "paper_strategies", ["account_id"])
        op.create_index("ix_paper_strategies_active", "paper_strategies", ["active"])

    inspector = sa.inspect(op.get_bind())
    if "paper_strategy_buckets" not in inspector.get_table_names():
        op.create_table(
            "paper_strategy_buckets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("strategy_id", sa.Integer(), sa.ForeignKey("paper_strategies.id"), nullable=False),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("initial_amount", sa.Float(), nullable=False),
            sa.Column("cash", sa.Float(), nullable=False),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("avg_price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("strategy_id", "ordinal", name="uq_paper_strategy_bucket_ordinal"),
        )
        op.create_index("ix_paper_strategy_buckets_strategy_id", "paper_strategy_buckets", ["strategy_id"])
        op.create_index("ix_paper_strategy_buckets_asset_id", "paper_strategy_buckets", ["asset_id"])


def downgrade() -> None:
    op.drop_table("paper_strategy_buckets")
    op.drop_table("paper_strategies")
