from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class SignalContribution(BaseModel):
    name: str           # polska nazwa sygnału
    value: float        # surowa wartość (np. trend_score=65.2)
    normalized: float   # wkład do score [-1..+1]
    direction: str      # "bullish" | "bearish" | "neutral"


class AssetRecommendation(BaseModel):
    asset_id: str
    name: str
    symbol: str
    asset_type: str

    # Wynik główny
    recommendation: str         # "KUP" | "SPRZEDAJ" | "TRZYMAJ" | "BRAK TRANSAKCJI"
    composite_score: float      # 0-100; diagnostyczny surowy wynik sygnałów
    confidence: float           # 0-100; historycznie skalibrowane P(decyzja trafna)
    confidence_label: str       # "wysoka" | "średnia" | "niska"

    # Kalibracja segmentu i kosztów
    market_segment: str = "UNKNOWN"
    calibration_scope: str = "insufficient_data"
    calibration_sample_size: int = 0
    probability_buy: float = 0.0
    probability_sell: float = 0.0
    probability_no_trade: float = 100.0
    buy_threshold: float = 101.0
    sell_threshold: float = 101.0
    transaction_cost_pct: float = 0.0
    expected_gross_edge_pct: float = 0.0
    expected_net_edge_pct: float = 0.0
    uncertainty_pct: float = 0.0
    no_trade_reason: Optional[str] = None

    # Kluczowe sygnały
    trend_score: float
    sentiment_score: float
    fragility_score: float
    divergence_score: float
    regime: str

    forecast_dir_1d: Optional[str]
    forecast_dir_5d: Optional[str]
    forecast_dir_20d: Optional[str]
    forecast_up_1d: Optional[float]
    forecast_up_5d: Optional[float]
    forecast_up_20d: Optional[float]

    conviction_score: Optional[float]
    risk_score: Optional[float]
    action_label: Optional[str]       # z decision_support

    ml_prediction: Optional[str]      # "up" | "down" | None  (5d)
    ml_prob_up: Optional[float]
    ml_20d_prediction: Optional[str] = None   # "up" | "down" | None  (20d)
    ml_20d_prob_up: Optional[float] = None
    ml_thesis_prediction: Optional[str]   # target_thesis_success model
    ml_meta_prediction: Optional[str] = None
    meta_trade_probability: Optional[float] = None
    meta_gate_applied: bool = False
    meta_trade_threshold: Optional[float] = None
    meta_threshold_scope: Optional[str] = None

    directional_accuracy: Optional[float]   # historyczna jakość tez

    active_alerts: int
    has_critical_alert: bool

    # Uzasadnienie tekstowe
    rationale: str                    # główny argument
    top_signals: list[SignalContribution]   # top 5 wkładów do wyniku

    snapshot_at: Optional[datetime]
    data_complete: bool               # False gdy brak kluczowych danych

    # Dane opcyjne (dostępne dla US stocks i ETF; None dla GPW / metali)
    implied_volatility: Optional[float] = None   # ATM IV w % (np. 35.2)
    put_call_ratio: Optional[float] = None       # put vol / call vol
    iv_rank: Optional[float] = None              # 0-100: gdzie bieżące IV w 52-tygodniowym zakresie

    # Dane wynikowe
    earnings_surprise_pct: Optional[float] = None  # EPS surprise % ostatniego raportu (< 90 dni)

    last_price: Optional[float] = None  # ostatnia cena zamknięcia z DailyAssetFeatureORM


class TopPick(AssetRecommendation):
    certainty_score: float        # 0-100: ważona zbieżność wszystkich sygnałów
    signals_aligned: int          # ile z 9 sygnałów jest zgodnych (bullish)
    max_signals: int = 9
    aligned_labels: list[str]     # nazwy spełnionych sygnałów
    missing_labels: list[str]     # nazwy niespełnionych sygnałów


class RecommendationJournalRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: str
    snapshot_at: datetime
    created_at: datetime
    model_version: str
    revision: int = 1
    previous_record_id: Optional[int] = None
    change_type: str = "initial"
    change_summary: Optional[str] = None
    change_details_json: str = "{}"
    signal_snapshot_json: str = "{}"
    market: str
    regime: str
    action: str
    displayed_action: str
    has_position: bool
    calibration_scope: str
    calibration_sample_size: int
    composite_score: float
    confidence: float
    probability_buy: float
    probability_sell: float
    probability_no_trade: float
    buy_threshold: float
    sell_threshold: float
    transaction_cost_pct: float
    expected_gross_edge_pct: float
    expected_net_edge_pct: float
    uncertainty_pct: float
    meta_trade_probability: Optional[float]
    meta_gate_applied: bool
    meta_trade_threshold: Optional[float] = None
    meta_threshold_scope: Optional[str] = None
    no_trade_reason: Optional[str] = None
    rationale: Optional[str] = None
    data_complete: bool = True
    base_price: Optional[float]
    quality_flag: Optional[str]
    realized_return_1d_pct: Optional[float]
    realized_return_5d_pct: Optional[float]
    realized_return_20d_pct: Optional[float]
    strategy_net_return_1d_pct: Optional[float]
    strategy_net_return_5d_pct: Optional[float]
    strategy_net_return_20d_pct: Optional[float]
    evaluated_at: Optional[datetime]
