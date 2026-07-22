"""allow provider news titles longer than SQLite varchar hint

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite nie egzekwuje VARCHAR(500), więc jego fizyczny typ nie wymaga
    # przebudowy tabeli. PostgreSQL musi jawnie dostać nielimitowany TEXT.
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "news_items", "title",
            existing_type=sa.String(length=500),
            type_=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "news_items", "title",
            existing_type=sa.Text(),
            type_=sa.String(length=500),
            existing_nullable=False,
        )
