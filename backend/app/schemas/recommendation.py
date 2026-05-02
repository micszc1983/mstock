from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


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
    recommendation: str         # "KUP" | "SPRZEDAJ" | "TRZYMAJ"
    composite_score: float      # 0-100; >60=kup, <40=sprzedaj
    confidence: float           # 0-100; jak daleko od 50
    confidence_label: str       # "wysoka" | "średnia" | "niska"

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
