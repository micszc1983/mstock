"""add thesis outcomes

Revision ID: 0004_thesis_outcomes
Revises: 0003_theses_history
Create Date: 2026-04-12 00:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_thesis_outcomes"
down_revision = "0003_theses_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thesis_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("thesis_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.String(length=16), nullable=False),
        sa.Column("base_price", sa.Float(), nullable=False),
        sa.Column("realized_price", sa.Float(), nullable=False),
        sa.Column("realized_return_pct", sa.Float(), nullable=False),
        sa.Column("was_directionally_correct", sa.Boolean(), nullable=False),
        sa.Column("outcome_label", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_thesis_outcomes_thesis_id", "thesis_outcomes", ["thesis_id"])
    op.create_index("ix_thesis_outcomes_asset_id", "thesis_outcomes", ["asset_id"])
    op.create_index("ix_thesis_outcomes_evaluated_at", "thesis_outcomes", ["evaluated_at"])
    op.create_index("ix_thesis_outcomes_horizon", "thesis_outcomes", ["horizon"])
    op.create_index("ix_thesis_outcomes_outcome_label", "thesis_outcomes", ["outcome_label"])


def downgrade() -> None:
    op.drop_index("ix_thesis_outcomes_outcome_label", table_name="thesis_outcomes")
    op.drop_index("ix_thesis_outcomes_horizon", table_name="thesis_outcomes")
    op.drop_index("ix_thesis_outcomes_evaluated_at", table_name="thesis_outcomes")
    op.drop_index("ix_thesis_outcomes_asset_id", table_name="thesis_outcomes")
    op.drop_index("ix_thesis_outcomes_thesis_id", table_name="thesis_outcomes")
    op.drop_table("thesis_outcomes")
