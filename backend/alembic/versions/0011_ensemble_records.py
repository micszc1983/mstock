"""add ensemble_records table

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ensemble_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("mode", sa.String(32), nullable=False, index=True),
        sa.Column("heuristic_direction", sa.String(16), nullable=True),
        sa.Column("ml_direction", sa.String(16), nullable=True),
        sa.Column("ensemble_direction", sa.String(16), nullable=True),
        sa.Column("heuristic_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ml_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ensemble_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("actual_return_5d", sa.Float(), nullable=True),
        sa.Column("heuristic_correct", sa.Boolean(), nullable=True),
        sa.Column("ml_correct", sa.Boolean(), nullable=True),
        sa.Column("ensemble_correct", sa.Boolean(), nullable=True),
        sa.Column("winner", sa.String(16), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("ensemble_records")
