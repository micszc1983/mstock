"""add provider config columns to assets

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009_evaluation_comparison"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.add_column(sa.Column("price_symbol",   sa.String(32),  nullable=True))
        batch_op.add_column(sa.Column("news_symbol",    sa.String(32),  nullable=True))
        batch_op.add_column(sa.Column("news_term",      sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("metal_price_fn", sa.String(32),  nullable=True))

    # Wypełnij istniejące wiersze wartościami z dawnego settings.asset_provider_config
    op.execute("""
        UPDATE assets SET price_symbol='NVDA',   news_symbol='NVDA',  news_term='NVIDIA',    metal_price_fn=NULL WHERE id='nvda'
    """)
    op.execute("""
        UPDATE assets SET price_symbol='AAPL',   news_symbol='AAPL',  news_term='Apple',     metal_price_fn=NULL WHERE id='aapl'
    """)
    op.execute("""
        UPDATE assets SET price_symbol='MSFT',   news_symbol='MSFT',  news_term='Microsoft', metal_price_fn=NULL WHERE id='msft'
    """)
    op.execute("""
        UPDATE assets SET price_symbol='TSLA',   news_symbol='TSLA',  news_term='Tesla',     metal_price_fn=NULL WHERE id='tsla'
    """)
    op.execute("""
        UPDATE assets SET price_symbol='KGH.WA', news_symbol=NULL,    news_term='KGHM',      metal_price_fn=NULL WHERE id='kghm'
    """)
    op.execute("""
        UPDATE assets SET price_symbol=NULL,     news_symbol=NULL,    news_term='gold',      metal_price_fn='GOLD'   WHERE id='gold'
    """)
    op.execute("""
        UPDATE assets SET price_symbol=NULL,     news_symbol=NULL,    news_term='silver',    metal_price_fn='SILVER' WHERE id='silver'
    """)
    op.execute("""
        UPDATE assets SET price_symbol=NULL,     news_symbol=NULL,    news_term='platinum',  metal_price_fn=NULL WHERE id='platinum'
    """)
    op.execute("""
        UPDATE assets SET price_symbol=NULL,     news_symbol=NULL,    news_term='palladium', metal_price_fn=NULL WHERE id='palladium'
    """)


def downgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_column("price_symbol")
        batch_op.drop_column("news_symbol")
        batch_op.drop_column("news_term")
        batch_op.drop_column("metal_price_fn")
