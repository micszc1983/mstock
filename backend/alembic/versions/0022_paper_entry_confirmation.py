"""confirmed paper-trading entries

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "paper_strategy_buckets" not in inspector.get_table_names():
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("paper_strategy_buckets")
    }
    if "pending_asset_id" not in columns:
        op.add_column(
            "paper_strategy_buckets",
            sa.Column("pending_asset_id", sa.String(64), nullable=True),
        )
        op.create_foreign_key(
            "fk_paper_strategy_buckets_pending_asset_id",
            "paper_strategy_buckets",
            "assets",
            ["pending_asset_id"],
            ["id"],
        )
        op.create_index(
            "ix_paper_strategy_buckets_pending_asset_id",
            "paper_strategy_buckets",
            ["pending_asset_id"],
        )
    if "pending_signal_count" not in columns:
        op.add_column(
            "paper_strategy_buckets",
            sa.Column(
                "pending_signal_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if "pending_since" not in columns:
        op.add_column(
            "paper_strategy_buckets",
            sa.Column("pending_since", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "paper_strategy_buckets" not in inspector.get_table_names():
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("paper_strategy_buckets")
    }
    indexes = {
        index.get("name")
        for index in inspector.get_indexes("paper_strategy_buckets")
    }
    foreign_keys = {
        foreign_key.get("name")
        for foreign_key in inspector.get_foreign_keys("paper_strategy_buckets")
    }
    if "ix_paper_strategy_buckets_pending_asset_id" in indexes:
        op.drop_index(
            "ix_paper_strategy_buckets_pending_asset_id",
            table_name="paper_strategy_buckets",
        )
    if "fk_paper_strategy_buckets_pending_asset_id" in foreign_keys:
        op.drop_constraint(
            "fk_paper_strategy_buckets_pending_asset_id",
            "paper_strategy_buckets",
            type_="foreignkey",
        )
    for name in ("pending_since", "pending_signal_count", "pending_asset_id"):
        if name in columns:
            op.drop_column("paper_strategy_buckets", name)
