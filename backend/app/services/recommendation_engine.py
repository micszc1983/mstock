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

Wynik: "KUP" / "SPRZEDAJ" / "TRZYMAJ" / "BRAK TRANSAKCJI" z uzasadnieniem.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.assets import get_asset, list_assets
from app.repositories.alerts import list_alerts_for_asset
from app.repositories.decision_support import get_latest_decision_snapshot
from app.repositories.features import get_latest_feature_snapshot
from app.repositories.forecasts import get_latest_forecasts
from app.repositories.theses import get_latest_thesis
from app.services.quality_metrics import build_thesis_quality_summary
from app.schemas.recommendation import AssetRecommendation, SignalContribution, TopPick
from app.utils.datetime import ensure_utc


def _has_open_position(db: Session, asset_id: str) -> bool:
    from app.db.models import PortfolioPositionORM

    quantity = db.scalar(
        select(PortfolioPositionORM.quantity)
        .where(PortfolioPositionORM.asset_id == asset_id)
        .limit(1)
    )
    return bool(quantity and quantity > 0)


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _norm(value: float, center: float, scale: float) -> float:
    """Normalizuje wartość do [-1, +1] wokół centrum."""
    return max(-1.0, min(1.0, (value - center) / scale))


def _forecast_consensus_veto(recommendation: str, *forecasts) -> str | None:
    """Move a calibrated action to no-trade on multi-horizon disagreement."""
    if len(forecasts) != 3 or any(forecast is None for forecast in forecasts):
        return None
    threshold = _clamp(
        settings.recommendation_forecast_consensus_veto_probability,
        0.05,
        0.49,
    )
    directions = [(forecast.direction or "").lower() for forecast in forecasts]
    up_probabilities = [float(forecast.up_probability) for forecast in forecasts]
    # Horyzont 5d jest zgodny z targetem kalibratora, 20d stabilizuje sygnał,
    # a 1d ma tylko rolę pomocniczą. Większość zgodnych horyzontów wystarcza,
    # jeżeli ich ważone prawdopodobieństwo także przeczy transakcji.
    weighted_up = (
        up_probabilities[0] * 0.20
        + up_probabilities[1] * 0.45
        + up_probabilities[2] * 0.35
    )
    if (
        recommendation == "KUP"
        and sum(direction == "down" for direction in directions) >= 2
        and weighted_up <= min(0.48, threshold + 0.03)
    ):
        return (
            "Sygnał KUP został przeniesiony do strefy bez transakcji: "
            "prognozy 1d, 5d i 20d zgodnie wskazują wyraźną przewagę spadku."
        )
    if (
        recommendation == "SPRZEDAJ"
        and sum(direction == "up" for direction in directions) >= 2
        and weighted_up >= max(0.52, 1.0 - threshold - 0.03)
    ):
        return (
            "Sygnał SPRZEDAJ został przeniesiony do strefy bez transakcji: "
            "prognozy 1d, 5d i 20d zgodnie wskazują wyraźną przewagę wzrostu."
        )
    return None


def _composite_consistency_veto(recommendation: str, composite_score: float) -> str | None:
    """Prevent a directional trade that contradicts the broad signal basket."""
    if recommendation == "SPRZEDAJ" and composite_score >= 55.0:
        return (
            "Sygnał SPRZEDAJ został przeniesiony do strefy bez transakcji: "
            "łączny koszyk sygnałów nie potwierdza presji spadkowej."
        )
    if recommendation == "KUP" and composite_score <= 45.0:
        return (
            "Sygnał KUP został przeniesiony do strefy bez transakcji: "
            "łączny koszyk sygnałów nie potwierdza przewagi wzrostowej."
        )
    return None


def build_recommendation(db: Session, asset_id: str) -> AssetRecommendation | None:
    asset_row = get_asset(db, asset_id)
    if asset_row is None:
        return None

    feature = get_latest_feature_snapshot(db, asset_id)
    if feature is None:
        held = _has_open_position(db, asset_id)
        return AssetRecommendation(
            asset_id=asset_id,
            name=asset_row.name,
            symbol=asset_row.symbol,
            asset_type=asset_row.type,
            recommendation="TRZYMAJ" if held else "BRAK TRANSAKCJI",
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
    try:
        from app.services.ml_activation import get_eligible_prediction
        ml_5d = get_eligible_prediction(db, asset_id, "target_up_5d")
        ml_20d = get_eligible_prediction(db, asset_id, "target_up_20d")
        ml_thesis = get_eligible_prediction(db, asset_id, "target_thesis_success")
        ml_meta = get_eligible_prediction(db, asset_id, "target_meta_label")
    except Exception:
        ml_5d = ml_20d = ml_thesis = ml_meta = None

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

    # ── Earnings surprise ──────────────────────────────────────────────────
    try:
        from app.services.earnings_service import get_latest_earnings_surprise
        earnings_surprise_pct = get_latest_earnings_surprise(db, asset_id)
    except Exception:
        earnings_surprise_pct = None

    # ── LLM sentiment z analizy wynikowej ─────────────────────────────────
    try:
        from app.repositories.earnings_analysis import get_latest_llm_sentiment
        llm_earnings_sentiment = get_latest_llm_sentiment(db, asset_id, max_days=90)
    except Exception:
        llm_earnings_sentiment = None

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
            _norm(ml_5d.probability_up, 0.5, 0.5), 0.08)

    # 10b. ML predykcja 20d (jeśli dostępna) — ważniejszy horyzont
    if ml_20d:
        add("ML: kierunek 20d", ml_20d.probability_up * 100,
            _norm(ml_20d.probability_up, 0.5, 0.5), 0.10)

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

    # 14. Implied Volatility — wysoka IV = większa niepewność/ryzyko (bearish)
    #     Normalizacja: centrum 0.30 (30%), skala 0.30; wartości >0.60 = panika
    if feature.implied_volatility is not None:
        add("Impl. zmienność (IV)", feature.implied_volatility * 100,
            _norm(feature.implied_volatility, 0.30, 0.30) * -1, 0.05)

    # 15. P/C ratio — >1 = przewaga put (bearish), <0.5 = przewaga call (bullish)
    #     Centrum 0.70 (typowy poziom rynku), skala 0.60
    if feature.put_call_ratio is not None:
        add("Wskaźnik P/C", feature.put_call_ratio,
            _norm(feature.put_call_ratio, 0.70, 0.60) * -1, 0.04)

    # 16. Earnings surprise — EPS beat/miss z ostatnich 90 dni
    #     Centrum 0%, skala 15%; +15% zaskoczenie = +1.0 (bullish)
    if earnings_surprise_pct is not None:
        add("Zaskoczenie EPS", earnings_surprise_pct,
            _norm(earnings_surprise_pct, 0.0, 15.0), 0.07)

    # 17. LLM sentyment z analizy wynikowej — ocena tonu zarządu i newsów
    #     Centrum 0, skala 60; wartości ±60 = silny sygnał
    if llm_earnings_sentiment is not None:
        add("LLM: ton wyników", llm_earnings_sentiment,
            _norm(llm_earnings_sentiment, 0.0, 60.0), 0.06)

    # ── Oblicz composite score ──────────────────────────────────────────
    total_weight = sum(w for _, _, _, w in contributions)
    weighted_sum = sum(c * w for _, _, c, w in contributions)
    normalized = weighted_sum / total_weight if total_weight > 0 else 0.0
    composite = _clamp(50.0 + normalized * 50.0)

    # ── Decyzja i confidence z historii out-of-sample ──────────────────
    from app.services.recommendation_calibration import calibrate_recommendation

    calibrated = calibrate_recommendation(db, asset_row, feature)
    from app.services.meta_thresholds import calibrated_meta_threshold
    meta_threshold = calibrated_meta_threshold(db, calibrated.market, feature.regime_label)
    held = _has_open_position(db, asset_id)
    if calibrated.action == "BUY":
        recommendation = "KUP"
    elif calibrated.action == "SELL":
        recommendation = "SPRZEDAJ"
    else:
        recommendation = "TRZYMAJ" if held else "BRAK TRANSAKCJI"

    meta_gate_applied = False
    final_no_trade_reason = calibrated.no_trade_reason
    confidence_probability = calibrated.confidence_probability
    forecast_gate_reason = (
        _forecast_consensus_veto(recommendation, f1, f5, f20)
        or _composite_consistency_veto(recommendation, composite)
    )
    if forecast_gate_reason is not None:
        recommendation = "TRZYMAJ" if held else "BRAK TRANSAKCJI"
        final_no_trade_reason = forecast_gate_reason
        confidence_probability = calibrated.probability_no_trade
    if (
        recommendation in {"KUP", "SPRZEDAJ"}
        and ml_meta is not None
        and ml_meta.probability_up < meta_threshold.threshold
    ):
        recommendation = "TRZYMAJ" if held else "BRAK TRANSAKCJI"
        meta_gate_applied = True
        confidence_probability = calibrated.probability_no_trade
        final_no_trade_reason = (
            f"Meta-model ocenia opłacalność wykonania na {ml_meta.probability_up * 100:.1f}% "
            f"przy progu {meta_threshold.threshold * 100:.1f}% ({meta_threshold.scope}) "
            "i kieruje sygnał do strefy bez transakcji."
        )

    confidence = confidence_probability * 100
    if confidence >= 70:
        confidence_label = "wysoka"
    elif confidence >= 55:
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
    elif recommendation == "TRZYMAJ":
        main = "Brak przewagi uzasadniającej zmianę już posiadanej pozycji."
        all_drivers = bullish_drivers[:2] + bearish_drivers[:2]
        if all_drivers:
            main += f" Kluczowe czynniki: {', '.join(all_drivers)}."
    else:
        main = "Brak transakcji jest obecnie optymalną decyzją."
        if final_no_trade_reason:
            main += f" {final_no_trade_reason}"

    main += (
        f" Kalibracja {calibrated.market}/{calibrated.regime} ({calibrated.scope}, "
        f"n={calibrated.sample_size}): P(kup)={calibrated.probability_buy * 100:.1f}%, "
        f"P(sprzedaj)={calibrated.probability_sell * 100:.1f}%, koszt={calibrated.transaction_cost_pct:.2f}%, "
        f"przewaga netto={calibrated.expected_net_edge_pct:.2f}% ± {calibrated.uncertainty_pct:.2f}%."
    )

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
        market_segment=calibrated.market,
        calibration_scope=calibrated.scope,
        calibration_sample_size=calibrated.sample_size,
        probability_buy=round(calibrated.probability_buy * 100, 1),
        probability_sell=round(calibrated.probability_sell * 100, 1),
        probability_no_trade=round(calibrated.probability_no_trade * 100, 1),
        buy_threshold=round(calibrated.buy_threshold * 100, 1),
        sell_threshold=round(calibrated.sell_threshold * 100, 1),
        transaction_cost_pct=round(calibrated.transaction_cost_pct, 3),
        expected_gross_edge_pct=round(calibrated.expected_gross_edge_pct, 3),
        expected_net_edge_pct=round(calibrated.expected_net_edge_pct, 3),
        uncertainty_pct=round(calibrated.uncertainty_pct, 3),
        no_trade_reason=final_no_trade_reason,
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
        ml_20d_prediction=ml_20d.predicted_label if ml_20d else None,
        ml_20d_prob_up=round(ml_20d.probability_up * 100, 1) if ml_20d else None,
        ml_thesis_prediction=ml_thesis.predicted_label if ml_thesis else None,
        ml_meta_prediction=ml_meta.predicted_label if ml_meta else None,
        meta_trade_probability=round(ml_meta.probability_up * 100, 1) if ml_meta else None,
        meta_gate_applied=meta_gate_applied,
        meta_trade_threshold=round(meta_threshold.threshold * 100, 1) if ml_meta else None,
        meta_threshold_scope=meta_threshold.scope if ml_meta else None,
        directional_accuracy=round(dir_acc * 100, 1) if dir_acc else None,
        active_alerts=len(active),
        has_critical_alert=has_critical,
        rationale=main,
        top_signals=top_signals,
        snapshot_at=ensure_utc(feature.snapshot_at),
        data_complete=True,
        implied_volatility=round(feature.implied_volatility * 100, 1) if feature.implied_volatility is not None else None,
        put_call_ratio=round(feature.put_call_ratio, 3) if feature.put_call_ratio is not None else None,
        iv_rank=round(feature.iv_rank, 1) if feature.iv_rank is not None else None,
        earnings_surprise_pct=round(earnings_surprise_pct, 2) if earnings_surprise_pct is not None else None,
        last_price=feature.last_price if feature.last_price else None,
    )


import threading as _threading
import time as _time

_rec_cache: list[AssetRecommendation] = []
_rec_cache_ts: float = 0.0
_rec_cache_ttl: float = 90.0
_rec_cache_lock = _threading.Lock()


def invalidate_recommendations_cache() -> None:
    """Wymuś odświeżenie cache przy następnym wywołaniu (np. po pełnym cyklu schedulera)."""
    global _rec_cache_ts
    _rec_cache_ts = 0.0
    from app.services.recommendation_calibration import invalidate_calibration_cache
    invalidate_calibration_cache()


def build_all_recommendations(db: Session) -> list[AssetRecommendation]:
    global _rec_cache, _rec_cache_ts

    now = _time.monotonic()
    if now - _rec_cache_ts < _rec_cache_ttl and _rec_cache:
        return _rec_cache

    with _rec_cache_lock:
        # Podwójne sprawdzenie po nabyciu locka
        if _time.monotonic() - _rec_cache_ts < _rec_cache_ttl and _rec_cache:
            return _rec_cache

        results = []
        for asset in list_assets(db):
            rec = build_recommendation(db, asset.id)
            if rec is not None:
                results.append(rec)
        order = {"KUP": 0, "TRZYMAJ": 1, "BRAK TRANSAKCJI": 2, "SPRZEDAJ": 3}
        results.sort(key=lambda r: (order.get(r.recommendation, 1), -r.composite_score))

        _rec_cache = results
        _rec_cache_ts = _time.monotonic()
        return results


# ── Top Picks ─────────────────────────────────────────────────────────────────

_SIGNAL_CHECKS: list[tuple[str, str]] = [
    ("calibrated_edge",            "Przewaga netto pokrywa niepewność"),
    ("conviction_score >= 60",     "Wysokie przekonanie (≥60)"),
    ("risk_score <= 40",           "Niskie ryzyko (≤40)"),
    ("ml_prediction == up",        "ML 5d: wzrost"),
    ("ml_20d_prediction == up",    "ML 20d: wzrost"),
    ("forecast_dir_5d == up",      "Prognoza 5d: wzrost"),
    ("forecast_dir_20d == up",     "Prognoza 20d: wzrost"),
    ("fragility_score <= 40",      "Niska kruchość (≤40)"),
    ("trend_score >= 55",          "Silny trend (≥55)"),
]


def _check_signal(rec: AssetRecommendation, check: str) -> bool:
    if check == "calibrated_edge":
        return rec.expected_net_edge_pct > rec.uncertainty_pct
    if check == "conviction_score >= 60":
        return rec.conviction_score is not None and rec.conviction_score >= 60
    if check == "risk_score <= 40":
        return rec.risk_score is not None and rec.risk_score <= 40
    if check == "ml_prediction == up":
        return rec.ml_prediction == "up"
    if check == "ml_20d_prediction == up":
        return rec.ml_20d_prediction == "up"
    if check == "forecast_dir_5d == up":
        return rec.forecast_dir_5d == "up"
    if check == "forecast_dir_20d == up":
        return rec.forecast_dir_20d == "up"
    if check == "fragility_score <= 40":
        return rec.fragility_score <= 40
    if check == "trend_score >= 55":
        return rec.trend_score >= 55
    return False


def _compute_certainty(rec: AssetRecommendation) -> float:
    return rec.confidence


def build_top_picks(db: Session, min_signals: int = 6) -> list[TopPick]:
    """
    Zwraca aktywa gdzie wszystkie kluczowe sygnały są zgodne (bullish).
    Minimalne wymagania:
      - recommendation == "KUP"
      - co najmniej min_signals z 9 sygnałów zgodnych
      - historycznie skalibrowane confidence >= 62%
    """
    picks: list[TopPick] = []

    for asset in list_assets(db):
        rec = build_recommendation(db, asset.id)
        if rec is None:
            continue
        if rec.recommendation != "KUP":
            continue
        aligned, missing = [], []
        for check, label in _SIGNAL_CHECKS:
            if _check_signal(rec, check):
                aligned.append(label)
            else:
                missing.append(label)

        if len(aligned) < min_signals:
            continue

        certainty = _compute_certainty(rec)
        if certainty < 62:
            continue

        picks.append(TopPick(
            **rec.model_dump(),
            certainty_score=certainty,
            signals_aligned=len(aligned),
            aligned_labels=aligned,
            missing_labels=missing,
        ))

    picks.sort(key=lambda p: -p.certainty_score)
    return picks
