"""recommendation journal and walk-forward audits

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "recommendation_records" not in tables:
        op.create_table(
            "recommendation_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
            sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("model_version", sa.String(32), nullable=False, index=True),
            sa.Column("market", sa.String(16), nullable=False, index=True),
            sa.Column("regime", sa.String(64), nullable=False, index=True),
            sa.Column("action", sa.String(16), nullable=False, index=True),
            sa.Column("displayed_action", sa.String(32), nullable=False, index=True),
            sa.Column("has_position", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("calibration_scope", sa.String(32), nullable=False),
            sa.Column("calibration_sample_size", sa.Integer(), nullable=False),
            sa.Column("composite_score", sa.Float(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("probability_buy", sa.Float(), nullable=False),
            sa.Column("probability_sell", sa.Float(), nullable=False),
            sa.Column("probability_no_trade", sa.Float(), nullable=False),
            sa.Column("buy_threshold", sa.Float(), nullable=False),
            sa.Column("sell_threshold", sa.Float(), nullable=False),
            sa.Column("transaction_cost_pct", sa.Float(), nullable=False),
            sa.Column("expected_gross_edge_pct", sa.Float(), nullable=False),
            sa.Column("expected_net_edge_pct", sa.Float(), nullable=False),
            sa.Column("uncertainty_pct", sa.Float(), nullable=False),
            sa.Column("base_price", sa.Float()),
            sa.Column("quality_flag", sa.String(64), index=True),
            sa.Column("realized_return_1d_pct", sa.Float()),
            sa.Column("realized_return_5d_pct", sa.Float()),
            sa.Column("realized_return_20d_pct", sa.Float()),
            sa.Column("strategy_net_return_1d_pct", sa.Float()),
            sa.Column("strategy_net_return_5d_pct", sa.Float()),
            sa.Column("strategy_net_return_20d_pct", sa.Float()),
            sa.Column("evaluated_at", sa.DateTime(timezone=True), index=True),
            sa.UniqueConstraint(
                "asset_id", "snapshot_at", "model_version",
                name="uq_recommendation_record_snapshot",
            ),
        )
    if "recommendation_audit_runs" not in tables:
        op.create_table(
            "recommendation_audit_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("model_version", sa.String(32), nullable=False, index=True),
            sa.Column("dataset_rows", sa.Integer(), nullable=False),
            sa.Column("eligible_rows", sa.Integer(), nullable=False),
            sa.Column("excluded_outliers", sa.Integer(), nullable=False),
            sa.Column("fold_count", sa.Integer(), nullable=False),
            sa.Column("embargo_sessions", sa.Integer(), nullable=False),
            sa.Column("result_json", sa.Text(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("recommendation_audit_runs")
    op.drop_table("recommendation_records")
