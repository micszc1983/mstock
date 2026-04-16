"""add nlp and alerts

Revision ID: 0005_nlp_and_alerts
Revises: 0004_thesis_outcomes
Create Date: 2026-04-13 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_nlp_and_alerts"
down_revision = "0004_thesis_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_nlp_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("news_id", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("sentiment_label", sa.String(length=32), nullable=False),
        sa.Column("sentiment_confidence", sa.Float(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("raw_output_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_news_nlp_runs_news_id", "news_nlp_runs", ["news_id"])
    op.create_index("ix_news_nlp_runs_model_name", "news_nlp_runs", ["model_name"])
    op.create_index("ix_news_nlp_runs_processed_at", "news_nlp_runs", ["processed_at"])

    op.create_table(
        "news_narrative_predictions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("news_id", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("narrative_label", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
    )
    op.create_index("ix_news_narrative_predictions_news_id", "news_narrative_predictions", ["news_id"])
    op.create_index("ix_news_narrative_predictions_model_name", "news_narrative_predictions", ["model_name"])
    op.create_index("ix_news_narrative_predictions_narrative_label", "news_narrative_predictions", ["narrative_label"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trigger_value", sa.Float(), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_alerts_asset_id", "alerts", ["asset_id"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])
    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_status", "alerts", ["status"])

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rule_name", sa.String(length=128), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("asset_scope", sa.String(length=128), nullable=False),
        sa.Column("threshold_json", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False),
    )
    op.create_index("ix_alert_rules_rule_name", "alert_rules", ["rule_name"])
    op.create_index("ix_alert_rules_alert_type", "alert_rules", ["alert_type"])
    op.create_index("ix_alert_rules_asset_scope", "alert_rules", ["asset_scope"])


def downgrade() -> None:
    op.drop_index("ix_alert_rules_asset_scope", table_name="alert_rules")
    op.drop_index("ix_alert_rules_alert_type", table_name="alert_rules")
    op.drop_index("ix_alert_rules_rule_name", table_name="alert_rules")
    op.drop_table("alert_rules")

    op.drop_index("ix_alerts_status", table_name="alerts")
    op.drop_index("ix_alerts_severity", table_name="alerts")
    op.drop_index("ix_alerts_alert_type", table_name="alerts")
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_index("ix_alerts_asset_id", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index("ix_news_narrative_predictions_narrative_label", table_name="news_narrative_predictions")
    op.drop_index("ix_news_narrative_predictions_model_name", table_name="news_narrative_predictions")
    op.drop_index("ix_news_narrative_predictions_news_id", table_name="news_narrative_predictions")
    op.drop_table("news_narrative_predictions")

    op.drop_index("ix_news_nlp_runs_processed_at", table_name="news_nlp_runs")
    op.drop_index("ix_news_nlp_runs_model_name", table_name="news_nlp_runs")
    op.drop_index("ix_news_nlp_runs_news_id", table_name="news_nlp_runs")
    op.drop_table("news_nlp_runs")
