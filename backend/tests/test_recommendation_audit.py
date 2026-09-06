from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AssetORM,
    DailyAssetFeatureORM,
    MLTrainingRowORM,
    PricePointORM,
    RecommendationRecordORM,
    RecommendationAuditRunORM,
)
from app.db.session import Base
from app.schemas.recommendation import AssetRecommendation
from app.services.recommendation_audit import (
    AUDIT_MODEL_VERSION,
    automatic_audit_status,
    run_automatic_audit_if_due,
    run_walk_forward_audit,
)
from app.services.recommendation_calibration import _walk_forward_gate
from app.services.recommendation_journal import (
    evaluate_recommendation_outcomes,
    persist_recommendation,
)
from app.services.technical_indicators import compute_all
from app.repositories.ml import delete_predictions_older_than
from app.db.models import MLPredictionORM


def _feature(asset_id: str, snap: datetime, value: float) -> DailyAssetFeatureORM:
    return DailyAssetFeatureORM(
        asset_id=asset_id, snapshot_at=snap, last_price=100 + value,
        price_change_1d_pct=value, price_change_5d_pct=value,
        price_change_20d_pct=value, trend_score=value * 20,
        sentiment_score=value * 10, narrative_shift_score=0,
        divergence_score=30, fragility_score=30, regime_label="trending",
        regime_confidence=0.8, dominant_narrative=None, volatility_10d=1,
        momentum_20d=value, news_count_7d=1,
    )


def test_walk_forward_has_untouched_blocks_and_embargo(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr("app.core.config.settings.recommendation_calibration_min_rows", 60)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        for index in range(220):
            snap = start + timedelta(days=index)
            signal = 1.0 if index % 3 == 0 else -1.0 if index % 3 == 1 else 0.0
            realized = 2.0 if signal > 0 else -2.0 if signal < 0 else 0.05
            payload = {
                "trend_score": signal * 70, "sentiment_score": signal * 50,
                "momentum_20d": signal * 8, "fragility_score": 30,
                "divergence_score": 30, "price_change_1d_pct": signal,
                "price_change_5d_pct": signal * 2, "price_change_20d_pct": signal * 4,
            }
            db.add(_feature("abc", snap, signal))
            db.add(MLTrainingRowORM(
                asset_id="abc", snapshot_at=snap, feature_json=json.dumps(payload),
                target_up_1d=int(realized > 0), target_up_5d=int(realized > 0),
                target_up_20d=int(realized > 0), target_return_1d=realized / 2,
                target_return_5d=realized, target_return_20d=realized * 2,
                target_thesis_success=None,
            ))
        db.commit()

        report = run_walk_forward_audit(db, fold_count=3)

        assert report["evaluated_rows"] > 0
        assert report["embargo_sessions"] == 20
        assert 0 <= report["calibration"]["ece"] <= 1
        assert report["by_market_side"]
        assert report["by_regime_side"]
        for fold in report["folds"]:
            train_end = datetime.fromisoformat(fold["train_end_exclusive"])
            test_start = datetime.fromisoformat(fold["test_start"])
            assert (test_start - train_end).days >= 20


def test_automatic_audit_waits_for_interval_and_new_outcomes(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'automatic_audit.db'}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    with Session(engine) as db:
        audit = RecommendationAuditRunORM(
            created_at=now - timedelta(days=2), model_version=AUDIT_MODEL_VERSION,
            dataset_rows=100, eligible_rows=100, excluded_outliers=0,
            fold_count=3, embargo_sessions=20,
            result_json=json.dumps({"folds": [{"test_end": "2026-07-14"}]}),
        )
        db.add(audit)
        db.commit()

        young = automatic_audit_status(db, now=now, interval_days=7, min_new_outcomes=50)
        assert young["due"] is False
        assert young["reason"] == "interval_not_elapsed"

        audit.created_at = now - timedelta(days=8)
        db.commit()
        samples = [
            SimpleNamespace(outlier_reason=None, snapshot_at=datetime(2026, 7, 14, tzinfo=timezone.utc))
            for _ in range(100)
        ] + [
            SimpleNamespace(outlier_reason=None, snapshot_at=datetime(2026, 7, 15, tzinfo=timezone.utc))
            for _ in range(49)
        ]
        monkeypatch.setattr("app.services.recommendation_audit.load_audit_samples", lambda _db: samples)
        too_few = automatic_audit_status(db, now=now, interval_days=7, min_new_outcomes=50)
        assert too_few["due"] is False
        assert too_few["new_outcomes"] == 49

        samples.append(SimpleNamespace(
            outlier_reason=None,
            snapshot_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        ))
        ready = automatic_audit_status(db, now=now, interval_days=7, min_new_outcomes=50)
        assert ready["due"] is True
        assert ready["new_outcomes"] == 50


def test_automatic_audit_runs_and_invalidates_recommendations(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'automatic_run.db'}")
    Base.metadata.create_all(engine)
    invalidated = []
    monkeypatch.setattr(
        "app.services.recommendation_audit.automatic_audit_status",
        lambda _db, now=None: {
            "due": True, "reason": "ready", "new_outcomes": 60,
            "required_new_outcomes": 50, "eligible_rows": 1060,
        },
    )
    monkeypatch.setattr(
        "app.services.recommendation_audit.run_walk_forward_audit",
        lambda _db, fold_count: {"id": 7, "evaluated_rows": 300, "eligible_rows": 1060},
    )
    monkeypatch.setattr(
        "app.services.recommendation_engine.invalidate_recommendations_cache",
        lambda: invalidated.append(True),
    )
    with Session(engine) as db:
        result = run_automatic_audit_if_due(db)

    assert result["ran"] is True
    assert result["audit_id"] == 7
    assert invalidated == [True]


def test_journal_is_idempotent_and_outcomes_mature_by_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'journal.db'}")
    Base.metadata.create_all(engine)
    snap = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        for day in range(1, 21):
            price = 100 + day
            db.add(PricePointORM(
                asset_id="abc", timestamp=snap + timedelta(days=day),
                open=price, high=price, low=price, close=price, volume=1000,
            ))
        db.commit()
        rec = AssetRecommendation.model_construct(
            asset_id="abc", snapshot_at=snap, market_segment="USA", regime="trending",
            recommendation="KUP", calibration_scope="market", calibration_sample_size=200,
            composite_score=70, confidence=75, probability_buy=75, probability_sell=10,
            probability_no_trade=15, buy_threshold=65, sell_threshold=70,
            transaction_cost_pct=0.2, expected_gross_edge_pct=1.5,
            expected_net_edge_pct=1.3, uncertainty_pct=0.3, last_price=100,
        )
        first = persist_recommendation(db, rec)
        db.commit()
        second = persist_recommendation(db, rec)
        db.commit()

        assert first is not None and second is not None and first.id == second.id
        assert db.scalar(select(func.count()).select_from(RecommendationRecordORM)) == 1
        assert evaluate_recommendation_outcomes(db) == 1
        row = db.scalar(select(RecommendationRecordORM))
        assert row is not None
        assert row.realized_return_1d_pct == 1.0
        assert row.realized_return_5d_pct == 5.0
        assert row.realized_return_20d_pct == 20.0
        assert row.strategy_net_return_5d_pct == 4.8


def test_short_horizon_outcome_is_not_blocked_by_pending_20d_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'journal-horizon-queues.db'}")
    Base.metadata.create_all(engine)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def recommendation(asset_id: str, snapshot_at: datetime) -> AssetRecommendation:
        return AssetRecommendation.model_construct(
            asset_id=asset_id, snapshot_at=snapshot_at,
            market_segment="USA", regime="trending", recommendation="KUP",
            calibration_scope="market", calibration_sample_size=200,
            composite_score=70, confidence=75, probability_buy=75,
            probability_sell=10, probability_no_trade=15,
            buy_threshold=65, sell_threshold=70, transaction_cost_pct=0.2,
            expected_gross_edge_pct=1.5, expected_net_edge_pct=1.3,
            uncertainty_pct=0.3, last_price=100,
        )

    with Session(engine) as db:
        db.add_all([
            AssetORM(id="old", symbol="OLD", name="Old", type="stock", currency="USD"),
            AssetORM(id="recent", symbol="NEW", name="Recent", type="stock", currency="USD"),
        ])
        db.commit()
        old_rows = []
        for offset in (0, 1):
            row = persist_recommendation(db, recommendation("old", start + timedelta(days=offset)))
            assert row is not None
            row.realized_return_1d_pct = 1.0
            row.strategy_net_return_1d_pct = 0.8
            row.realized_return_5d_pct = 5.0
            row.strategy_net_return_5d_pct = 4.8
            old_rows.append(row)
        recent_snapshot = start + timedelta(days=10)
        recent = persist_recommendation(db, recommendation("recent", recent_snapshot))
        assert recent is not None
        db.add(PricePointORM(
            asset_id="recent", timestamp=recent_snapshot + timedelta(days=1),
            open=110, high=110, low=110, close=110, volume=1000,
        ))
        db.commit()

        assert evaluate_recommendation_outcomes(db, limit=2) == 1
        db.refresh(recent)
        assert recent.realized_return_1d_pct == 10.0
        assert recent.realized_return_5d_pct is None
        assert all(row.realized_return_20d_pct is None for row in old_rows)


def test_journal_creates_revision_only_for_material_change(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'journal-revisions.db'}")
    Base.metadata.create_all(engine)
    snap = datetime(2025, 2, 3, tzinfo=timezone.utc)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        db.commit()
        rec = AssetRecommendation.model_construct(
            asset_id="abc", snapshot_at=snap, market_segment="USA", regime="range_bound",
            recommendation="BRAK TRANSAKCJI", calibration_scope="market_regime",
            calibration_sample_size=300, composite_score=54, confidence=50,
            probability_buy=54, probability_sell=40, probability_no_trade=6,
            buy_threshold=60, sell_threshold=60, transaction_cost_pct=0.2,
            expected_gross_edge_pct=1.5, expected_net_edge_pct=1.3,
            uncertainty_pct=0.3, no_trade_reason="Poniżej progu.", rationale="Brak przewagi.",
            trend_score=20, sentiment_score=10, fragility_score=30, divergence_score=15,
            data_complete=True, last_price=100,
        )

        initial = persist_recommendation(db, rec)
        db.commit()
        unchanged = persist_recommendation(db, rec)
        db.commit()

        assert initial is not None and unchanged is not None
        assert unchanged.id == initial.id
        assert initial.revision == 1
        assert initial.change_type == "initial"

        rec.recommendation = "KUP"
        rec.probability_buy = 62
        rec.probability_no_trade = 2
        rec.confidence = 62
        rec.no_trade_reason = None
        rec.rationale = "Próg kupna został przekroczony."
        changed = persist_recommendation(db, rec)
        db.commit()
        repeated = persist_recommendation(db, rec)
        db.commit()

        assert changed is not None and repeated is not None
        assert changed.id != initial.id
        assert repeated.id == changed.id
        assert changed.revision == 2
        assert changed.previous_record_id == initial.id
        assert changed.change_type == "action"
        assert "Decyzja: BRAK TRANSAKCJI → KUP" in (changed.change_summary or "")
        details = json.loads(changed.change_details_json)
        assert details["recommendation"] == {"from": "BRAK TRANSAKCJI", "to": "KUP"}
        assert json.loads(changed.signal_snapshot_json)["probability_buy"] == 62
        assert db.scalar(select(func.count()).select_from(RecommendationRecordORM)) == 2


def test_alpha_feature_uses_trailing_return_not_future_target():
    closes = [100, 101, 102, 103, 104, 105]
    snap = datetime(2025, 1, 6, tzinfo=timezone.utc).date()
    trailing = (closes[-1] / closes[-6] - 1) * 100

    features = compute_all(
        closes, [1000] * 6, {snap: 1.0}, snap,
        asset_return_5d=trailing, macro_data={}, sector_closes=[],
    )

    assert features["alpha_vs_spy_5d"] == trailing - 1.0
    assert features["alpha_vs_spy_5d"] != 25.0 - 1.0  # przykładowy przyszły target


def test_prediction_retention_does_not_compare_naive_and_aware_datetimes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retention.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        db.add(MLPredictionORM(
            asset_id="abc", snapshot_at=datetime(2020, 1, 1), model_run_id=1,
            target_name="target_up_5d", probability_up=0.5,
            predicted_label="up", raw_json="{}",
        ))
        db.flush()  # obiekt pozostaje w identity map i ma naive datetime
        assert delete_predictions_older_than(db, 365) == 1


def test_live_gate_blocks_unprofitable_or_too_small_segments(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gate.db'}")
    Base.metadata.create_all(engine)
    report = {
        "by_market_side": [
            {"name": "USA", "side": "BUY", "trades": 100, "avg_net_return_pct": 1.0, "profit_factor": 1.5, "win_rate_pct": 62.0},
            {"name": "USA", "side": "SELL", "trades": 100, "avg_net_return_pct": -0.2, "profit_factor": 0.9, "win_rate_pct": 40.0},
            {"name": "OTHER", "side": "BUY", "trades": 100, "avg_net_return_pct": -0.2, "profit_factor": 0.9, "win_rate_pct": 40.0},
        ],
        "by_regime_side": [
            {"name": "range_bound", "side": "BUY", "trades": 80, "avg_net_return_pct": 0.7, "profit_factor": 1.3, "win_rate_pct": 58.0},
            {"name": "range_bound", "side": "SELL", "trades": 80, "avg_net_return_pct": -0.2, "profit_factor": 0.9, "win_rate_pct": 40.0},
            {"name": "risk_on", "side": "BUY", "trades": 5, "avg_net_return_pct": 2.0, "profit_factor": 2.0, "win_rate_pct": 80.0},
        ],
    }
    with Session(engine) as db:
        db.add(RecommendationAuditRunORM(
            created_at=datetime.now(timezone.utc), model_version=AUDIT_MODEL_VERSION,
            dataset_rows=1000, eligible_rows=990, excluded_outliers=10,
            fold_count=3, embargo_sessions=20, result_json=json.dumps(report),
        ))
        db.commit()

        assert _walk_forward_gate(db, "USA", "range_bound", "BUY") == (True, None)
        assert _walk_forward_gate(db, "USA", "range_bound", "SELL")[0] is False
        assert _walk_forward_gate(db, "OTHER", "range_bound", "BUY")[0] is False
        assert _walk_forward_gate(db, "USA", "risk_on", "BUY")[0] is False
