"""add heuristic vs ml comparisons

Revision ID: 0009_evaluation_comparison
Revises: 0008_ml_foundation
Create Date: 2026-04-13 03:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_evaluation_comparison"
down_revision = "0008_ml_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "heuristic_vs_ml_comparisons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heuristic_accuracy_5d", sa.Float(), nullable=False),
        sa.Column("ml_accuracy_5d", sa.Float(), nullable=False),
        sa.Column("heuristic_avg_return_5d", sa.Float(), nullable=False),
        sa.Column("ml_avg_return_5d", sa.Float(), nullable=False),
        sa.Column("better_mode", sa.String(length=32), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
    )
    op.create_index("ix_heuristic_vs_ml_comparisons_asset_id", "heuristic_vs_ml_comparisons", ["asset_id"])
    op.create_index("ix_heuristic_vs_ml_comparisons_created_at", "heuristic_vs_ml_comparisons", ["created_at"])
    op.create_index("ix_heuristic_vs_ml_comparisons_better_mode", "heuristic_vs_ml_comparisons", ["better_mode"])


def downgrade() -> None:
    op.drop_index("ix_heuristic_vs_ml_comparisons_better_mode", table_name="heuristic_vs_ml_comparisons")
    op.drop_index("ix_heuristic_vs_ml_comparisons_created_at", table_name="heuristic_vs_ml_comparisons")
    op.drop_index("ix_heuristic_vs_ml_comparisons_asset_id", table_name="heuristic_vs_ml_comparisons")
    op.drop_table("heuristic_vs_ml_comparisons")
