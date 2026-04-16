from __future__ import annotations

import json

from app.db.models import (
    AssetORM,
    DailyAssetFeatureORM,
    ForecastORM,
    NewsItemORM,
    PricePointORM,
    SyncLogORM,
    ThesisORM,
    ThesisOutcomeORM,
    AlertORM,
    AlertRuleORM,
    NewsNLPRunORM,
    NewsNarrativePredictionORM,
)
from app.schemas.asset import Asset, PricePoint
from app.schemas.alerts import AlertResponse, AlertRuleResponse
from app.schemas.features import DailyAssetFeatureSnapshot, ForecastResponse
from app.schemas.news import NewsItem
from app.schemas.nlp import NewsNLPResponse, NewsNarrativePredictionResponse
from app.schemas.outcomes import ThesisOutcomeResponse
from app.schemas.sync import SyncLogResponse
from app.schemas.thesis import StoredThesisResponse


def asset_to_schema(row: AssetORM) -> Asset:
    return Asset(
        id=row.id,
        symbol=row.symbol,
        name=row.name,
        type=row.type,
        currency=getattr(row, "currency", "USD") or "USD",
        sector=row.sector,
        description=row.description,
        price_symbol=row.price_symbol,
        news_symbol=row.news_symbol,
        news_term=row.news_term,
        metal_price_fn=row.metal_price_fn,
    )


def price_to_schema(row: PricePointORM) -> PricePoint:
    return PricePoint(
        timestamp=row.timestamp,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
    )


def news_to_schema(row: NewsItemORM) -> NewsItem:
    return NewsItem(
        id=row.id,
        asset_id=row.asset_id,
        published_at=row.published_at,
        source=row.source,
        title=row.title,
        body=row.body,
        sentiment_score=row.sentiment_score,
        impact_score=row.impact_score,
        narratives={n.narrative_label: n.score for n in row.narratives},
    )


def sync_log_to_schema(row: SyncLogORM) -> SyncLogResponse:
    return SyncLogResponse(
        id=row.id,
        asset_id=row.asset_id,
        sync_type=row.sync_type,
        provider=row.provider,
        inserted=row.inserted,
        skipped=row.skipped,
        status=row.status,
        detail=row.detail,
        created_at=row.created_at,
    )


def feature_to_schema(row: DailyAssetFeatureORM) -> DailyAssetFeatureSnapshot:
    return DailyAssetFeatureSnapshot(
        asset_id=row.asset_id,
        snapshot_at=row.snapshot_at,
        last_price=row.last_price,
        price_change_1d_pct=row.price_change_1d_pct,
        price_change_5d_pct=row.price_change_5d_pct,
        price_change_20d_pct=row.price_change_20d_pct,
        trend_score=row.trend_score,
        sentiment_score=row.sentiment_score,
        narrative_shift_score=row.narrative_shift_score,
        divergence_score=row.divergence_score,
        fragility_score=row.fragility_score,
        regime_label=row.regime_label,
        regime_confidence=row.regime_confidence,
        dominant_narrative=row.dominant_narrative,
        volatility_10d=row.volatility_10d,
        momentum_20d=row.momentum_20d,
        news_count_7d=row.news_count_7d,
    )


def forecast_to_schema(row: ForecastORM) -> ForecastResponse:
    return ForecastResponse(
        asset_id=row.asset_id,
        horizon=row.horizon,
        generated_at=row.generated_at,
        direction=row.direction,
        up_probability=row.up_probability,
        down_probability=row.down_probability,
        confidence=row.confidence,
        expected_return_pct=row.expected_return_pct,
        expected_range_low=row.expected_range_low,
        expected_range_high=row.expected_range_high,
        model_name=row.model_name,
        regime_label=row.regime_label,
    )


def thesis_to_schema(row: ThesisORM) -> StoredThesisResponse:
    return StoredThesisResponse(
        id=row.id,
        asset_id=row.asset_id,
        generated_at=row.generated_at,
        source_snapshot_at=row.source_snapshot_at,
        regime=row.regime,
        regime_confidence=row.regime_confidence,
        dominant_narrative=row.dominant_narrative,
        thesis_confidence=row.thesis_confidence,
        fragility_score=row.fragility_score,
        divergence_score=row.divergence_score,
        thesis=row.thesis,
        anti_thesis=row.anti_thesis,
        support_factors=json.loads(row.support_factors_json),
        risk_factors=json.loads(row.risk_factors_json),
        invalidation_conditions=json.loads(row.invalidation_conditions_json),
        model_name=row.model_name,
    )


def thesis_outcome_to_schema(row: ThesisOutcomeORM) -> ThesisOutcomeResponse:
    return ThesisOutcomeResponse(
        thesis_id=row.thesis_id,
        asset_id=row.asset_id,
        evaluated_at=row.evaluated_at,
        horizon=row.horizon,
        base_price=row.base_price,
        realized_price=row.realized_price,
        realized_return_pct=row.realized_return_pct,
        was_directionally_correct=row.was_directionally_correct,
        outcome_label=row.outcome_label,
    )


def alert_to_schema(row: AlertORM) -> AlertResponse:
    return AlertResponse(
        id=row.id,
        asset_id=row.asset_id,
        created_at=row.created_at,
        alert_type=row.alert_type,
        severity=row.severity,
        title=row.title,
        message=row.message,
        status=row.status,
        trigger_value=row.trigger_value,
        threshold_value=row.threshold_value,
        snapshot_json=row.snapshot_json,
    )

def alert_rule_to_schema(row: AlertRuleORM) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=row.id,
        rule_name=row.rule_name,
        is_enabled=row.is_enabled,
        alert_type=row.alert_type,
        asset_scope=row.asset_scope,
        threshold_json=row.threshold_json,
        severity=row.severity,
        cooldown_minutes=row.cooldown_minutes,
    )

def news_nlp_to_schema(run: NewsNLPRunORM, preds: list[NewsNarrativePredictionORM]) -> NewsNLPResponse:
    return NewsNLPResponse(
        news_id=run.news_id,
        model_name=run.model_name,
        processed_at=run.processed_at,
        sentiment_score=run.sentiment_score,
        sentiment_label=run.sentiment_label,
        sentiment_confidence=run.sentiment_confidence,
        relevance_score=run.relevance_score,
        raw_output_json=run.raw_output_json,
        narratives=[
            NewsNarrativePredictionResponse(
                news_id=p.news_id,
                model_name=p.model_name,
                narrative_label=p.narrative_label,
                score=p.score,
                confidence=p.confidence,
            )
            for p in preds
        ],
    )


from app.schemas.ml import MLBacktestResponse, MLModelRunResponse, MLPredictionResponse

def ml_model_run_to_schema(row: MLModelRunORM) -> MLModelRunResponse:
    return MLModelRunResponse(
        id=row.id,
        model_name=row.model_name,
        target_name=row.target_name,
        trained_at=row.trained_at,
        dataset_rows=row.dataset_rows,
        metrics_json=row.metrics_json,
        model_path=row.model_path,
        is_active=row.is_active,
    )

def ml_backtest_to_schema(row: MLBacktestResultORM) -> MLBacktestResponse:
    return MLBacktestResponse(
        model_run_id=row.model_run_id,
        created_at=row.created_at,
        result_json=row.result_json,
    )

def ml_prediction_to_schema(row: MLPredictionORM) -> MLPredictionResponse:
    return MLPredictionResponse(
        asset_id=row.asset_id,
        snapshot_at=row.snapshot_at,
        model_run_id=row.model_run_id,
        target_name=row.target_name,
        probability_up=row.probability_up,
        predicted_label=row.predicted_label,
        raw_json=row.raw_json,
    )


from app.schemas.evaluation import StrategyComparisonResponse, WalkForwardBacktestResponse

def walkforward_backtest_to_schema(row: MLBacktestResultORM) -> WalkForwardBacktestResponse:
    return WalkForwardBacktestResponse(
        model_run_id=row.model_run_id,
        created_at=row.created_at,
        result_json=row.result_json,
    )

def strategy_comparison_to_schema(row: HeuristicVsMLComparisonORM) -> StrategyComparisonResponse:
    return StrategyComparisonResponse(
        asset_id=row.asset_id,
        heuristic_accuracy_5d=row.heuristic_accuracy_5d,
        ml_accuracy_5d=row.ml_accuracy_5d,
        heuristic_avg_return_5d=row.heuristic_avg_return_5d,
        ml_avg_return_5d=row.ml_avg_return_5d,
        better_mode=row.better_mode,
        sample_size=row.sample_size,
    )

from app.schemas.decision_support import DecisionSnapshotResponse, ConfidenceContribution, ScenarioBlock, ChangeItem, PositionSizingResponse, CrossAssetSignal, RegimeMemoryItem, MacroPressureResponse, RelativeStrengthResponse, CompanyRiskStackResponse


def decision_snapshot_to_schema(row: DecisionSnapshotORM) -> DecisionSnapshotResponse:
    import json
    return DecisionSnapshotResponse(
        asset_id=row.asset_id,
        snapshot_at=row.snapshot_at,
        conviction_score=row.conviction_score,
        risk_score=row.risk_score,
        timing_score=row.timing_score,
        setup_quality_score=row.setup_quality_score,
        bullish_strength=row.bullish_strength,
        bearish_pressure=row.bearish_pressure,
        net_thesis_edge=row.net_thesis_edge,
        action_label=row.action_label,
        confidence_breakdown=[ConfidenceContribution(**item) for item in json.loads(row.confidence_breakdown_json)],
        scenario_base=ScenarioBlock(**json.loads(row.scenario_base_json)),
        scenario_bull=ScenarioBlock(**json.loads(row.scenario_bull_json)),
        scenario_bear=ScenarioBlock(**json.loads(row.scenario_bear_json)),
        change_summary=[ChangeItem(**item) for item in json.loads(row.change_summary_json)],
        position_sizing=PositionSizingResponse(**json.loads(row.position_sizing_json)),
        cross_asset_confirmation=[CrossAssetSignal(**item) for item in json.loads(row.cross_asset_confirmation_json)],
        regime_memory=[RegimeMemoryItem(**item) for item in json.loads(row.regime_memory_json)],
        macro_pressure=MacroPressureResponse(**json.loads(row.macro_pressure_json)) if row.macro_pressure_json else None,
        relative_strength=RelativeStrengthResponse(**json.loads(row.relative_strength_json)) if row.relative_strength_json else None,
        company_risk_stack=CompanyRiskStackResponse(**json.loads(row.company_risk_stack_json)) if row.company_risk_stack_json else None,
    )
