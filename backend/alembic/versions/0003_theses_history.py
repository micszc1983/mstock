"""add theses history

Revision ID: 0003_theses_history
Revises: 0002_features_and_forecasts
Create Date: 2026-04-12 00:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_theses_history"
down_revision = "0002_features_and_forecasts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "theses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("regime", sa.String(length=64), nullable=False),
        sa.Column("regime_confidence", sa.Float(), nullable=False),
        sa.Column("dominant_narrative", sa.String(length=64), nullable=True),
        sa.Column("thesis_confidence", sa.Float(), nullable=False),
        sa.Column("fragility_score", sa.Float(), nullable=False),
        sa.Column("divergence_score", sa.Float(), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("anti_thesis", sa.Text(), nullable=False),
        sa.Column("support_factors_json", sa.Text(), nullable=False),
        sa.Column("risk_factors_json", sa.Text(), nullable=False),
        sa.Column("invalidation_conditions_json", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False, server_default="thesis_v1"),
    )
    op.create_index("ix_theses_asset_id", "theses", ["asset_id"])
    op.create_index("ix_theses_generated_at", "theses", ["generated_at"])
    op.create_index("ix_theses_source_snapshot_at", "theses", ["source_snapshot_at"])
    op.create_index("ix_theses_regime", "theses", ["regime"])


def downgrade() -> None:
    op.drop_index("ix_theses_regime", table_name="theses")
    op.drop_index("ix_theses_source_snapshot_at", table_name="theses")
    op.drop_index("ix_theses_generated_at", table_name="theses")
    op.drop_index("ix_theses_asset_id", table_name="theses")
    op.drop_table("theses")
