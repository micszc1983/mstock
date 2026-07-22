from __future__ import annotations

from datetime import datetime, date, timezone
from typing import List, Optional
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    title: Mapped[str] = mapped_column(Text)
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
    target_triple_barrier: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_meta_label: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    triple_barrier_return_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    triple_barrier_hit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    meta_side: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    meta_strategy_return_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_segment: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    market_regime: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    meta_primary_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta_primary_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta_model_disagreement: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta_label_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

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
    deployment_role: Mapped[str] = mapped_column(String(16), default="candidate", server_default="candidate", index=True)
    promotion_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    market_segment: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)


class MLModelMonitorORM(Base):
    __tablename__ = "ml_model_monitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("ml_model_runs.id"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    asset_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    market_segment: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    feature_psi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    calibration_error: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recent_avg_net_return_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recent_profit_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", index=True)
    action: Mapped[str] = mapped_column(String(32), default="keep", server_default="keep", index=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")

class MLBacktestResultORM(Base):
    __tablename__ = "ml_backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("ml_model_runs.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    result_json: Mapped[str] = mapped_column(Text)

class MLPredictionORM(Base):
    __tablename__ = "ml_predictions"
    __table_args__ = (
        UniqueConstraint("asset_id", "snapshot_at", "target_name", name="uq_ml_prediction_snapshot"),
    )

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
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


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


class EarningsORM(Base):
    __tablename__ = "earnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    fiscal_period: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)   # np. "2025Q1"
    eps_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eps_actual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue_actual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eps_surprise_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # (actual-est)/|est|*100
    surprise_label: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)   # BEAT|MISS|MEET
    is_upcoming: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class InsiderTradeORM(Base):
    __tablename__ = "insider_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    filing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    transaction_code: Mapped[str] = mapped_column(String(4))      # P=buy S=sell M=exercise etc.
    transaction_type: Mapped[str] = mapped_column(String(20))     # buy|sell|other
    shares: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="finnhub")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ShortInterestORM(Base):
    __tablename__ = "short_interest"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    shares_short: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    short_percent_float: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    short_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class IntradayCandleORM(Base):
    __tablename__ = "intraday_candles"
    __table_args__ = (
        UniqueConstraint("asset_id", "resolution", "timestamp", name="uq_intraday_candle"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    resolution: Mapped[str] = mapped_column(String(8), index=True)       # "15" | "60"
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    # Wskaźniki techniczne obliczone dla tej świecy
    rsi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ema9: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ema20: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    macd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    macd_signal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bb_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bb_lower: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # vol / avg20vol
    vwap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)          # Volume Weighted Avg Price (reset per day)
    adx: Mapped[Optional[float]] = mapped_column(Float, nullable=True)           # Average Directional Index (trend strength)
    di_plus: Mapped[Optional[float]] = mapped_column(Float, nullable=True)       # +DI (directional movement up)
    di_minus: Mapped[Optional[float]] = mapped_column(Float, nullable=True)      # -DI (directional movement down)


class EarningsCallAnalysisORM(Base):
    __tablename__ = "earnings_call_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    earnings_id: Mapped[int] = mapped_column(ForeignKey("earnings.id"), unique=True, index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    tone_score: Mapped[int] = mapped_column(Integer)            # 1–5 (1=bardzo niedźwiedzi, 5=bardzo bycze)
    guidance_change: Mapped[str] = mapped_column(String(16))    # raised/lowered/maintained/none
    key_themes_json: Mapped[str] = mapped_column(Text)          # JSON list[str]
    risk_factors_json: Mapped[str] = mapped_column(Text)        # JSON list[str]
    key_quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_sentiment_score: Mapped[float] = mapped_column(Float)   # -100 do +100
    summary: Mapped[str] = mapped_column(Text)
    model_used: Mapped[str] = mapped_column(String(64))
    news_articles_used: Mapped[int] = mapped_column(Integer, default=0)


class IntradayBacktestORM(Base):
    __tablename__ = "intraday_backtests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    resolution: Mapped[str] = mapped_column(String(8), default="15")
    run_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    lookback_days: Mapped[int] = mapped_column(Integer, default=30)
    candles_count: Mapped[int] = mapped_column(Integer, default=0)
    total_signals: Mapped[int] = mapped_column(Integer, default=0)
    win_count: Mapped[int] = mapped_column(Integer, default=0)
    loss_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout_count: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_win_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_loss_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_return_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_return_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expectancy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Calibrated thresholds (default = baseline)
    rsi_oversold: Mapped[float] = mapped_column(Float, default=32.0)
    rsi_overbought: Mapped[float] = mapped_column(Float, default=68.0)
    sl_pct: Mapped[float] = mapped_column(Float, default=1.5)
    tp_pct: Mapped[float] = mapped_column(Float, default=2.0)
    # Baseline comparison (default params)
    default_signals: Mapped[int] = mapped_column(Integer, default=0)
    default_win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    default_expectancy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trades_json: Mapped[str] = mapped_column(Text, default="[]")
    initial_capital: Mapped[float] = mapped_column(Float, default=10000.0)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")


class AnomalyScoreORM(Base):
    __tablename__ = "anomaly_scores"
    __table_args__ = (
        UniqueConstraint("asset_id", "scored_at", name="uq_anomaly_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    anomaly_score: Mapped[float] = mapped_column(Float)           # 0-100, 100 = najbardziej anomalny
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    trained_on_rows: Mapped[int] = mapped_column(Integer, default=0)
    top_features_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[{feature,value,median,z_score}]
    raw_response: Mapped[str] = mapped_column(Text, default="")


class PaperAccountORM(Base):
    __tablename__ = "paper_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    initial_cash: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaperPositionORM(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("account_id", "asset_id", name="uq_paper_position"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaperOrderORM(Base):
    __tablename__ = "paper_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    side: Mapped[str] = mapped_column(String(8), index=True)
    order_type: Mapped[str] = mapped_column(String(16), default="market")
    quantity: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reference_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fill_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    slippage: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str] = mapped_column(Text, default="")


class PaperTradeORM(Base):
    __tablename__ = "paper_trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("paper_orders.id"), unique=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    gross_value: Mapped[float] = mapped_column(Float)
    costs: Mapped[float] = mapped_column(Float)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RecommendationRecordORM(Base):
    """Niezmienny dziennik decyzji modelu i ich późniejszych rezultatów."""

    __tablename__ = "recommendation_records"
    __table_args__ = (
        UniqueConstraint(
            "asset_id", "snapshot_at", "model_version",
            name="uq_recommendation_record_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    model_version: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(16), index=True)
    regime: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(16), index=True)
    displayed_action: Mapped[str] = mapped_column(String(32), index=True)
    has_position: Mapped[bool] = mapped_column(Boolean, default=False)
    calibration_scope: Mapped[str] = mapped_column(String(32))
    calibration_sample_size: Mapped[int] = mapped_column(Integer)
    composite_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    probability_buy: Mapped[float] = mapped_column(Float)
    probability_sell: Mapped[float] = mapped_column(Float)
    probability_no_trade: Mapped[float] = mapped_column(Float)
    buy_threshold: Mapped[float] = mapped_column(Float)
    sell_threshold: Mapped[float] = mapped_column(Float)
    transaction_cost_pct: Mapped[float] = mapped_column(Float)
    expected_gross_edge_pct: Mapped[float] = mapped_column(Float)
    expected_net_edge_pct: Mapped[float] = mapped_column(Float)
    uncertainty_pct: Mapped[float] = mapped_column(Float)
    meta_trade_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta_gate_applied: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    meta_trade_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta_threshold_scope: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    base_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quality_flag: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    realized_return_1d_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    realized_return_5d_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    realized_return_20d_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strategy_net_return_1d_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strategy_net_return_5d_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strategy_net_return_20d_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class RecommendationAuditRunORM(Base):
    """Wersjonowany wynik audytu walk-forward, przeznaczony do porównań w czasie."""

    __tablename__ = "recommendation_audit_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    model_version: Mapped[str] = mapped_column(String(32), index=True)
    dataset_rows: Mapped[int] = mapped_column(Integer)
    eligible_rows: Mapped[int] = mapped_column(Integer)
    excluded_outliers: Mapped[int] = mapped_column(Integer)
    fold_count: Mapped[int] = mapped_column(Integer)
    embargo_sessions: Mapped[int] = mapped_column(Integer)
    result_json: Mapped[str] = mapped_column(Text)
