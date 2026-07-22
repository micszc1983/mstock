"""move runtime schema changes into Alembic

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if table in _tables() and column.name not in _columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing("assets", sa.Column("currency", sa.String(8), nullable=False, server_default="USD"))
    op.get_bind().execute(sa.text("UPDATE assets SET currency = 'PLN' WHERE price_symbol LIKE '%.WA'"))
    _add_column_if_missing("ml_model_runs", sa.Column("asset_id", sa.String(64), nullable=True))
    for name in ("implied_volatility", "put_call_ratio", "iv_rank"):
        _add_column_if_missing("daily_asset_features", sa.Column(name, sa.Float(), nullable=True))
    for name in ("vwap", "adx", "di_plus", "di_minus"):
        _add_column_if_missing("intraday_candles", sa.Column(name, sa.Float(), nullable=True))

    tables = _tables()
    if "portfolio_positions" not in tables:
        op.create_table(
            "portfolio_positions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("avg_buy_price", sa.Float(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("asset_id", name="uq_portfolio_position_asset"),
        )
    if "earnings" not in tables:
        op.create_table(
            "earnings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
            sa.Column("report_date", sa.Date(), nullable=False, index=True),
            sa.Column("fiscal_period", sa.String(16)), sa.Column("eps_estimate", sa.Float()),
            sa.Column("eps_actual", sa.Float()), sa.Column("revenue_estimate", sa.Float()),
            sa.Column("revenue_actual", sa.Float()), sa.Column("eps_surprise_pct", sa.Float()),
            sa.Column("surprise_label", sa.String(8)),
            sa.Column("is_upcoming", sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "earnings_call_analyses" not in tables:
        op.create_table(
            "earnings_call_analyses",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("earnings_id", sa.Integer(), sa.ForeignKey("earnings.id"), nullable=False, unique=True),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
            sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("tone_score", sa.Integer(), nullable=False), sa.Column("guidance_change", sa.String(16), nullable=False),
            sa.Column("key_themes_json", sa.Text(), nullable=False), sa.Column("risk_factors_json", sa.Text(), nullable=False),
            sa.Column("key_quote", sa.Text()), sa.Column("llm_sentiment_score", sa.Float(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False), sa.Column("model_used", sa.String(64), nullable=False),
            sa.Column("news_articles_used", sa.Integer(), nullable=False, server_default="0"),
        )
    if "insider_trades" not in tables:
        op.create_table(
            "insider_trades",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
            sa.Column("transaction_date", sa.Date(), nullable=False, index=True), sa.Column("filing_date", sa.Date()),
            sa.Column("name", sa.String(200), nullable=False), sa.Column("transaction_code", sa.String(4), nullable=False),
            sa.Column("transaction_type", sa.String(20), nullable=False), sa.Column("shares", sa.Float()),
            sa.Column("price", sa.Float()), sa.Column("value", sa.Float()),
            sa.Column("source", sa.String(20), nullable=False, server_default="finnhub"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "short_interest" not in tables:
        op.create_table(
            "short_interest", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
            sa.Column("report_date", sa.Date(), nullable=False, index=True), sa.Column("shares_short", sa.Float()),
            sa.Column("short_percent_float", sa.Float()), sa.Column("short_ratio", sa.Float()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "intraday_backtests" not in tables:
        op.create_table(
            "intraday_backtests", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
            sa.Column("resolution", sa.String(8), nullable=False, server_default="15"),
            sa.Column("run_at", sa.DateTime(), nullable=False), sa.Column("lookback_days", sa.Integer(), nullable=False),
            sa.Column("candles_count", sa.Integer(), nullable=False), sa.Column("total_signals", sa.Integer(), nullable=False),
            sa.Column("win_count", sa.Integer(), nullable=False), sa.Column("loss_count", sa.Integer(), nullable=False),
            sa.Column("timeout_count", sa.Integer(), nullable=False), sa.Column("win_rate", sa.Float()),
            sa.Column("avg_win_pct", sa.Float()), sa.Column("avg_loss_pct", sa.Float()),
            sa.Column("avg_return_pct", sa.Float()), sa.Column("total_return_pct", sa.Float()), sa.Column("expectancy", sa.Float()),
            sa.Column("rsi_oversold", sa.Float(), nullable=False), sa.Column("rsi_overbought", sa.Float(), nullable=False),
            sa.Column("sl_pct", sa.Float(), nullable=False), sa.Column("tp_pct", sa.Float(), nullable=False),
            sa.Column("default_signals", sa.Integer(), nullable=False), sa.Column("default_win_rate", sa.Float()),
            sa.Column("default_expectancy", sa.Float()), sa.Column("trades_json", sa.Text(), nullable=False),
        )
    if "anomaly_scores" not in tables:
        op.create_table(
            "anomaly_scores", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
            sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("anomaly_score", sa.Float(), nullable=False), sa.Column("is_anomaly", sa.Boolean(), nullable=False),
            sa.Column("trained_on_rows", sa.Integer(), nullable=False), sa.Column("top_features_json", sa.Text(), nullable=False),
            sa.Column("raw_response", sa.Text(), nullable=False, server_default=""),
            sa.UniqueConstraint("asset_id", "scored_at", name="uq_anomaly_score"),
        )
    else:
        _add_column_if_missing("anomaly_scores", sa.Column("raw_response", sa.Text(), nullable=False, server_default=""))

    # Usuń istniejące duplikaty przed założeniem gwarancji upsertu.
    bind = op.get_bind()
    bind.execute(sa.text("""DELETE FROM ml_predictions WHERE id NOT IN (
        SELECT MAX(id) FROM ml_predictions GROUP BY asset_id, snapshot_at, target_name
    )"""))
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("ml_predictions")}
    if "uq_ml_prediction_snapshot" not in indexes:
        op.create_index("uq_ml_prediction_snapshot", "ml_predictions", ["asset_id", "snapshot_at", "target_name"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_ml_prediction_snapshot", table_name="ml_predictions")
