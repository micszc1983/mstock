"""Trwały dziennik rekomendacji i ocena ich wyników po sesjach 1/5/20."""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import PricePointORM, RecommendationRecordORM
from app.schemas.recommendation import AssetRecommendation


MODEL_VERSION = "calibrated_v6_oof_meta"
HORIZONS = (1, 5, 20)
_journal_lock = threading.RLock()

_SNAPSHOT_FIELDS = (
    "recommendation",
    "composite_score",
    "confidence",
    "market_segment",
    "calibration_scope",
    "calibration_sample_size",
    "probability_buy",
    "probability_sell",
    "probability_no_trade",
    "buy_threshold",
    "sell_threshold",
    "transaction_cost_pct",
    "expected_gross_edge_pct",
    "expected_net_edge_pct",
    "uncertainty_pct",
    "no_trade_reason",
    "trend_score",
    "sentiment_score",
    "fragility_score",
    "divergence_score",
    "regime",
    "forecast_dir_1d",
    "forecast_dir_5d",
    "forecast_dir_20d",
    "forecast_up_1d",
    "forecast_up_5d",
    "forecast_up_20d",
    "conviction_score",
    "risk_score",
    "action_label",
    "ml_prediction",
    "ml_prob_up",
    "ml_20d_prediction",
    "ml_20d_prob_up",
    "ml_thesis_prediction",
    "ml_meta_prediction",
    "meta_trade_probability",
    "meta_gate_applied",
    "meta_trade_threshold",
    "meta_threshold_scope",
    "directional_accuracy",
    "active_alerts",
    "has_critical_alert",
    "rationale",
    "data_complete",
    "implied_volatility",
    "put_call_ratio",
    "iv_rank",
    "earnings_surprise_pct",
    "last_price",
)

_CHANGE_LABELS = {
    "recommendation": "Decyzja",
    "has_position": "Pozycja w portfelu",
    "probability_buy": "P(kup)",
    "probability_sell": "P(sprzedaj)",
    "probability_no_trade": "P(brak transakcji)",
    "buy_threshold": "Próg kupna",
    "sell_threshold": "Próg sprzedaży",
    "confidence": "Pewność",
    "composite_score": "Wynik złożony",
    "expected_net_edge_pct": "Przewaga netto",
    "uncertainty_pct": "Niepewność",
    "regime": "Reżim",
    "market_segment": "Rynek",
    "calibration_scope": "Zakres kalibracji",
    "no_trade_reason": "Powód braku transakcji",
    "trend_score": "Trend",
    "sentiment_score": "Sentyment",
    "fragility_score": "Kruchość",
    "divergence_score": "Rozjazd",
    "forecast_dir_5d": "Prognoza 5d",
    "forecast_dir_20d": "Prognoza 20d",
    "meta_gate_applied": "Bramka meta",
    "data_complete": "Kompletność danych",
    "last_price": "Cena",
}

_SUMMARY_PRIORITY = tuple(_CHANGE_LABELS)


def _model_action(recommendation: str) -> str:
    if recommendation == "KUP":
        return "BUY"
    if recommendation == "SPRZEDAJ":
        return "SELL"
    return "NO_TRADE"


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _recommendation_snapshot(rec: AssetRecommendation, has_position: bool) -> dict[str, Any]:
    payload = {
        field: _jsonable(getattr(rec, field, None))
        for field in _SNAPSHOT_FIELDS
    }
    payload["has_position"] = has_position
    payload["top_signals"] = _jsonable(getattr(rec, "top_signals", []))
    return payload


def _record_snapshot(row: RecommendationRecordORM) -> dict[str, Any]:
    try:
        payload = json.loads(row.signal_snapshot_json or "{}")
        if isinstance(payload, dict) and payload:
            return payload
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    # Rekordy sprzed migracji nie mają pełnego snapshotu. Te pola pozwalają
    # mimo to opisać pierwszą zmianę po wdrożeniu wersjonowania.
    return {
        "recommendation": row.displayed_action,
        "has_position": row.has_position,
        "market_segment": row.market,
        "regime": row.regime,
        "calibration_scope": row.calibration_scope,
        "calibration_sample_size": row.calibration_sample_size,
        "composite_score": row.composite_score,
        "confidence": row.confidence,
        "probability_buy": row.probability_buy,
        "probability_sell": row.probability_sell,
        "probability_no_trade": row.probability_no_trade,
        "buy_threshold": row.buy_threshold,
        "sell_threshold": row.sell_threshold,
        "transaction_cost_pct": row.transaction_cost_pct,
        "expected_gross_edge_pct": row.expected_gross_edge_pct,
        "expected_net_edge_pct": row.expected_net_edge_pct,
        "uncertainty_pct": row.uncertainty_pct,
        "meta_trade_probability": row.meta_trade_probability,
        "meta_gate_applied": row.meta_gate_applied,
        "meta_trade_threshold": row.meta_trade_threshold,
        "meta_threshold_scope": row.meta_threshold_scope,
        "no_trade_reason": row.no_trade_reason,
        "rationale": row.rationale,
        "data_complete": row.data_complete,
        "last_price": row.base_price,
    }


def _signature(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _changes(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, dict[str, Any]]:
    keys = set(previous) | set(current)
    return {
        key: {"from": previous.get(key), "to": current.get(key)}
        for key in sorted(keys)
        if previous.get(key) != current.get(key)
    }


def _format_change_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "tak" if value else "nie"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    text = str(value)
    return text if len(text) <= 90 else f"{text[:87]}…"


def _change_summary(changes: dict[str, dict[str, Any]]) -> str:
    if not changes:
        return "Brak materialnej zmiany."
    ordered = [field for field in _SUMMARY_PRIORITY if field in changes]
    ordered.extend(field for field in changes if field not in ordered and field != "top_signals")
    fragments = []
    for field in ordered[:6]:
        values = changes[field]
        label = _CHANGE_LABELS.get(field, field.replace("_", " "))
        fragments.append(
            f"{label}: {_format_change_value(values['from'])} → {_format_change_value(values['to'])}"
        )
    hidden = len([field for field in changes if field != "top_signals"]) - len(fragments)
    if "top_signals" in changes:
        hidden += 1
    if hidden > 0:
        fragments.append(f"+{hidden} innych zmian")
    return "; ".join(fragments)


def _change_type(changes: dict[str, dict[str, Any]], previous: RecommendationRecordORM | None) -> str:
    if previous is None:
        return "initial"
    if "recommendation" in changes:
        return "action"
    if "has_position" in changes:
        return "position"
    if "data_complete" in changes:
        return "data_quality"
    if {"regime", "market_segment", "calibration_scope", "buy_threshold", "sell_threshold"} & changes.keys():
        return "calibration"
    return "signals"


def _latest_record(
    db: Session,
    asset_id: str,
    snapshot_at: datetime,
    *,
    lock: bool = False,
) -> RecommendationRecordORM | None:
    stmt = (
        select(RecommendationRecordORM)
        .where(
            RecommendationRecordORM.asset_id == asset_id,
            RecommendationRecordORM.snapshot_at == snapshot_at,
            RecommendationRecordORM.model_version == MODEL_VERSION,
        )
        .order_by(
            RecommendationRecordORM.revision.desc(),
            RecommendationRecordORM.created_at.desc(),
            RecommendationRecordORM.id.desc(),
        )
        .limit(1)
    )
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def persist_recommendation(
    db: Session,
    rec: AssetRecommendation,
    *,
    has_position: bool = False,
) -> RecommendationRecordORM | None:
    """Zapisuje nową rewizję tylko wtedy, gdy rekomendacja materialnie się zmieniła."""
    if rec.snapshot_at is None:
        return None
    with _journal_lock:
        previous = _latest_record(db, rec.asset_id, rec.snapshot_at, lock=True)
        snapshot = _recommendation_snapshot(rec, has_position)
        signature = _signature(snapshot)
        if previous is not None and previous.decision_signature == signature:
            return previous

        differences = (
            _changes(_record_snapshot(previous), snapshot)
            if previous is not None else {}
        )
        revision = int(previous.revision or 1) + 1 if previous is not None else 1
        row = RecommendationRecordORM(
            asset_id=rec.asset_id,
            snapshot_at=rec.snapshot_at,
            created_at=datetime.now(timezone.utc),
            model_version=MODEL_VERSION,
            revision=revision,
            previous_record_id=previous.id if previous is not None else None,
            decision_signature=signature,
            change_type=_change_type(differences, previous),
            change_summary=(
                _change_summary(differences)
                if previous is not None else "Pierwsza rekomendacja dla tej świecy."
            ),
            change_details_json=json.dumps(differences, ensure_ascii=False, sort_keys=True),
            signal_snapshot_json=json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
            market=rec.market_segment,
            regime=rec.regime,
            action=_model_action(rec.recommendation),
            displayed_action=rec.recommendation,
            has_position=has_position,
            calibration_scope=rec.calibration_scope,
            calibration_sample_size=rec.calibration_sample_size,
            composite_score=rec.composite_score,
            confidence=rec.confidence,
            probability_buy=rec.probability_buy,
            probability_sell=rec.probability_sell,
            probability_no_trade=rec.probability_no_trade,
            buy_threshold=rec.buy_threshold,
            sell_threshold=rec.sell_threshold,
            transaction_cost_pct=rec.transaction_cost_pct,
            expected_gross_edge_pct=rec.expected_gross_edge_pct,
            expected_net_edge_pct=rec.expected_net_edge_pct,
            uncertainty_pct=rec.uncertainty_pct,
            meta_trade_probability=getattr(rec, "meta_trade_probability", None),
            meta_gate_applied=bool(getattr(rec, "meta_gate_applied", False)),
            meta_trade_threshold=getattr(rec, "meta_trade_threshold", None),
            meta_threshold_scope=getattr(rec, "meta_threshold_scope", None),
            no_trade_reason=getattr(rec, "no_trade_reason", None),
            rationale=getattr(rec, "rationale", None),
            data_complete=bool(getattr(rec, "data_complete", True)),
            base_price=rec.last_price,
        )
        db.add(row)
        db.flush()
        return row


def persist_current_recommendations(db: Session) -> int:
    from app.db.models import PortfolioPositionORM
    from app.services.recommendation_engine import build_all_recommendations

    held = set(db.scalars(
        select(PortfolioPositionORM.asset_id).where(PortfolioPositionORM.quantity > 0)
    ).all())
    inserted = 0
    with _journal_lock:
        for rec in build_all_recommendations(db):
            before = (
                _latest_record(db, rec.asset_id, rec.snapshot_at)
                if rec.snapshot_at is not None else None
            )
            saved = persist_recommendation(db, rec, has_position=rec.asset_id in held)
            inserted += int(saved is not None and (before is None or saved.id != before.id))
        # Commit wewnątrz blokady zamyka okno, w którym równoległe żądanie
        # mogłoby jeszcze nie widzieć właśnie utworzonej rewizji.
        db.commit()
    return inserted


def _future_daily_closes(db: Session, row: RecommendationRecordORM) -> list[float]:
    # MAX(id) wybiera najnowszy zapis, gdy provider pozostawi kilka świec dnia.
    latest_per_day = (
        select(
            func.date(PricePointORM.timestamp).label("day"),
            func.max(PricePointORM.id).label("price_id"),
        )
        .where(
            PricePointORM.asset_id == row.asset_id,
            func.date(PricePointORM.timestamp) > row.snapshot_at.date(),
        )
        .group_by(func.date(PricePointORM.timestamp))
        .order_by(func.date(PricePointORM.timestamp).asc())
        .limit(20)
        .subquery()
    )
    return [float(value) for value in db.scalars(
        select(PricePointORM.close)
        .join(latest_per_day, PricePointORM.id == latest_per_day.c.price_id)
        .order_by(latest_per_day.c.day.asc())
    ).all()]


def _strategy_net_return(action: str, gross_return: float, cost: float) -> float:
    if action == "BUY":
        return gross_return - cost
    if action == "SELL":
        return -gross_return - cost
    return 0.0


def evaluate_recommendation_outcomes(db: Session, limit: int = 500) -> int:
    # Każdy horyzont ma osobną kolejkę. Poprzednio wybór rekordów wyłącznie
    # przez brak wyniku 20d powodował, że setki starych rewizji czekających na
    # dwadzieścia sesji blokowały gotowe już wyniki 1d i 5d.
    per_horizon_limit = max(1, limit // len(HORIZONS))
    changed_rows: dict[int, RecommendationRecordORM] = {}
    closes_cache: dict[int, list[float]] = {}

    for horizon in HORIZONS:
        realized_name = f"realized_return_{horizon}d_pct"
        strategy_name = f"strategy_net_return_{horizon}d_pct"
        pending_column = getattr(RecommendationRecordORM, realized_name)
        rows = db.scalars(
            select(RecommendationRecordORM)
            .where(pending_column.is_(None))
            # Dla tej samej świecy najpierw oceniamy końcową rewizję, bo to
            # ona zasila monitoring live i jest pokazywana jako stan sesji.
            .order_by(
                RecommendationRecordORM.snapshot_at.asc(),
                RecommendationRecordORM.revision.desc(),
                RecommendationRecordORM.created_at.desc(),
            )
            .limit(per_horizon_limit)
        ).all()
        for row in rows:
            if not row.base_price or row.base_price <= 0:
                row.quality_flag = "missing_base_price"
                continue
            closes = closes_cache.get(row.id)
            if closes is None:
                closes = _future_daily_closes(db, row)
                closes_cache[row.id] = closes
            if len(closes) < horizon:
                continue
            gross = (closes[horizon - 1] / row.base_price - 1.0) * 100.0
            setattr(row, realized_name, round(gross, 6))
            setattr(
                row,
                strategy_name,
                round(_strategy_net_return(row.action, gross, row.transaction_cost_pct), 6),
            )
            row.evaluated_at = datetime.now(timezone.utc)
            changed_rows[row.id] = row

    for row in changed_rows.values():
        # Flagi jakości są przeliczane po uzupełnieniu wszystkich dojrzałych
        # horyzontów danego rekordu w bieżącym przebiegu.
        if row.realized_return_1d_pct is not None and abs(row.realized_return_1d_pct) > 35:
            row.quality_flag = "possible_corporate_action_1d"
        elif row.realized_return_5d_pct is not None and abs(row.realized_return_5d_pct) > 60:
            row.quality_flag = "possible_corporate_action_5d"
        elif row.realized_return_20d_pct is not None and abs(row.realized_return_20d_pct) > 100:
            row.quality_flag = "possible_corporate_action_20d"

    db.commit()
    return len(changed_rows)


def list_recommendation_records(
    db: Session,
    *,
    limit: int = 200,
    asset_id: str | None = None,
) -> list[RecommendationRecordORM]:
    stmt = select(RecommendationRecordORM)
    if asset_id:
        stmt = stmt.where(RecommendationRecordORM.asset_id == asset_id)
    return list(db.scalars(
        stmt.order_by(
            RecommendationRecordORM.snapshot_at.desc(),
            RecommendationRecordORM.revision.desc(),
            RecommendationRecordORM.created_at.desc(),
        ).limit(min(max(limit, 1), 1000))
    ).all())
