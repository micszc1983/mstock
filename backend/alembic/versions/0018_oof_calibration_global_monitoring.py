"""OOF meta features, calibrated market models and monitoring

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    training = _columns("ml_training_rows")
    for column in (
        sa.Column("market_segment", sa.String(16), nullable=True),
        sa.Column("market_regime", sa.String(64), nullable=True),
        sa.Column("meta_primary_probability", sa.Float(), nullable=True),
        sa.Column("meta_primary_margin", sa.Float(), nullable=True),
        sa.Column("meta_model_disagreement", sa.Float(), nullable=True),
        sa.Column("meta_label_source", sa.String(32), nullable=True),
    ):
        if column.name not in training:
            op.add_column("ml_training_rows", column)
    training_indexes = _indexes("ml_training_rows")
    if "ix_ml_training_rows_market_segment" not in training_indexes:
        op.create_index("ix_ml_training_rows_market_segment", "ml_training_rows", ["market_segment"])
    if "ix_ml_training_rows_market_regime" not in training_indexes:
        op.create_index("ix_ml_training_rows_market_regime", "ml_training_rows", ["market_regime"])

    model_runs = _columns("ml_model_runs")
    if "market_segment" not in model_runs:
        op.add_column("ml_model_runs", sa.Column("market_segment", sa.String(16), nullable=True))
        op.create_index("ix_ml_model_runs_market_segment", "ml_model_runs", ["market_segment"])

    recommendation = _columns("recommendation_records")
    if "meta_trade_threshold" not in recommendation:
        op.add_column("recommendation_records", sa.Column("meta_trade_threshold", sa.Float(), nullable=True))
    if "meta_threshold_scope" not in recommendation:
        op.add_column("recommendation_records", sa.Column("meta_threshold_scope", sa.String(32), nullable=True))

    inspector = sa.inspect(op.get_bind())
    if "ml_model_monitors" not in inspector.get_table_names():
        op.create_table(
            "ml_model_monitors",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("model_run_id", sa.Integer(), sa.ForeignKey("ml_model_runs.id"), nullable=False),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("asset_id", sa.String(64), nullable=True),
            sa.Column("market_segment", sa.String(16), nullable=True),
            sa.Column("feature_psi", sa.Float(), nullable=True),
            sa.Column("calibration_error", sa.Float(), nullable=True),
            sa.Column("recent_avg_net_return_pct", sa.Float(), nullable=True),
            sa.Column("recent_profit_factor", sa.Float(), nullable=True),
            sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_degraded", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("action", sa.String(32), nullable=False, server_default="keep"),
            sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        )
    monitor_indexes = _indexes("ml_model_monitors")
    for name in ("model_run_id", "checked_at", "asset_id", "market_segment", "is_degraded", "action"):
        index_name = f"ix_ml_model_monitors_{name}"
        if index_name not in monitor_indexes:
            op.create_index(index_name, "ml_model_monitors", [name])


def downgrade() -> None:
    op.drop_table("ml_model_monitors")
    op.drop_column("recommendation_records", "meta_threshold_scope")
    op.drop_column("recommendation_records", "meta_trade_threshold")
    op.drop_index("ix_ml_model_runs_market_segment", table_name="ml_model_runs")
    op.drop_column("ml_model_runs", "market_segment")
    op.drop_index("ix_ml_training_rows_market_regime", table_name="ml_training_rows")
    op.drop_index("ix_ml_training_rows_market_segment", table_name="ml_training_rows")
    for name in (
        "meta_label_source", "meta_model_disagreement", "meta_primary_margin",
        "meta_primary_probability", "market_regime", "market_segment",
    ):
        op.drop_column("ml_training_rows", name)
