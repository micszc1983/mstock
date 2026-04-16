"""add features and forecasts

Revision ID: 0002_features_and_forecasts
Revises: 0001_initial
Create Date: 2026-04-12 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_features_and_forecasts"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_asset_features",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_price", sa.Float(), nullable=False),
        sa.Column("price_change_1d_pct", sa.Float(), nullable=False),
        sa.Column("price_change_5d_pct", sa.Float(), nullable=False),
        sa.Column("price_change_20d_pct", sa.Float(), nullable=False),
        sa.Column("trend_score", sa.Float(), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("narrative_shift_score", sa.Float(), nullable=False),
        sa.Column("divergence_score", sa.Float(), nullable=False),
        sa.Column("fragility_score", sa.Float(), nullable=False),
        sa.Column("regime_label", sa.String(length=64), nullable=False),
        sa.Column("regime_confidence", sa.Float(), nullable=False),
        sa.Column("dominant_narrative", sa.String(length=64), nullable=True),
        sa.Column("volatility_10d", sa.Float(), nullable=False),
        sa.Column("momentum_20d", sa.Float(), nullable=False),
        sa.Column("news_count_7d", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_daily_asset_features_asset_id", "daily_asset_features", ["asset_id"])
    op.create_index("ix_daily_asset_features_snapshot_at", "daily_asset_features", ["snapshot_at"])

    op.create_table(
        "forecasts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("up_probability", sa.Float(), nullable=False),
        sa.Column("down_probability", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("expected_return_pct", sa.Float(), nullable=False),
        sa.Column("expected_range_low", sa.Float(), nullable=False),
        sa.Column("expected_range_high", sa.Float(), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("regime_label", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_forecasts_asset_id", "forecasts", ["asset_id"])
    op.create_index("ix_forecasts_generated_at", "forecasts", ["generated_at"])
    op.create_index("ix_forecasts_horizon", "forecasts", ["horizon"])
    op.create_index("ix_forecasts_regime_label", "forecasts", ["regime_label"])


def downgrade() -> None:
    op.drop_index("ix_forecasts_regime_label", table_name="forecasts")
    op.drop_index("ix_forecasts_horizon", table_name="forecasts")
    op.drop_index("ix_forecasts_generated_at", table_name="forecasts")
    op.drop_index("ix_forecasts_asset_id", table_name="forecasts")
    op.drop_table("forecasts")

    op.drop_index("ix_daily_asset_features_snapshot_at", table_name="daily_asset_features")
    op.drop_index("ix_daily_asset_features_asset_id", table_name="daily_asset_features")
    op.drop_table("daily_asset_features")
