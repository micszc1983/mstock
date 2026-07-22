from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import AssetORM, PaperOrderORM, PaperTradeORM, PricePointORM
from app.db.session import Base
from app.services.intraday_backtest_service import _portfolio_metrics
from app.services.ohlcv_validation import validate_series
from app.services.paper_trading import account_snapshot, get_or_create_account, place_market_order


def test_ohlcv_validator_blocks_impossible_bar():
    bars = [SimpleNamespace(timestamp=datetime(2026, 1, 1), open=100, high=99, low=98, close=101, volume=10)]
    result = validate_series(bars)
    assert not result["valid"]
    assert result["critical_count"] >= 1


def test_backtest_portfolio_metrics_include_risk_statistics():
    trades = [
        {"entry_price": 100, "pct": 2.0, "result": "TP"},
        {"entry_price": 110, "pct": -1.0, "result": "SL"},
    ]
    result = _portfolio_metrics(trades, 10_000, sl_pct=1.0, risk_per_trade_pct=1, max_position_pct=25)
    assert result["final_capital"] > 10_000
    assert result["max_drawdown_pct"] > 0
    assert result["profit_factor"] is not None
    assert len(result["equity_curve"]) == 3


def test_paper_trading_persists_order_trade_and_position(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(30):
            db.add(PricePointORM(asset_id="abc", timestamp=start + timedelta(days=i),
                open=100+i, high=101+i, low=99+i, close=100+i, volume=1000))
        db.commit()
        account = get_or_create_account(db, initial_cash=10_000); db.commit()
        buy = place_market_order(db, account.id, "abc", "buy", 10, commission_pct=.1, slippage_pct=.1)
        assert buy.status == "filled"
        snap = account_snapshot(db, account.id)
        assert snap["positions"][0]["quantity"] == 10
        sell = place_market_order(db, account.id, "abc", "sell", 10, commission_pct=.1, slippage_pct=.1)
        assert sell.status == "filled"
        assert db.scalar(select(func.count()).select_from(PaperOrderORM)) == 2
        assert db.scalar(select(func.count()).select_from(PaperTradeORM)) == 2
