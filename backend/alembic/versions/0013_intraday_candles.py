"""add intraday_candles table

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intraday_candles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("resolution", sa.String(8), nullable=False, index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("rsi", sa.Float(), nullable=True),
        sa.Column("ema9", sa.Float(), nullable=True),
        sa.Column("ema20", sa.Float(), nullable=True),
        sa.Column("macd", sa.Float(), nullable=True),
        sa.Column("macd_signal", sa.Float(), nullable=True),
        sa.Column("bb_upper", sa.Float(), nullable=True),
        sa.Column("bb_lower", sa.Float(), nullable=True),
        sa.Column("volume_ratio", sa.Float(), nullable=True),
        sa.UniqueConstraint("asset_id", "resolution", "timestamp", name="uq_intraday_candle"),
    )


def downgrade() -> None:
    op.drop_table("intraday_candles")