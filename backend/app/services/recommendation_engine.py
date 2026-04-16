"""
recommendation_engine.py

Silnik rekomendacji inwestycyjnych agregujący WSZYSTKIE dostępne sygnały:
  - cechy techniczne i sentymentowe (DailyAssetFeature)
  - prognozy heurystyczne 1d / 5d / 20d
  - decision support (conviction, risk, action_label)
  - tezy (thesis_confidence, fragility)
  - predykcje ML (target_up_5d, target_thesis_success)
  - historyczna jakość tez (directional_accuracy)
  - aktywne alerty (liczba i severity)

Wynik: "KUP" / "SPRZEDAJ" / "TRZYMAJ" z uzasadnieniem.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.assets import get_asset, list_assets
from app.repositories.alerts import list_alerts_for_asset
from app.repositories.decision_support import get_latest_decision_snapshot
from app.repositories.features import get_latest_feature_snapshot
from app.repositories.forecasts import get_latest_forecasts
from app.repositories.ml import get_latest_prediction
from app.repositories.theses import get_latest_thesis
from app.services.quality_metrics import build_thesis_quality_summary
from app.schemas.recommendation import AssetRecommendation, SignalContribution
from app.utils.datetime import ensure_utc


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _norm(value: float, center: float, scale: float) -> float:
    """Normalizuje wartość do [-1, +1] wokół centrum."""
    return max(-1.0, min(1.0, (value - center) / scale))


def build_recommendation(db: Session, asset_id: str) -> AssetRecommendation | None:
    asset_row = get_asset(db, asset_id)
    if asset_row is None:
        return None

    feature = get_latest_feature_snapshot(db, asset_id)
    if feature is None:
        return AssetRecommendation(
            asset_id=asset_id,
            name=asset_row.name,
            symbol=asset_row.symbol,
            asset_type=asset_row.type,
            recommendation="TRZYMAJ",
            composite_score=50.0,
            confidence=0.0,
            confidence_label="niska",
            trend_score=0, sentiment_score=0, fragility_score=0,
            divergence_score=0, regime="brak danych",
            forecast_dir_1d=None, forecast_dir_5d=None, forecast_dir_20d=None,
            forecast_up_1d=None, forecast_up_5d=None, forecast_up_20d=None,
            conviction_score=None, risk_score=None, action_label=None,
            ml_prediction=None, ml_prob_up=None, ml_thesis_prediction=None,
            directional_accuracy=None, active_alerts=0, has_critical_alert=False,
            rationale="Brak danych do analizy. Uruchom synchronizację danych.",
            top_signals=[], snapshot_at=None, data_complete=False,
        )

    # ── Forecasts ──────────────────────────────────────────────────────────
    forecasts = {f.horizon: f for f in get_latest_forecasts(db, asset_id)}
    f1  = forecasts.get("1d")
    f5  = forecasts.get("5d")
    f20 = forecasts.get("20d")

    # ── Decision Support ───────────────────────────────────────────────────
    decision = get_latest_decision_snapshot(db, asset_id)

    # ── ML Predictions ─────────────────────────────────────────────────────
    ml_5d     = get_latest_prediction(db, asset_id, "target_up_5d")
    ml_thesis = get_latest_prediction(db, asset_id, "target_thesis_success")

    # ── Jakość historyczna ─────────────────────────────────────────────────
    try:
        quality = build_thesis_quality_summary(db, asset_id, limit=100)
        dir_acc = quality.directional_accuracy if quality.total_outcomes >= 5 else None
    except Exception:
        dir_acc = None

    # ── Alerty ─────────────────────────────────────────────────────────────
    alerts = list_alerts_for_asset(db, asset_id, limit=20)
    active = [a for a in alerts if a.status == "active"]
    has_critical = any(a.severity in ("critical", "high") for a in active)

    # ══════════════════════════════════════════════════════════════════════
    # COMPOSITE SCORE — ważona suma znormalizowanych sygnałów
    # Każdy sygnał → wkład w [-1, +1], potem suma × wagi → [−100, +100]
    # Przesunięcie o +50 daje zakres [0, 100], neutral = 50.
    # ══════════════════════════════════════════════════════════════════════
    contributions: list[tuple[str, float, float, float]] = []
    # (nazwa_PL, wartość_surowa, wkład [-1..1], waga)

    def add(name: str, raw: float, contrib: float, weight: float) -> None:
        contributions.append((name, raw, contrib, weight))

    # 1. Trend (trend_score: -100 → +100)
    add("Trend techniczny",    feature.trend_score,
        _norm(feature.trend_score, 0, 100), 0.18)

    # 2. Sentyment (sentiment_score: -100 → +100)
    add("Sentyment newsów",    feature.sentiment_score,
        _norm(feature.sentiment_score, 0, 100), 0.12)

    # 3. Forecast 5d up_probability (kluczowy horyzont)
    if f5:
        add("Prognoza 5d",     f5.up_probability * 100,
            _norm(f5.up_probability, 0.5, 0.5), 0.15)

    # 4. Forecast 20d up_probability (długi termin)
    if f20:
        add("Prognoza 20d",    f20.up_probability * 100,
            _norm(f20.up_probability, 0.5, 0.5), 0.10)

    # 5. Forecast 1d (krótki termin — mniejsza waga)
    if f1:
        add("Prognoza 1d",     f1.up_probability * 100,
            _norm(f1.up_probability, 0.5, 0.5), 0.07)

    # 6. Conviction score z decision support
    if decision:
        add("Conviction",      decision.conviction_score,
            _norm(decision.conviction_score, 50, 50), 0.12)

    # 7. Risk score — odwrócony (wyższe ryzyko = gorszy sygnał)
    if decision:
        add("Ryzyko (−)",      decision.risk_score,
            _norm(decision.risk_score, 50, 50) * -1, 0.10)

    # 8. Fragility — odwrócona
    add("Kruchość (−)",        feature.fragility_score,
        _norm(feature.fragility_score, 50, 50) * -1, 0.07)

    # 9. Divergence — odwrócona
    add("Rozjazd (−)",         feature.divergence_score,
        _norm(feature.divergence_score, 50, 50) * -1, 0.05)

    # 10. ML predykcja 5d (jeśli dostępna)
    if ml_5d:
        add("ML: kierunek 5d", ml_5d.probability_up * 100,
            _norm(ml_5d.probability_up, 0.5, 0.5), 0.09)

    # 11. ML: skuteczność tezy
    if ml_thesis:
        add("ML: skuteczność tezy", ml_thesis.probability_up * 100,
            _norm(ml_thesis.probability_up, 0.5, 0.5), 0.06)

    # 12. Historyczna trafność (jeśli >= 5 outcomes)
    if dir_acc is not None:
        add("Hist. trafność",  dir_acc * 100,
            _norm(dir_acc, 0.5, 0.5), 0.05)

    # 13. Kara za aktywne alerty krytyczne
    if has_critical:
        add("Alert krytyczny", float(len(active)),
            -0.7, 0.05)
    elif len(active) > 3:
        add("Wiele alertów",   float(len(active)),
            -0.3, 0.05)

    # ── Oblicz composite score ──────────────────────────────────────────
    total_weight = sum(w for _, _, _, w in contributions)
    weighted_sum = sum(c * w for _, _, c, w in contributions)
    normalized = weighted_sum / total_weight if total_weight > 0 else 0.0
    composite = _clamp(50.0 + normalized * 50.0)

    # ── Rekomendacja ───────────────────────────────────────────────────
    if composite >= 62:
        recommendation = "KUP"
    elif composite <= 38:
        recommendation = "SPRZEDAJ"
    else:
        recommendation = "TRZYMAJ"

    confidence = abs(composite - 50.0) * 2  # 0-100
    if confidence >= 60:
        confidence_label = "wysoka"
    elif confidence >= 30:
        confidence_label = "średnia"
    else:
        confidence_label = "niska"

    # ── Top 5 sygnałów (po abs wkładu * waga) ──────────────────────────
    ranked = sorted(contributions, key=lambda x: -abs(x[2] * x[3]))[:5]
    top_signals = [
        SignalContribution(
            name=name,
            value=round(raw, 2),
            normalized=round(contrib * weight, 4),
            direction="bullish" if contrib > 0 else "bearish" if contrib < 0 else "neutral",
        )
        for name, raw, contrib, weight in ranked
    ]

    # ── Uzasadnienie tekstowe ──────────────────────────────────────────
    bullish_drivers = [n for n, _, c, _ in ranked if c > 0]
    bearish_drivers = [n for n, _, c, _ in ranked if c < 0]

    if recommendation == "KUP":
        main = f"Sygnały wskazują na przewagę kupujących."
        if bullish_drivers:
            main += f" Kluczowe czynniki: {', '.join(bullish_drivers[:3])}."
        if bearish_drivers:
            main += f" Ryzyka: {', '.join(bearish_drivers[:2])}."
    elif recommendation == "SPRZEDAJ":
        main = f"Układ wskaźników sugeruje presję sprzedażową."
        if bearish_drivers:
            main += f" Czynniki negatywne: {', '.join(bearish_drivers[:3])}."
        if bullish_drivers:
            main += f" Potencjalne wsparcie: {', '.join(bullish_drivers[:2])}."
    else:
        main = f"Sygnały są mieszane — brak wyraźnej przewagi."
        all_drivers = bullish_drivers[:2] + bearish_drivers[:2]
        if all_drivers:
            main += f" Kluczowe czynniki: {', '.join(all_drivers)}."

    if has_critical:
        main += " ⚠ Aktywny alert wysokiego priorytetu."

    return AssetRecommendation(
        asset_id=asset_id,
        name=asset_row.name,
        symbol=asset_row.symbol,
        asset_type=asset_row.type,
        recommendation=recommendation,
        composite_score=round(composite, 1),
        confidence=round(confidence, 1),
        confidence_label=confidence_label,
        trend_score=round(feature.trend_score, 1),
        sentiment_score=round(feature.sentiment_score, 1),
        fragility_score=round(feature.fragility_score, 1),
        divergence_score=round(feature.divergence_score, 1),
        regime=feature.regime_label,
        forecast_dir_1d=f1.direction if f1 else None,
        forecast_dir_5d=f5.direction if f5 else None,
        forecast_dir_20d=f20.direction if f20 else None,
        forecast_up_1d=round(f1.up_probability * 100, 1) if f1 else None,
        forecast_up_5d=round(f5.up_probability * 100, 1) if f5 else None,
        forecast_up_20d=round(f20.up_probability * 100, 1) if f20 else None,
        conviction_score=round(decision.conviction_score, 1) if decision else None,
        risk_score=round(decision.risk_score, 1) if decision else None,
        action_label=decision.action_label if decision else None,
        ml_prediction=ml_5d.predicted_label if ml_5d else None,
        ml_prob_up=round(ml_5d.probability_up * 100, 1) if ml_5d else None,
        ml_thesis_prediction=ml_thesis.predicted_label if ml_thesis else None,
        directional_accuracy=round(dir_acc * 100, 1) if dir_acc else None,
        active_alerts=len(active),
        has_critical_alert=has_critical,
        rationale=main,
        top_signals=top_signals,
        snapshot_at=ensure_utc(feature.snapshot_at),
        data_complete=True,
    )


def build_all_recommendations(db: Session) -> list[AssetRecommendation]:
    results = []
    for asset in list_assets(db):
        rec = build_recommendation(db, asset.id)
        if rec is not None:
            results.append(rec)
    # Sortuj: KUP → TRZYMAJ → SPRZEDAJ, potem malejąco po composite_score
    order = {"KUP": 0, "TRZYMAJ": 1, "SPRZEDAJ": 2}
    results.sort(key=lambda r: (order.get(r.recommendation, 1), -r.composite_score))
    return results
