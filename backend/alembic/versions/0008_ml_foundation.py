"""add ml foundation tables

Revision ID: 0008_ml_foundation
Revises: 0007_decision_support
Create Date: 2026-04-13 02:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_ml_foundation"
down_revision = "0007_decision_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_training_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_json", sa.Text(), nullable=False),
        sa.Column("target_up_1d", sa.Integer(), nullable=True),
        sa.Column("target_up_5d", sa.Integer(), nullable=True),
        sa.Column("target_up_20d", sa.Integer(), nullable=True),
        sa.Column("target_return_1d", sa.Float(), nullable=True),
        sa.Column("target_return_5d", sa.Float(), nullable=True),
        sa.Column("target_return_20d", sa.Float(), nullable=True),
        sa.Column("target_thesis_success", sa.Integer(), nullable=True),
    )
    op.create_index("ix_ml_training_rows_asset_id", "ml_training_rows", ["asset_id"])
    op.create_index("ix_ml_training_rows_snapshot_at", "ml_training_rows", ["snapshot_at"])

    op.create_table(
        "ml_model_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("target_name", sa.String(length=64), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dataset_rows", sa.Integer(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("model_path", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_ml_model_runs_model_name", "ml_model_runs", ["model_name"])
    op.create_index("ix_ml_model_runs_target_name", "ml_model_runs", ["target_name"])

    op.create_table(
        "ml_backtest_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_run_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_ml_backtest_results_model_run_id", "ml_backtest_results", ["model_run_id"])
    op.create_index("ix_ml_backtest_results_created_at", "ml_backtest_results", ["created_at"])

    op.create_table(
        "ml_predictions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_run_id", sa.Integer(), nullable=False),
        sa.Column("target_name", sa.String(length=64), nullable=False),
        sa.Column("probability_up", sa.Float(), nullable=False),
        sa.Column("predicted_label", sa.String(length=32), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_ml_predictions_asset_id", "ml_predictions", ["asset_id"])
    op.create_index("ix_ml_predictions_snapshot_at", "ml_predictions", ["snapshot_at"])
    op.create_index("ix_ml_predictions_model_run_id", "ml_predictions", ["model_run_id"])
    op.create_index("ix_ml_predictions_target_name", "ml_predictions", ["target_name"])

    op.create_table(
        "ml_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("setting_key", sa.String(length=128), nullable=False),
        sa.Column("setting_value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ml_settings_setting_key", "ml_settings", ["setting_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_ml_settings_setting_key", table_name="ml_settings")
    op.drop_table("ml_settings")

    op.drop_index("ix_ml_predictions_target_name", table_name="ml_predictions")
    op.drop_index("ix_ml_predictions_model_run_id", table_name="ml_predictions")
    op.drop_index("ix_ml_predictions_snapshot_at", table_name="ml_predictions")
    op.drop_index("ix_ml_predictions_asset_id", table_name="ml_predictions")
    op.drop_table("ml_predictions")

    op.drop_index("ix_ml_backtest_results_created_at", table_name="ml_backtest_results")
    op.drop_index("ix_ml_backtest_results_model_run_id", table_name="ml_backtest_results")
    op.drop_table("ml_backtest_results")

    op.drop_index("ix_ml_model_runs_target_name", table_name="ml_model_runs")
    op.drop_index("ix_ml_model_runs_model_name", table_name="ml_model_runs")
    op.drop_table("ml_model_runs")

    op.drop_index("ix_ml_training_rows_snapshot_at", table_name="ml_training_rows")
    op.drop_index("ix_ml_training_rows_asset_id", table_name="ml_training_rows")
    op.drop_table("ml_training_rows")
