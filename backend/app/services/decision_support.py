from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.mappers import decision_snapshot_to_schema
from app.repositories.assets import get_asset
from app.repositories.decision_support import (
    delete_decision_snapshot_for_timestamp,
    get_latest_decision_snapshot,
    insert_decision_snapshot,
)
from app.repositories.features import get_latest_feature_snapshot, list_feature_history
from app.repositories.forecasts import get_latest_forecasts
from app.schemas.decision_support import (
    ChangeItem,
    CompanyRiskStackResponse,
    ConfidenceContribution,
    CrossAssetSignal,
    DecisionSnapshotResponse,
    MacroPressureResponse,
    PositionSizingResponse,
    RegimeMemoryItem,
    RelativeStrengthResponse,
    ScenarioBlock,
)
from app.utils.datetime import ensure_utc, now_utc
from app.core.config import weights as W


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 2)


def build_decision_snapshot(db: Session, asset_id: str) -> DecisionSnapshotResponse | None:
    asset = get_asset(db, asset_id)
    feature = get_latest_feature_snapshot(db, asset_id)
    if asset is None or feature is None:
        return None

    forecasts = get_latest_forecasts(db, asset_id)
    forecast_1d = next((f for f in forecasts if f.horizon == "1d"), forecasts[0] if forecasts else None)
    history = list_feature_history(db, asset_id, limit=2)
    previous = history[1] if len(history) > 1 else None

    conviction = _clamp(feature.trend_score * W.CONVICTION_TREND_W + feature.sentiment_score * W.CONVICTION_SENTIMENT_W + (forecast_1d.confidence if forecast_1d else 50.0) * W.CONVICTION_FORECAST_W)
    risk = _clamp(feature.fragility_score * W.RISK_FRAGILITY_W + feature.divergence_score * W.RISK_DIVERGENCE_W)
    timing = _clamp(feature.trend_score * 0.5 + (100 - feature.fragility_score) * 0.3 + (forecast_1d.up_probability if forecast_1d else 50.0) * 0.2)
    setup_quality = _clamp(conviction * 0.5 + (100 - risk) * 0.5)
    bullish = _clamp(feature.trend_score * 0.45 + feature.sentiment_score * 0.2 + (forecast_1d.up_probability if forecast_1d else 50.0) * 0.35)
    bearish = _clamp(feature.fragility_score * 0.35 + feature.divergence_score * 0.25 + (forecast_1d.down_probability if forecast_1d else 50.0) * 0.4)
    net_edge = round(bullish - bearish, 2)

    if conviction >= 70 and risk < 45:
        action = "candidate_for_entry"
    elif risk >= 70:
        action = "high_risk_avoid"
    elif net_edge < -10:
        action = "thesis_weakening"
    elif conviction >= 50:
        action = "watch_closely"
    else:
        action = "monitor"

    change_summary = []
    if previous is not None:
        change_summary = [
            ChangeItem(metric="trend_score", previous=f"{previous.trend_score:.2f}", current=f"{feature.trend_score:.2f}", delta=f"{feature.trend_score-previous.trend_score:+.2f}", interpretation="trend change"),
            ChangeItem(metric="sentiment_score", previous=f"{previous.sentiment_score:.2f}", current=f"{feature.sentiment_score:.2f}", delta=f"{feature.sentiment_score-previous.sentiment_score:+.2f}", interpretation="sentiment change"),
            ChangeItem(metric="fragility_score", previous=f"{previous.fragility_score:.2f}", current=f"{feature.fragility_score:.2f}", delta=f"{feature.fragility_score-previous.fragility_score:+.2f}", interpretation="risk change"),
        ]

    macro = None
    rel = None
    company = None
    if asset_id in {"gold", "silver"}:
        macro = MacroPressureResponse(
            usd_pressure=_clamp(50 + feature.divergence_score * 0.2),
            real_yield_pressure=_clamp(45 + feature.fragility_score * 0.15),
            safe_haven_demand=_clamp(55 + feature.sentiment_score * 0.2),
            central_bank_buying=_clamp(52 + feature.trend_score * 0.15),
            inflation_hedge_support=_clamp(48 + feature.narrative_shift_score * 0.1),
            summary="Macro pressure monitor for precious metals.",
        )
        rel = RelativeStrengthResponse(
            ratio_name=f"{asset_id}/peer",
            value=round(feature.last_price, 4),
            interpretation="Relative strength proxy for precious metals.",
        )
    else:
        company = CompanyRiskStackResponse(
            valuation_pressure=_clamp(55 + feature.divergence_score * 0.25),
            earnings_sensitivity=_clamp(50 + feature.fragility_score * 0.2),
            regulation_risk=_clamp(35 + feature.narrative_shift_score * 0.15),
            competition_pressure=_clamp(45 + (100 - feature.trend_score) * 0.15),
            product_cycle_strength=_clamp(55 + feature.trend_score * 0.2 - feature.fragility_score * 0.1),
            summary="Company-specific decision risk stack.",
        )

    return DecisionSnapshotResponse(
        asset_id=asset_id,
        snapshot_at=ensure_utc(feature.snapshot_at),
        conviction_score=conviction,
        risk_score=risk,
        timing_score=timing,
        setup_quality_score=setup_quality,
        bullish_strength=bullish,
        bearish_pressure=bearish,
        net_thesis_edge=net_edge,
        action_label=action,
        confidence_breakdown=[
            ConfidenceContribution(name="trend contribution", contribution=round(feature.trend_score * 0.35, 2)),
            ConfidenceContribution(name="sentiment contribution", contribution=round(feature.sentiment_score * 0.25, 2)),
            ConfidenceContribution(name="forecast contribution", contribution=round((forecast_1d.confidence if forecast_1d else 50.0) * 0.15, 2)),
            ConfidenceContribution(name="divergence penalty", contribution=round(-feature.divergence_score * 0.12, 2)),
            ConfidenceContribution(name="fragility penalty", contribution=round(-feature.fragility_score * 0.18, 2)),
        ],
        scenario_base=ScenarioBlock(title="Base case", summary=f"{asset.name}: continuation of current regime.", drivers=[feature.regime_label, str(feature.dominant_narrative)]),
        scenario_bull=ScenarioBlock(title="Bull case", summary=f"{asset.name}: stronger upside with improving sentiment.", drivers=["trend remains constructive", "sentiment expands"]),
        scenario_bear=ScenarioBlock(title="Bear case", summary=f"{asset.name}: downside if fragility and divergence rise.", drivers=["fragility rises", "forecast weakens"]),
        change_summary=change_summary,
        position_sizing=PositionSizingResponse(
            suggested_size_label="large" if conviction - risk > 30 else "medium" if conviction - risk > 10 else "small" if conviction > risk else "watch-only",
            sizing_fraction=1.0 if conviction - risk > 30 else 0.6 if conviction - risk > 10 else 0.3 if conviction > risk else 0.0,
            rationale=f"conviction={conviction:.1f}, risk={risk:.1f}",
        ),
        cross_asset_confirmation=[CrossAssetSignal(related_asset="market_proxy", relationship="cross-asset", confirmation="mixed", interpretation="Confirmation layer placeholder.")],
        regime_memory=[RegimeMemoryItem(label=f"{feature.regime_label} @ {ensure_utc(feature.snapshot_at).date()}", similarity_score=75.0, interpretation="Historically similar regime cluster.")],
        macro_pressure=macro,
        relative_strength=rel,
        company_risk_stack=company,
    )


def persist_decision_snapshot(db: Session, asset_id: str) -> DecisionSnapshotResponse | None:
    snapshot = build_decision_snapshot(db, asset_id)
    if snapshot is None:
        return None
    delete_decision_snapshot_for_timestamp(db, asset_id, snapshot.snapshot_at)
    insert_decision_snapshot(
        db,
        asset_id=snapshot.asset_id,
        snapshot_at=snapshot.snapshot_at,
        conviction_score=snapshot.conviction_score,
        risk_score=snapshot.risk_score,
        timing_score=snapshot.timing_score,
        setup_quality_score=snapshot.setup_quality_score,
        bullish_strength=snapshot.bullish_strength,
        bearish_pressure=snapshot.bearish_pressure,
        net_thesis_edge=snapshot.net_thesis_edge,
        action_label=snapshot.action_label,
        confidence_breakdown_json=json.dumps([x.model_dump() for x in snapshot.confidence_breakdown], ensure_ascii=False),
        scenario_base_json=json.dumps(snapshot.scenario_base.model_dump(), ensure_ascii=False),
        scenario_bull_json=json.dumps(snapshot.scenario_bull.model_dump(), ensure_ascii=False),
        scenario_bear_json=json.dumps(snapshot.scenario_bear.model_dump(), ensure_ascii=False),
        change_summary_json=json.dumps([x.model_dump() for x in snapshot.change_summary], ensure_ascii=False),
        position_sizing_json=json.dumps(snapshot.position_sizing.model_dump(), ensure_ascii=False),
        cross_asset_confirmation_json=json.dumps([x.model_dump() for x in snapshot.cross_asset_confirmation], ensure_ascii=False),
        regime_memory_json=json.dumps([x.model_dump() for x in snapshot.regime_memory], ensure_ascii=False),
        macro_pressure_json=json.dumps(snapshot.macro_pressure.model_dump(), ensure_ascii=False) if snapshot.macro_pressure else None,
        relative_strength_json=json.dumps(snapshot.relative_strength.model_dump(), ensure_ascii=False) if snapshot.relative_strength else None,
        company_risk_stack_json=json.dumps(snapshot.company_risk_stack.model_dump(), ensure_ascii=False) if snapshot.company_risk_stack else None,
    )
    db.commit()
    return snapshot
