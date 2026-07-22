"""triple barrier, meta labels and champion challenger roles

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    training_columns = _columns("ml_training_rows")
    for column in (
        sa.Column("target_triple_barrier", sa.Integer(), nullable=True),
        sa.Column("target_meta_label", sa.Integer(), nullable=True),
        sa.Column("triple_barrier_return_pct", sa.Float(), nullable=True),
        sa.Column("triple_barrier_hit", sa.String(16), nullable=True),
        sa.Column("meta_side", sa.Integer(), nullable=True),
        sa.Column("meta_strategy_return_pct", sa.Float(), nullable=True),
    ):
        if column.name not in training_columns:
            op.add_column("ml_training_rows", column)

    model_columns = _columns("ml_model_runs")
    if "deployment_role" not in model_columns:
        op.add_column(
            "ml_model_runs",
            sa.Column("deployment_role", sa.String(16), nullable=False, server_default="candidate"),
        )
        op.create_index("ix_ml_model_runs_deployment_role", "ml_model_runs", ["deployment_role"])
        op.get_bind().execute(sa.text(
            "UPDATE ml_model_runs SET deployment_role = CASE WHEN is_active THEN 'champion' ELSE 'archived' END"
        ))
    if "promotion_reason" not in model_columns:
        op.add_column("ml_model_runs", sa.Column("promotion_reason", sa.Text(), nullable=True))

    recommendation_columns = _columns("recommendation_records")
    if "meta_trade_probability" not in recommendation_columns:
        op.add_column("recommendation_records", sa.Column("meta_trade_probability", sa.Float(), nullable=True))
    if "meta_gate_applied" not in recommendation_columns:
        op.add_column(
            "recommendation_records",
            sa.Column("meta_gate_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    op.drop_column("recommendation_records", "meta_gate_applied")
    op.drop_column("recommendation_records", "meta_trade_probability")
    op.drop_column("ml_model_runs", "promotion_reason")
    op.drop_index("ix_ml_model_runs_deployment_role", table_name="ml_model_runs")
    op.drop_column("ml_model_runs", "deployment_role")
    for name in (
        "meta_strategy_return_pct", "meta_side", "triple_barrier_hit",
        "triple_barrier_return_pct", "target_meta_label", "target_triple_barrier",
    ):
        op.drop_column("ml_training_rows", name)
