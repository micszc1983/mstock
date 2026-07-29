"""versioned recommendation journal

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "recommendation_records" not in inspector.get_table_names():
        return

    columns = _columns("recommendation_records")
    additions = (
        ("revision", sa.Column("revision", sa.Integer(), nullable=False, server_default="1")),
        ("previous_record_id", sa.Column("previous_record_id", sa.Integer(), nullable=True)),
        ("decision_signature", sa.Column("decision_signature", sa.String(64), nullable=False, server_default="")),
        ("change_type", sa.Column("change_type", sa.String(32), nullable=False, server_default="initial")),
        ("change_summary", sa.Column("change_summary", sa.Text(), nullable=True)),
        ("change_details_json", sa.Column("change_details_json", sa.Text(), nullable=False, server_default="{}")),
        ("signal_snapshot_json", sa.Column("signal_snapshot_json", sa.Text(), nullable=False, server_default="{}")),
        ("no_trade_reason", sa.Column("no_trade_reason", sa.Text(), nullable=True)),
        ("rationale", sa.Column("rationale", sa.Text(), nullable=True)),
        ("data_complete", sa.Column("data_complete", sa.Boolean(), nullable=False, server_default=sa.true())),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("recommendation_records", column)

    inspector = sa.inspect(op.get_bind())
    unique_names = {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints("recommendation_records")
    }
    if "uq_recommendation_record_snapshot" in unique_names:
        op.drop_constraint(
            "uq_recommendation_record_snapshot",
            "recommendation_records",
            type_="unique",
        )
    if "uq_recommendation_record_revision" not in unique_names:
        op.create_unique_constraint(
            "uq_recommendation_record_revision",
            "recommendation_records",
            ["asset_id", "snapshot_at", "model_version", "revision"],
        )

    foreign_keys = {
        foreign_key.get("name")
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys("recommendation_records")
    }
    if "fk_recommendation_records_previous_record_id" not in foreign_keys:
        op.create_foreign_key(
            "fk_recommendation_records_previous_record_id",
            "recommendation_records",
            "recommendation_records",
            ["previous_record_id"],
            ["id"],
        )

    indexes = {
        index.get("name")
        for index in sa.inspect(op.get_bind()).get_indexes("recommendation_records")
    }
    if "ix_recommendation_records_previous_record_id" not in indexes:
        op.create_index(
            "ix_recommendation_records_previous_record_id",
            "recommendation_records",
            ["previous_record_id"],
        )
    if "ix_recommendation_records_change_type" not in indexes:
        op.create_index(
            "ix_recommendation_records_change_type",
            "recommendation_records",
            ["change_type"],
        )

    op.execute(
        sa.text(
            """
            UPDATE recommendation_records
            SET change_type = 'legacy',
                change_summary = COALESCE(
                    change_summary,
                    'Historyczny wpis bazowy sprzed wersjonowania dziennika.'
                )
            WHERE decision_signature = ''
            """
        )
    )


def downgrade() -> None:
    if "recommendation_records" not in sa.inspect(op.get_bind()).get_table_names():
        return

    indexes = {
        index.get("name")
        for index in sa.inspect(op.get_bind()).get_indexes("recommendation_records")
    }
    if "ix_recommendation_records_change_type" in indexes:
        op.drop_index("ix_recommendation_records_change_type", table_name="recommendation_records")
    if "ix_recommendation_records_previous_record_id" in indexes:
        op.drop_index("ix_recommendation_records_previous_record_id", table_name="recommendation_records")

    foreign_keys = {
        foreign_key.get("name")
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys("recommendation_records")
    }
    if "fk_recommendation_records_previous_record_id" in foreign_keys:
        op.drop_constraint(
            "fk_recommendation_records_previous_record_id",
            "recommendation_records",
            type_="foreignkey",
        )

    unique_names = {
        constraint.get("name")
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints("recommendation_records")
    }
    if "uq_recommendation_record_revision" in unique_names:
        op.drop_constraint(
            "uq_recommendation_record_revision",
            "recommendation_records",
            type_="unique",
        )
    # Starszy schemat mieści tylko jeden wpis na świecę. Przy świadomym
    # downgrade zachowujemy najnowszą rewizję, zamiast dopuścić błąd przy
    # odtwarzaniu poprzedniego ograniczenia unikalności.
    op.execute(sa.text("UPDATE recommendation_records SET previous_record_id = NULL"))
    op.execute(
        sa.text(
            """
            DELETE FROM recommendation_records
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM recommendation_records
                GROUP BY asset_id, snapshot_at, model_version
            )
            """
        )
    )
    if "uq_recommendation_record_snapshot" not in unique_names:
        op.create_unique_constraint(
            "uq_recommendation_record_snapshot",
            "recommendation_records",
            ["asset_id", "snapshot_at", "model_version"],
        )

    for column in (
        "data_complete",
        "rationale",
        "no_trade_reason",
        "signal_snapshot_json",
        "change_details_json",
        "change_summary",
        "change_type",
        "decision_signature",
        "previous_record_id",
        "revision",
    ):
        if column in _columns("recommendation_records"):
            op.drop_column("recommendation_records", column)
