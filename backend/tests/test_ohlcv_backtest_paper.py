from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AssetORM,
    PaperOrderORM,
    PaperStrategyBucketORM,
    PaperStrategyORM,
    PaperTradeORM,
    PricePointORM,
)
from app.db.session import Base
from app.services.intraday_backtest_service import _portfolio_metrics
from app.services.ohlcv_validation import validate_series
from app.services.paper_trading import (
    account_snapshot,
    allocate_recommended_amounts,
    get_or_create_account,
    place_market_order,
    run_active_paper_strategies,
)


def _allow_immediate_strategy_entries(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.paper_trading._entry_session_ready",
        lambda *_args, **_kwargs: (True, None),
    )
    monkeypatch.setattr(
        "app.services.paper_trading.settings.paper_entry_confirmation_cycles",
        1,
    )


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


def test_paper_trading_allocates_cash_buckets_to_distinct_buy_recommendations(tmp_path, monkeypatch):
    _allow_immediate_strategy_entries(monkeypatch)
    engine = create_engine(f"sqlite:///{tmp_path / 'allocation.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for asset_id, confidence, edge in (
            ("first", 82.0, 2.1),
            ("second", 77.0, 3.0),
            ("third", 70.0, 1.8),
        ):
            db.add(AssetORM(id=asset_id, symbol=asset_id.upper(), name=asset_id.title(), type="stock", currency="USD"))
            for i in range(30):
                db.add(PricePointORM(
                    asset_id=asset_id,
                    timestamp=start + timedelta(days=i),
                    open=100 + i,
                    high=101 + i,
                    low=99 + i,
                    close=100 + i,
                    volume=1000,
                ))
        db.commit()

        def recommendation(asset_id, confidence, edge):
            return SimpleNamespace(
                asset_id=asset_id,
                symbol=asset_id.upper(),
                name=asset_id.title(),
                recommendation="KUP",
                data_complete=True,
                has_critical_alert=False,
                expected_net_edge_pct=edge,
                uncertainty_pct=0.4,
                composite_score=75.0,
                confidence=confidence,
                transaction_cost_pct=0.2,
                market_segment="USA",
                regime="bull",
            )

        monkeypatch.setattr(
            "app.services.recommendation_engine.build_all_recommendations",
            lambda _db: [
                recommendation("third", 70.0, 1.8),
                recommendation("first", 82.0, 2.1),
                recommendation("second", 77.0, 3.0),
            ],
        )
        account = get_or_create_account(db, name="allocation", initial_cash=10_000, currency="USD")
        db.commit()

        result = allocate_recommended_amounts(db, account.id, [1000, 2000, 3000])

        assert [row["asset_id"] for row in result["allocations"]] == ["first", "second", "third"]
        assert [row["amount"] for row in result["allocations"]] == [1000, 2000, 3000]
        assert not result["unallocated"]
        assert len({row["asset_id"] for row in result["allocations"]}) == 3
        assert result["account"]["cash"] == 4000.0
        assert db.scalar(select(func.count()).select_from(PaperOrderORM)) == 3
        assert db.scalar(select(func.count()).select_from(PaperTradeORM)) == 3


def test_paper_trading_leaves_bucket_in_cash_when_no_additional_buy_exists(tmp_path, monkeypatch):
    _allow_immediate_strategy_entries(monkeypatch)
    engine = create_engine(f"sqlite:///{tmp_path / 'no_force.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AssetORM(id="only", symbol="ONLY", name="Only", type="stock", currency="USD"))
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(30):
            db.add(PricePointORM(asset_id="only", timestamp=start + timedelta(days=i),
                open=100+i, high=101+i, low=99+i, close=100+i, volume=1000))
        db.commit()
        rec = SimpleNamespace(
            asset_id="only", symbol="ONLY", name="Only", recommendation="KUP",
            data_complete=True, has_critical_alert=False, expected_net_edge_pct=2.0,
            uncertainty_pct=0.5, composite_score=70.0, confidence=75.0,
            transaction_cost_pct=0.2, market_segment="USA", regime="bull",
        )
        monkeypatch.setattr(
            "app.services.recommendation_engine.build_all_recommendations",
            lambda _db: [rec],
        )
        account = get_or_create_account(db, name="no-force", initial_cash=5000, currency="USD")
        db.commit()

        result = allocate_recommended_amounts(db, account.id, [1000, 2000])

        assert len(result["allocations"]) == 1
        assert result["unallocated"] == [{
            "amount": 2000.0,
            "reason": "Oczekuje na odpowiednie aktywo z rekomendacją KUP",
        }]
        assert result["account"]["cash"] == 4000.0
        assert result["account"]["strategy"]["active"] is True
        assert [row["status"] for row in result["account"]["strategy"]["buckets"]] == [
            "position", "waiting",
        ]


def test_background_strategy_sells_and_reinvests_bucket(tmp_path, monkeypatch):
    _allow_immediate_strategy_entries(monkeypatch)
    engine = create_engine(f"sqlite:///{tmp_path / 'background.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for asset_id in ("old", "new"):
            db.add(AssetORM(id=asset_id, symbol=asset_id.upper(), name=asset_id.title(), type="stock", currency="USD"))
            for i in range(30):
                db.add(PricePointORM(asset_id=asset_id, timestamp=start + timedelta(days=i),
                    open=100+i, high=101+i, low=99+i, close=100+i, volume=1000))
        db.commit()

        def rec(asset_id, action, confidence=75.0):
            return SimpleNamespace(
                asset_id=asset_id, symbol=asset_id.upper(), name=asset_id.title(),
                recommendation=action, data_complete=True, has_critical_alert=False,
                expected_net_edge_pct=2.0 if action == "KUP" else -2.0,
                uncertainty_pct=0.5, composite_score=70.0, confidence=confidence,
                transaction_cost_pct=0.2, market_segment="USA", regime="bull",
            )

        recommendations = [rec("old", "KUP")]
        monkeypatch.setattr(
            "app.services.recommendation_engine.build_all_recommendations",
            lambda _db: recommendations,
        )
        account = get_or_create_account(db, name="background", initial_cash=2000, currency="USD")
        db.commit()
        first = allocate_recommended_amounts(db, account.id, [1000])
        assert first["account"]["strategy"]["buckets"][0]["asset_id"] == "old"

        recommendations[:] = [rec("old", "SPRZEDAJ"), rec("new", "KUP", confidence=80.0)]
        result = run_active_paper_strategies(db)

        assert len(result) == 1
        assert len(result[0]["sells"]) == 1
        assert len(result[0]["buys"]) == 1
        strategy = db.scalar(select(PaperStrategyORM).where(PaperStrategyORM.account_id == account.id))
        bucket = db.scalar(select(PaperStrategyBucketORM).where(PaperStrategyBucketORM.strategy_id == strategy.id))
        assert bucket.asset_id == "new"
        assert bucket.quantity > 0
        assert db.scalar(select(func.count()).select_from(PaperOrderORM)) == 3
        assert db.scalar(select(func.count()).select_from(PaperTradeORM)) == 3


def test_paper_strategy_requires_two_matching_closed_session_signals(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'confirmed-entry.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AssetORM(
            id="confirmed", symbol="CONF", name="Confirmed", type="stock", currency="USD",
        ))
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(30):
            db.add(PricePointORM(
                asset_id="confirmed", timestamp=start + timedelta(days=i),
                open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=1000,
            ))
        db.commit()
        recommendation = SimpleNamespace(
            asset_id="confirmed", symbol="CONF", name="Confirmed",
            recommendation="KUP", data_complete=True, has_critical_alert=False,
            expected_net_edge_pct=2.0, uncertainty_pct=0.5, composite_score=70.0,
            confidence=75.0, transaction_cost_pct=0.2,
            market_segment="USA", regime="bull",
        )
        monkeypatch.setattr(
            "app.services.recommendation_engine.build_all_recommendations",
            lambda _db: [recommendation],
        )
        monkeypatch.setattr(
            "app.services.paper_trading._entry_session_ready",
            lambda *_args, **_kwargs: (True, None),
        )
        monkeypatch.setattr(
            "app.services.paper_trading.settings.paper_entry_confirmation_cycles",
            2,
        )
        account = get_or_create_account(
            db, name="confirmed-entry", initial_cash=2000, currency="USD",
        )
        db.commit()

        first = allocate_recommended_amounts(db, account.id, [1000])

        assert first["allocations"] == []
        first_bucket = first["account"]["strategy"]["buckets"][0]
        assert first_bucket["pending_asset_id"] == "confirmed"
        assert first_bucket["pending_signal_count"] == 1
        assert first_bucket["signal_status"] == "confirming"
        assert first["account"]["cash"] == 2000.0

        second = run_active_paper_strategies(db)

        assert len(second[0]["buys"]) == 1
        snapshot = account_snapshot(db, account.id)
        assert snapshot["strategy"]["buckets"][0]["asset_id"] == "confirmed"
        assert snapshot["strategy"]["buckets"][0]["pending_asset_id"] is None


def test_paper_strategy_does_not_confirm_an_open_session_signal(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'open-session.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AssetORM(
            id="open", symbol="OPEN", name="Open", type="stock", currency="USD",
        ))
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(30):
            db.add(PricePointORM(
                asset_id="open", timestamp=start + timedelta(days=i),
                open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=1000,
            ))
        db.commit()
        recommendation = SimpleNamespace(
            asset_id="open", symbol="OPEN", name="Open",
            recommendation="KUP", data_complete=True, has_critical_alert=False,
            expected_net_edge_pct=2.0, uncertainty_pct=0.5, composite_score=70.0,
            confidence=75.0, transaction_cost_pct=0.2,
            market_segment="USA", regime="bull",
        )
        monkeypatch.setattr(
            "app.services.recommendation_engine.build_all_recommendations",
            lambda _db: [recommendation],
        )
        monkeypatch.setattr(
            "app.services.paper_trading._entry_session_ready",
            lambda *_args, **_kwargs: (False, "sesja nadal trwa"),
        )
        account = get_or_create_account(
            db, name="open-session", initial_cash=2000, currency="USD",
        )
        db.commit()

        result = allocate_recommended_amounts(db, account.id, [1000])

        bucket = result["account"]["strategy"]["buckets"][0]
        assert result["allocations"] == []
        assert bucket["pending_asset_id"] == "open"
        assert bucket["pending_signal_count"] == 0
        assert result["account"]["cash"] == 2000.0
