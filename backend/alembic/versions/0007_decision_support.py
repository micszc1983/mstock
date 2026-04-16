"""add decision support snapshots

Revision ID: 0007_decision_support
Revises: 0006_watchlists_reports_notifications
Create Date: 2026-04-13 01:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_decision_support"
down_revision = "0006_watchlists_reports_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conviction_score", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("timing_score", sa.Float(), nullable=False),
        sa.Column("setup_quality_score", sa.Float(), nullable=False),
        sa.Column("bullish_strength", sa.Float(), nullable=False),
        sa.Column("bearish_pressure", sa.Float(), nullable=False),
        sa.Column("net_thesis_edge", sa.Float(), nullable=False),
        sa.Column("action_label", sa.String(length=64), nullable=False),
        sa.Column("confidence_breakdown_json", sa.Text(), nullable=False),
        sa.Column("scenario_base_json", sa.Text(), nullable=False),
        sa.Column("scenario_bull_json", sa.Text(), nullable=False),
        sa.Column("scenario_bear_json", sa.Text(), nullable=False),
        sa.Column("change_summary_json", sa.Text(), nullable=False),
        sa.Column("position_sizing_json", sa.Text(), nullable=False),
        sa.Column("cross_asset_confirmation_json", sa.Text(), nullable=False),
        sa.Column("regime_memory_json", sa.Text(), nullable=False),
        sa.Column("macro_pressure_json", sa.Text(), nullable=True),
        sa.Column("relative_strength_json", sa.Text(), nullable=True),
        sa.Column("company_risk_stack_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_decision_snapshots_asset_id", "decision_snapshots", ["asset_id"])
    op.create_index("ix_decision_snapshots_snapshot_at", "decision_snapshots", ["snapshot_at"])
    op.create_index("ix_decision_snapshots_action_label", "decision_snapshots", ["action_label"])


def downgrade() -> None:
    op.drop_index("ix_decision_snapshots_action_label", table_name="decision_snapshots")
    op.drop_index("ix_decision_snapshots_snapshot_at", table_name="decision_snapshots")
    op.drop_index("ix_decision_snapshots_asset_id", table_name="decision_snapshots")
    op.drop_table("decision_snapshots")
