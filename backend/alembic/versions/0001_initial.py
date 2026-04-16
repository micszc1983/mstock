"""initial schema

Revision ID: 0001_initial
Revises: None
Create Date: 2026-04-12 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_index("ix_assets_symbol", "assets", ["symbol"])
    op.create_index("ix_assets_type", "assets", ["type"])

    op.create_table(
        "price_points",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
    )
    op.create_index("ix_price_points_asset_id", "price_points", ["asset_id"])
    op.create_index("ix_price_points_timestamp", "price_points", ["timestamp"])

    op.create_table(
        "news_items",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("impact_score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
    )
    op.create_index("ix_news_items_asset_id", "news_items", ["asset_id"])
    op.create_index("ix_news_items_published_at", "news_items", ["published_at"])

    op.create_table(
        "news_narratives",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("news_id", sa.String(length=128), nullable=False),
        sa.Column("narrative_label", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["news_id"], ["news_items.id"]),
    )
    op.create_index("ix_news_narratives_news_id", "news_narratives", ["news_id"])
    op.create_index("ix_news_narratives_narrative_label", "news_narratives", ["narrative_label"])

    op.create_table(
        "sync_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("sync_type", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sync_logs_asset_id", "sync_logs", ["asset_id"])
    op.create_index("ix_sync_logs_sync_type", "sync_logs", ["sync_type"])
    op.create_index("ix_sync_logs_status", "sync_logs", ["status"])
    op.create_index("ix_sync_logs_created_at", "sync_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sync_logs_created_at", table_name="sync_logs")
    op.drop_index("ix_sync_logs_status", table_name="sync_logs")
    op.drop_index("ix_sync_logs_sync_type", table_name="sync_logs")
    op.drop_index("ix_sync_logs_asset_id", table_name="sync_logs")
    op.drop_table("sync_logs")

    op.drop_index("ix_news_narratives_narrative_label", table_name="news_narratives")
    op.drop_index("ix_news_narratives_news_id", table_name="news_narratives")
    op.drop_table("news_narratives")

    op.drop_index("ix_news_items_published_at", table_name="news_items")
    op.drop_index("ix_news_items_asset_id", table_name="news_items")
    op.drop_table("news_items")

    op.drop_index("ix_price_points_timestamp", table_name="price_points")
    op.drop_index("ix_price_points_asset_id", table_name="price_points")
    op.drop_table("price_points")

    op.drop_index("ix_assets_type", table_name="assets")
    op.drop_index("ix_assets_symbol", table_name="assets")
    op.drop_table("assets")
