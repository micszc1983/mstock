from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import AssetORM, MLModelRunORM
from app.db.session import Base
from app.services.ml_validation import purged_group_time_series_splits
from app.services.triple_barrier import build_triple_barrier_outcome, primary_side


def test_purged_split_groups_sessions_and_leaves_full_gap():
    sessions = [date(2025, 1, 1) + timedelta(days=index) for index in range(160)]
    groups = [session for session in sessions for _asset in range(3)]
    splits = purged_group_time_series_splits(
        groups, n_splits=3, purge_sessions=10, min_train_sessions=60,
    )

    assert len(splits) == 3
    for train_idx, test_idx in splits:
        train_groups = {groups[index] for index in train_idx}
        test_groups = {groups[index] for index in test_idx}
        assert train_groups.isdisjoint(test_groups)
        assert (min(test_groups) - max(train_groups)).days >= 11


def test_triple_barrier_and_meta_label_use_primary_side():
    closes = [100.0] * 40
    highs = [100.2] * 40
    lows = [99.8] * 40
    # Po dniu 20 następuje jednoznaczne wybicie górnej bariery.
    highs[22] = 105.0
    closes[22] = 103.0
    side = primary_side({"trend_score": 70, "momentum_20d": 5, "sentiment_score": 20})

    result = build_triple_barrier_outcome(
        closes, highs, lows, 20, side=side, transaction_cost_pct=0.2,
    )

    assert result is not None
    assert result.hit == "upper"
    assert result.direction_label == 1
    assert result.side == 1
    assert result.meta_label == 1
    assert result.strategy_net_return_pct > 0


def test_ambiguous_barrier_is_never_a_positive_meta_label():
    closes = [100.0] * 40
    highs = [100.1] * 40
    lows = [99.9] * 40
    highs[21] = 110.0
    lows[21] = 90.0

    result = build_triple_barrier_outcome(
        closes, highs, lows, 20, side=1, transaction_cost_pct=0.2,
    )

    assert result is not None
    assert result.hit == "ambiguous"
    assert result.meta_label == 0


def test_challenger_promotes_better_net_model(tmp_path, monkeypatch):
    from app.services import ml_foundation
    from app.services.ml_models import registry

    engine = create_engine(f"sqlite:///{tmp_path / 'champion.db'}")
    Base.metadata.create_all(engine)
    metrics = {
        "logistic_regression": {"holdout_trades": 50, "holdout_avg_net_return_pct": 0.4, "holdout_profit_factor": 1.2, "holdout_max_drawdown_pct": 8, "f1": 0.60, "cv_folds": 3, "cpcv_paths": 4},
        "random_forest": {"holdout_trades": 50, "holdout_avg_net_return_pct": 0.9, "holdout_profit_factor": 1.5, "holdout_max_drawdown_pct": 7, "f1": 0.62, "cv_folds": 3, "cpcv_paths": 4},
        "xgboost": {"holdout_trades": 50, "holdout_avg_net_return_pct": 0.5, "holdout_profit_factor": 1.3, "holdout_max_drawdown_pct": 12, "f1": 0.59, "cv_folds": 3, "cpcv_paths": 4},
    }
    monkeypatch.setattr(registry, "AVAILABLE_MODELS", ["logistic_regression", "random_forest", "xgboost"])

    def fake_train(db, *, target_name, model_name, asset_id, activate=False, **_kwargs):
        row = MLModelRunORM(
            model_name=model_name, target_name=target_name, asset_id=asset_id,
            trained_at=datetime.now(timezone.utc), dataset_rows=200,
            metrics_json=json.dumps(metrics[model_name]), model_path=f"/{model_name}.joblib",
            is_active=False, deployment_role="candidate",
        )
        db.add(row); db.commit(); db.refresh(row)
        return row

    monkeypatch.setattr(ml_foundation, "train_model", fake_train)
    monkeypatch.setattr(ml_foundation, "score_asset", lambda *_args, **_kwargs: None)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        db.commit()
        outcome = ml_foundation.train_champion_challengers(
            db, target_name="target_meta_label", asset_id="abc",
        )

        assert outcome["champion_model"] == "random_forest"
        champions = db.query(MLModelRunORM).filter_by(is_active=True).all()
        assert len(champions) == 1
        assert champions[0].deployment_role == "champion"


def test_challenger_keeps_stronger_comparable_incumbent(tmp_path, monkeypatch):
    from app.services import ml_foundation
    from app.services.ml_models import registry

    engine = create_engine(f"sqlite:///{tmp_path / 'incumbent.db'}")
    Base.metadata.create_all(engine)
    candidate_metrics = {
        "holdout_trades": 50, "holdout_avg_net_return_pct": 0.4,
        "holdout_profit_factor": 1.2, "holdout_max_drawdown_pct": 8,
        "f1": 0.60, "cv_folds": 3, "cpcv_paths": 4, "cv_method": "purged_group_time_series",
    }
    incumbent_metrics = {
        **candidate_metrics, "holdout_avg_net_return_pct": 1.0,
        "holdout_profit_factor": 1.8, "holdout_max_drawdown_pct": 5,
        "f1": 0.66,
    }
    monkeypatch.setattr(registry, "AVAILABLE_MODELS", ["logistic_regression"])

    def fake_train(db, *, target_name, model_name, asset_id, activate=False, **_kwargs):
        row = MLModelRunORM(
            model_name=model_name, target_name=target_name, asset_id=asset_id,
            trained_at=datetime.now(timezone.utc), dataset_rows=200,
            metrics_json=json.dumps(candidate_metrics), model_path="/candidate.joblib",
            is_active=False, deployment_role="candidate",
        )
        db.add(row); db.commit(); db.refresh(row)
        return row

    monkeypatch.setattr(ml_foundation, "train_model", fake_train)
    monkeypatch.setattr(ml_foundation, "score_asset", lambda *_args, **_kwargs: None)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        db.add(MLModelRunORM(
            model_name="random_forest", target_name="target_meta_label", asset_id="abc",
            trained_at=datetime.now(timezone.utc) - timedelta(days=1), dataset_rows=200,
            metrics_json=json.dumps(incumbent_metrics), model_path="/champion.joblib",
            is_active=True, deployment_role="champion",
        ))
        db.commit()

        outcome = ml_foundation.train_champion_challengers(
            db, target_name="target_meta_label", asset_id="abc",
        )

        assert outcome["promoted"] is False
        assert outcome["champion_model"] == "random_forest"
        champions = db.query(MLModelRunORM).filter_by(is_active=True).all()
        assert len(champions) == 1
        assert champions[0].model_name == "random_forest"


def test_active_model_fallback_never_uses_another_asset(tmp_path):
    from app.repositories.ml import get_active_model_run

    engine = create_engine(f"sqlite:///{tmp_path / 'fallback.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"),
            AssetORM(id="xyz", symbol="XYZ", name="XYZ", type="stock", currency="USD"),
        ])
        db.add(MLModelRunORM(
            model_name="random_forest", target_name="target_meta_label", asset_id="abc",
            trained_at=datetime.now(timezone.utc), dataset_rows=200, metrics_json="{}",
            model_path="/abc.joblib", is_active=True, deployment_role="champion",
        ))
        db.commit()

        assert get_active_model_run(db, "target_meta_label", asset_id="xyz") is None


def test_automatic_training_includes_twenty_day_direction(monkeypatch):
    from app.services import ml_foundation

    calls = []
    monkeypatch.setattr(
        ml_foundation,
        "list_assets",
        lambda _db: [SimpleNamespace(id="abc")],
    )
    monkeypatch.setattr(
        ml_foundation,
        "list_training_rows_for_target",
        lambda *_args, **_kwargs: [object()] * ml_foundation.settings.ml_min_training_rows,
    )
    monkeypatch.setattr(
        ml_foundation,
        "train_champion_challengers",
        lambda _db, *, target_name, asset_id, market=None: (
            calls.append((asset_id, market, target_name)) or {"promoted": False}
        ),
    )
    monkeypatch.setattr(ml_foundation.settings, "ml_market_models_enabled", False)

    results = ml_foundation.train_all_targets(object())

    assert [target for _, _, target in calls] == [
        "target_up_5d",
        "target_up_20d",
        "target_triple_barrier",
        "target_meta_label",
    ]
    assert {result["target"] for result in results} == {
        "target_up_5d",
        "target_up_20d",
        "target_triple_barrier",
        "target_meta_label",
    }
