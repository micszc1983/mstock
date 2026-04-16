"""add watchlists preferences reports notifications

Revision ID: 0006_watchlists_reports_notifications
Revises: 0005_nlp_and_alerts
Create Date: 2026-04-13 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_watchlists_reports_notifications"
down_revision = "0005_nlp_and_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_watchlists_name", "watchlists", ["name"])

    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("watchlist_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_watchlist_items_watchlist_id", "watchlist_items", ["watchlist_id"])
    op.create_index("ix_watchlist_items_asset_id", "watchlist_items", ["asset_id"])

    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("preference_key", sa.String(length=128), nullable=False),
        sa.Column("preference_value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_preferences_preference_key", "user_preferences", ["preference_key"], unique=True)

    op.create_table(
        "notification_channels",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notification_channels_channel_type", "notification_channels", ["channel_type"])
    op.create_index("ix_notification_channels_target", "notification_channels", ["target"])

    op.create_table(
        "notification_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notification_events_channel_id", "notification_events", ["channel_id"])
    op.create_index("ix_notification_events_asset_id", "notification_events", ["asset_id"])
    op.create_index("ix_notification_events_event_type", "notification_events", ["event_type"])
    op.create_index("ix_notification_events_status", "notification_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_notification_events_status", table_name="notification_events")
    op.drop_index("ix_notification_events_event_type", table_name="notification_events")
    op.drop_index("ix_notification_events_asset_id", table_name="notification_events")
    op.drop_index("ix_notification_events_channel_id", table_name="notification_events")
    op.drop_table("notification_events")

    op.drop_index("ix_notification_channels_target", table_name="notification_channels")
    op.drop_index("ix_notification_channels_channel_type", table_name="notification_channels")
    op.drop_table("notification_channels")

    op.drop_index("ix_user_preferences_preference_key", table_name="user_preferences")
    op.drop_table("user_preferences")

    op.drop_index("ix_watchlist_items_asset_id", table_name="watchlist_items")
    op.drop_index("ix_watchlist_items_watchlist_id", table_name="watchlist_items")
    op.drop_table("watchlist_items")

    op.drop_index("ix_watchlists_name", table_name="watchlists")
    op.drop_table("watchlists")
