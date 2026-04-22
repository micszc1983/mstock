from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class AssetORM(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(32), index=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD", server_default="USD")
    sector: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Konfiguracja providera — wcześniej w settings.asset_provider_config
    # Przechowywana w DB, żeby aktywa można było dodawać z UI
    price_symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    news_symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    news_term: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    metal_price_fn: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    prices: Mapped[List["PricePointORM"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    news_items: Mapped[List["NewsItemORM"]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class PricePointORM(Base):
    __tablename__ = "price_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)

    asset: Mapped["AssetORM"] = relationship(back_populates="prices")


class NewsItemORM(Base):
    __tablename__ = "news_items"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    sentiment_score: Mapped[float] = mapped_column(Float)
    impact_score: Mapped[float] = mapped_column(Float)

    asset: Mapped["AssetORM"] = relationship(back_populates="news_items")
    narratives: Mapped[List["NewsNarrativeORM"]] = relationship(back_populates="news_item", cascade="all, delete-orphan")


class NewsNarrativeORM(Base):
    __tablename__ = "news_narratives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_id: Mapped[str] = mapped_column(ForeignKey("news_items.id"), index=True)
    narrative_label: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float)

    news_item: Mapped["NewsItemORM"] = relationship(back_populates="narratives")


class SyncLogORM(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(64), index=True)
    sync_type: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(128))
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), index=True)
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)



class DailyAssetFeatureORM(Base):
    __tablename__ = "daily_asset_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(64), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_price: Mapped[float] = mapped_column(Float)
    price_change_1d_pct: Mapped[float] = mapped_column(Float)
    price_change_5d_pct: Mapped[float] = mapped_column(Float)
    price_change_20d_pct: Mapped[float] = mapped_column(Float)
    trend_score: Mapped[float] = mapped_column(Float)
    sentiment_score: Mapped[float] = mapped_column(Float)
    narrative_shift_score: Mapped[float] = mapped_column(Float)
    divergence_score: Mapped[float] = mapped_column(Float)
    fragility_score: Mapped[float] = mapped_column(Float)
    regime_label: Mapped[str] = mapped_column(String(64), index=True)
    regime_confidence: Mapped[float] = mapped_column(Float)
    dominant_narrative: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    volatility_10d: Mapped[float] = mapped_column(Float)
    momentum_20d: Mapped[float] = mapped_column(Float)
    news_count_7d: Mapped[int] = mapped_column(Integer, default=0)
    implied_volatility: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    put_call_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    iv_rank: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class ForecastORM(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(64), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    horizon: Mapped[str] = mapped_column(String(16), index=True)
    direction: Mapped[str] = mapped_column(String(16))
    up_probability: Mapped[float] = mapped_column(Float)
    down_probability: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    expected_return_pct: Mapped[float] = mapped_column(Float)
    expected_range_low: Mapped[float] = mapped_column(Float)
    expected_range_high: Mapped[float] = mapped_column(Float)
    model_name: Mapped[str] = mapped_column(String(64))
    regime_label: Mapped[str] = mapped_column(String(64), index=True)


class ThesisORM(Base):
    __tablename__ = "theses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(64), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    regime: Mapped[str] = mapped_column(String(64), index=True)
    regime_confidence: Mapped[float] = mapped_column(Float)
    dominant_narrative: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    thesis_confidence: Mapped[float] = mapped_column(Float)
    fragility_score: Mapped[float] = mapped_column(Float)
    divergence_score: Mapped[float] = mapped_column(Float)
    thesis: Mapped[str] = mapped_column(Text)
    anti_thesis: Mapped[str] = mapped_column(Text)
    support_factors_json: Mapped[str] = mapped_column(Text)
    risk_factors_json: Mapped[str] = mapped_column(Text)
    invalidation_conditions_json: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(64), default="thesis_v1")


class ThesisOutcomeORM(Base):
    __tablename__ = "thesis_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thesis_id: Mapped[int] = mapped_column(ForeignKey("theses.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    horizon: Mapped[str] = mapped_column(String(16), index=True)
    base_price: Mapped[float] = mapped_column(Float)
    realized_price: Mapped[float] = mapped_column(Float)
    realized_return_pct: Mapped[float] = mapped_column(Float)
    was_directionally_correct: Mapped[bool] = mapped_column(Boolean)
    outcome_label: Mapped[str] = mapped_column(String(32), index=True)


class NewsNLPRunORM(Base):
    __tablename__ = "news_nlp_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_id: Mapped[str] = mapped_column(ForeignKey("news_items.id"), index=True)
    model_name: Mapped[str] = mapped_column(String(64), index=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sentiment_score: Mapped[float] = mapped_column(Float)
    sentiment_label: Mapped[str] = mapped_column(String(32), index=True)
    sentiment_confidence: Mapped[float] = mapped_column(Float)
    relevance_score: Mapped[float] = mapped_column(Float)
    raw_output_json: Mapped[str] = mapped_column(Text)

class NewsNarrativePredictionORM(Base):
    __tablename__ = "news_narrative_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_id: Mapped[str] = mapped_column(ForeignKey("news_items.id"), index=True)
    model_name: Mapped[str] = mapped_column(String(64), index=True)
    narrative_label: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)

class AlertORM(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), index=True)
    trigger_value: Mapped[float] = mapped_column(Float)
    threshold_value: Mapped[float] = mapped_column(Float)
    snapshot_json: Mapped[str] = mapped_column(Text)

class AlertRuleORM(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_name: Mapped[str] = mapped_column(String(128), index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    asset_scope: Mapped[str] = mapped_column(String(128), index=True)
    threshold_json: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60)


class WatchlistORM(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

class WatchlistItemORM(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

class UserPreferenceORM(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    preference_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    preference_value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

class NotificationChannelORM(Base):
    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_type: Mapped[str] = mapped_column(String(32), index=True)
    target: Mapped[str] = mapped_column(String(255), index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    label: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

class NotificationEventORM(Base):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("notification_channels.id"), index=True)
    asset_id: Mapped[Optional[str]] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MLTrainingRowORM(Base):
    __tablename__ = "ml_training_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    feature_json: Mapped[str] = mapped_column(Text)
    target_up_1d: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_up_5d: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_up_20d: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_return_1d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_return_5d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_return_20d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_thesis_success: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

class MLModelRunORM(Base):
    __tablename__ = "ml_model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(128), index=True)
    target_name: Mapped[str] = mapped_column(String(64), index=True)
    asset_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    dataset_rows: Mapped[int] = mapped_column(Integer)
    metrics_json: Mapped[str] = mapped_column(Text)
    model_path: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

class MLBacktestResultORM(Base):
    __tablename__ = "ml_backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("ml_model_runs.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    result_json: Mapped[str] = mapped_column(Text)

class MLPredictionORM(Base):
    __tablename__ = "ml_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("ml_model_runs.id"), index=True)
    target_name: Mapped[str] = mapped_column(String(64), index=True)
    probability_up: Mapped[float] = mapped_column(Float)
    predicted_label: Mapped[str] = mapped_column(String(32), index=True)
    raw_json: Mapped[str] = mapped_column(Text)

class MLSettingORM(Base):
    __tablename__ = "ml_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    setting_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    setting_value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class HeuristicVsMLComparisonORM(Base):
    __tablename__ = "heuristic_vs_ml_comparisons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    heuristic_accuracy_5d: Mapped[float] = mapped_column(Float)
    ml_accuracy_5d: Mapped[float] = mapped_column(Float)
    heuristic_avg_return_5d: Mapped[float] = mapped_column(Float)
    ml_avg_return_5d: Mapped[float] = mapped_column(Float)
    better_mode: Mapped[str] = mapped_column(String(32), index=True)
    sample_size: Mapped[int] = mapped_column(Integer)

class DecisionSnapshotORM(Base):
    __tablename__ = "decision_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    conviction_score: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float)
    timing_score: Mapped[float] = mapped_column(Float)
    setup_quality_score: Mapped[float] = mapped_column(Float)

    bullish_strength: Mapped[float] = mapped_column(Float)
    bearish_pressure: Mapped[float] = mapped_column(Float)
    net_thesis_edge: Mapped[float] = mapped_column(Float)

    action_label: Mapped[str] = mapped_column(String(64), index=True)

    confidence_breakdown_json: Mapped[str] = mapped_column(Text)
    scenario_base_json: Mapped[str] = mapped_column(Text)
    scenario_bull_json: Mapped[str] = mapped_column(Text)
    scenario_bear_json: Mapped[str] = mapped_column(Text)
    change_summary_json: Mapped[str] = mapped_column(Text)
    position_sizing_json: Mapped[str] = mapped_column(Text)
    cross_asset_confirmation_json: Mapped[str] = mapped_column(Text)
    regime_memory_json: Mapped[str] = mapped_column(Text)

    macro_pressure_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    relative_strength_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    company_risk_stack_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class PortfolioPositionORM(Base):
    __tablename__ = "portfolio_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), unique=True, index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    avg_buy_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow())


class EnsembleRecordORM(Base):
    __tablename__ = "ensemble_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    mode: Mapped[str] = mapped_column(String(32), index=True)
    heuristic_direction: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    ml_direction: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    ensemble_direction: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    heuristic_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ml_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ensemble_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # Outcome — wypełniany przez outcome evaluator
    actual_return_5d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    heuristic_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ml_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ensemble_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    winner: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
