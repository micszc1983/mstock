"""
ensemble_engine.py — tryby sygnałów: heurystyka, ML, ensemble.

Cztery tryby pracy:
  heuristic          — tylko sygnał z decision_support (conviction/risk/forecasts)
  ml                 — tylko predykcja modelu ML (target_up_5d)
  ensemble_weighted  — ważona suma głosów (konfigurowane wagi)
  ensemble_majority  — większość głosów wygrywa (1 vote per system)

Śledzenie:
  Każde wywołanie zapisuje EnsembleRecord w bazie.
  Outcome evaluator (outcome_fill_ensemble) wypełnia wyniki po 5 dniach.
  Leaderboard aggreguje: kto wygrywał historycznie.
"""
from __future__ import annotations

import json
from statistics import mean
from typing import Optional

from sqlalchemy.orm import Session

from app.repositories.assets import get_asset, list_assets
from app.repositories.decision_support import get_latest_decision_snapshot
from app.repositories.ensemble import (
    get_pending_outcome_records,
    insert_ensemble_record,
    list_ensemble_records,
    list_all_ensemble_records,
)
from app.repositories.features import get_latest_feature_snapshot
from app.repositories.forecasts import get_latest_forecasts
from app.repositories.ml import get_active_model_run, get_latest_prediction
from app.repositories.outcomes import list_outcomes_for_asset
from app.schemas.ensemble import (
    EnsembleConfig,
    EnsembleLeaderboard,
    EnsembleRecord,
    EnsembleSignal,
    SignalVote,
)
from app.utils.datetime import ensure_utc, now_utc


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, v)), 2)


# ── Heuristic vote ────────────────────────────────────────────────────────────

def _heuristic_vote(db: Session, asset_id: str) -> SignalVote:
    feature  = get_latest_feature_snapshot(db, asset_id)
    decision = get_latest_decision_snapshot(db, asset_id)
    forecasts = {f.horizon: f for f in get_latest_forecasts(db, asset_id)}
    f5 = forecasts.get("5d")

    if feature is None or decision is None:
        return SignalVote(
            source="heuristic", source_label="Heurystyka",
            direction="neutral", confidence=0.0, probability_up=50.0,
            reasoning="Brak danych (feature snapshot lub decision snapshot).",
            available=False,
        )

    # Sygnał bazowy: conviction − risk → zakres [-100, +100]
    net = decision.net_thesis_edge
    if f5:
        # Forecast 5d jako dodatkowy sygnał
        prob_up = f5.up_probability * 100
    else:
        prob_up = 50.0 + net * 0.3

    prob_up = _clamp(prob_up, 0, 100)
    direction = "up" if prob_up > 52 else "down" if prob_up < 48 else "neutral"
    confidence = _clamp(abs(prob_up - 50) * 2)

    parts = []
    if decision.action_label:
        parts.append(f"action={decision.action_label}")
    parts.append(f"conviction={decision.conviction_score:.0f}")
    parts.append(f"risk={decision.risk_score:.0f}")
    if f5:
        parts.append(f"forecast5d={f5.direction}@{f5.confidence*100:.0f}%")

    return SignalVote(
        source="heuristic", source_label="Heurystyka",
        direction=direction,
        confidence=confidence,
        probability_up=prob_up,
        reasoning=", ".join(parts),
        available=True,
    )


# ── ML votes ──────────────────────────────────────────────────────────────────

def _ml_vote(db: Session, asset_id: str, target: str, label: str) -> SignalVote:
    pred = get_latest_prediction(db, asset_id, target)
    if pred is None:
        active = get_active_model_run(db, target)
        if active is None:
            return SignalVote(
                source=f"ml_{target}", source_label=label,
                direction="neutral", confidence=0.0, probability_up=50.0,
                reasoning=f"Brak wytrenowanego modelu dla {target}.",
                available=False,
            )
        # Model istnieje ale brak predykcji — wygeneruj on-the-fly
        try:
            import joblib, json as _json
            feature = get_latest_feature_snapshot(db, asset_id)
            decision = get_latest_decision_snapshot(db, asset_id)
            if feature is None:
                raise ValueError("brak feature snapshot")
            bundle = joblib.load(active.model_path)
            model = bundle["model"]
            fnames = bundle["feature_names"]
            vec = {
                "last_price": feature.last_price,
                "trend_score": feature.trend_score,
                "sentiment_score": feature.sentiment_score,
                "divergence_score": feature.divergence_score,
                "fragility_score": feature.fragility_score,
                "narrative_shift_score": feature.narrative_shift_score,
                "volatility_10d": feature.volatility_10d,
                "momentum_20d": feature.momentum_20d,
                "news_count_7d": float(feature.news_count_7d),
                "forecast_confidence_1d": 50.0,
                "forecast_up_probability_1d": 50.0,
                "decision_conviction": decision.conviction_score if decision else 50.0,
                "decision_risk": decision.risk_score if decision else 50.0,
                "decision_timing": decision.timing_score if decision else 50.0,
                "decision_setup_quality": decision.setup_quality_score if decision else 50.0,
            }
            X = [[float(vec.get(k, 0.0)) for k in fnames]]
            prob = float(model.predict_proba(X)[0][1])
        except Exception as exc:
            return SignalVote(
                source=f"ml_{target}", source_label=label,
                direction="neutral", confidence=0.0, probability_up=50.0,
                reasoning=f"Błąd inferecji ML: {exc}",
                available=False,
            )
    else:
        prob = pred.probability_up

    prob_pct = _clamp(prob * 100 if prob <= 1.0 else prob, 0, 100)
    direction = "up" if prob_pct > 52 else "down" if prob_pct < 48 else "neutral"
    confidence = _clamp(abs(prob_pct - 50) * 2)

    return SignalVote(
        source=f"ml_{target}", source_label=label,
        direction=direction,
        confidence=confidence,
        probability_up=prob_pct,
        reasoning=f"p(up)={prob_pct:.1f}%, model={active.model_name if 'active' in dir() else 'cached'}",
        available=True,
    )


# ── Consensus ─────────────────────────────────────────────────────────────────

def _consensus(votes: list[SignalVote]) -> tuple[str, float]:
    available = [v for v in votes if v.available]
    if not available:
        return "n/a", 0.0
    ups = sum(1 for v in available if v.direction == "up")
    total = len(available)
    majority_pct = max(ups, total - ups) / total
    if majority_pct == 1.0:
        label = "pełny"
    elif majority_pct >= 0.67:
        label = "częściowy"
    else:
        label = "brak"
    return label, round(majority_pct, 3)


# ── Ensemble combiner ─────────────────────────────────────────────────────────

def _weighted_combine(votes: list[SignalVote], h_weight: float, ml_weight: float) -> tuple[float, float]:
    """Zwraca (prob_up, confidence) z ważonej sumy."""
    available = [v for v in votes if v.available]
    if not available:
        return 50.0, 0.0

    total_weight = 0.0
    weighted_prob = 0.0
    for v in available:
        w = h_weight if v.source == "heuristic" else ml_weight
        weighted_prob += v.probability_up * w
        total_weight += w

    if total_weight == 0:
        return 50.0, 0.0

    prob = _clamp(weighted_prob / total_weight, 0, 100)
    confidence = _clamp(abs(prob - 50) * 2)
    return prob, confidence


def _majority_combine(votes: list[SignalVote]) -> tuple[float, float]:
    """Zwraca (prob_up, confidence) przez głosowanie większościowe."""
    available = [v for v in votes if v.available]
    if not available:
        return 50.0, 0.0
    ups = [v for v in available if v.direction == "up"]
    downs = [v for v in available if v.direction == "down"]
    if len(ups) > len(downs):
        prob = mean(v.probability_up for v in ups)
        confidence = _clamp(abs(prob - 50) * 2 * len(ups) / len(available))
    elif len(downs) > len(ups):
        prob = mean(v.probability_up for v in downs)
        confidence = _clamp(abs(prob - 50) * 2 * len(downs) / len(available))
    else:
        prob = mean(v.probability_up for v in available)
        confidence = 0.0
    return _clamp(prob), _clamp(confidence)


# ── Public: build signal ──────────────────────────────────────────────────────

_ML_TARGET_LABELS = {
    "target_up_5d":          "ML Kierunek 5d",
    "target_up_20d":         "ML Kierunek 20d",
    "target_thesis_success": "ML Skuteczność tezy",
}

DEFAULT_CONFIG = EnsembleConfig(
    mode="ensemble_weighted",
    heuristic_weight=0.45,
    ml_weight=0.55,
    ml_targets=["target_up_5d", "target_up_20d"],
)

_MODE_LABELS = {
    "heuristic":          "Tylko heurystyka",
    "ml":                 "Tylko ML",
    "ensemble_weighted":  "Ensemble ważony",
    "ensemble_majority":  "Ensemble większościowy",
}


def build_ensemble_signal(
    db: Session,
    asset_id: str,
    config: EnsembleConfig | None = None,
    save_record: bool = True,
) -> EnsembleSignal | None:
    if config is None:
        config = DEFAULT_CONFIG

    feature = get_latest_feature_snapshot(db, asset_id)
    if feature is None:
        return None

    snapshot_at = ensure_utc(feature.snapshot_at)

    # Zbierz głosy
    votes: list[SignalVote] = []
    if config.mode in ("heuristic", "ensemble_weighted", "ensemble_majority"):
        votes.append(_heuristic_vote(db, asset_id))
    if config.mode in ("ml", "ensemble_weighted", "ensemble_majority"):
        for target in config.ml_targets:
            label = _ML_TARGET_LABELS.get(target, target)
            votes.append(_ml_vote(db, asset_id, target, label))

    # Kombinuj
    if config.mode == "heuristic":
        hv = next((v for v in votes if v.source == "heuristic"), None)
        if hv:
            prob, conf = hv.probability_up, hv.confidence
        else:
            prob, conf = 50.0, 0.0
    elif config.mode == "ml":
        ml_votes = [v for v in votes if v.source.startswith("ml_") and v.available]
        if ml_votes:
            prob = mean(v.probability_up for v in ml_votes)
            conf = mean(v.confidence for v in ml_votes)
        else:
            prob, conf = 50.0, 0.0
    elif config.mode == "ensemble_majority":
        prob, conf = _majority_combine(votes)
    else:  # ensemble_weighted
        prob, conf = _weighted_combine(votes, config.heuristic_weight, config.ml_weight)

    direction = "up" if prob > 52 else "down" if prob < 48 else "neutral"
    action = "KUP" if prob > 60 else "SPRZEDAJ" if prob < 40 else "TRZYMAJ"
    consensus, consensus_score = _consensus(votes)

    # Uzasadnienie
    available = [v for v in votes if v.available]
    if direction == "up":
        rationale = f"Zbiorczy sygnał wzrostowy (p={prob:.1f}%). Głosy: {', '.join(f'{v.source_label}→{v.direction}' for v in available)}."
    elif direction == "down":
        rationale = f"Zbiorczy sygnał spadkowy (p={prob:.1f}%). Głosy: {', '.join(f'{v.source_label}→{v.direction}' for v in available)}."
    else:
        rationale = f"Brak wyraźnego sygnału (p={prob:.1f}%). Konsensus: {consensus}."

    signal = EnsembleSignal(
        asset_id=asset_id,
        snapshot_at=snapshot_at,
        mode=config.mode,
        mode_label=_MODE_LABELS.get(config.mode, config.mode),
        votes=votes,
        final_direction=direction,
        final_confidence=conf,
        final_probability_up=prob,
        consensus=consensus,
        consensus_score=consensus_score,
        heuristic_weight=config.heuristic_weight,
        ml_weight=config.ml_weight,
        action=action,
        rationale=rationale,
    )

    # Zapisz rekord do śledzenia
    if save_record:
        h_vote = next((v for v in votes if v.source == "heuristic"), None)
        ml_votes = [v for v in votes if v.source.startswith("ml_") and v.available]
        ml_dir = None
        ml_conf = 0.0
        if ml_votes:
            ml_prob = mean(v.probability_up for v in ml_votes)
            ml_dir = "up" if ml_prob > 52 else "down" if ml_prob < 48 else "neutral"
            ml_conf = mean(v.confidence for v in ml_votes)
        try:
            insert_ensemble_record(
                db,
                asset_id=asset_id,
                mode=config.mode,
                heuristic_direction=h_vote.direction if h_vote and h_vote.available else None,
                ml_direction=ml_dir,
                ensemble_direction=direction,
                heuristic_confidence=h_vote.confidence if h_vote and h_vote.available else 0.0,
                ml_confidence=ml_conf,
                ensemble_confidence=conf,
            )
            db.commit()
        except Exception:
            db.rollback()

    return signal


# ── Outcome backfill ──────────────────────────────────────────────────────────

def fill_ensemble_outcomes(db: Session) -> int:
    """
    Wypełnia actual_return_5d i winner dla rekordów ensemble które już mają outcome.
    Wywoływany co cykl przez scheduler.
    """
    filled = 0
    pending = get_pending_outcome_records(db, limit=200)

    for rec in pending:
        outcomes = {o.horizon: o for o in list_outcomes_for_asset(db, rec.asset_id, limit=50)}
        o5d = outcomes.get("5d")
        if o5d is None:
            continue  # jeszcze za wcześnie

        actual_return = o5d.realized_return_pct
        actual_up = actual_return > 0

        h_correct = None
        if rec.heuristic_direction:
            h_correct = (rec.heuristic_direction == "up") == actual_up

        ml_correct = None
        if rec.ml_direction:
            ml_correct = (rec.ml_direction == "up") == actual_up

        ens_correct = None
        if rec.ensemble_direction:
            ens_correct = (rec.ensemble_direction == "up") == actual_up

        # Ustal zwycięzcę
        scores = {}
        if h_correct is not None:
            scores["heuristic"] = int(h_correct)
        if ml_correct is not None:
            scores["ml"] = int(ml_correct)
        if ens_correct is not None and rec.mode not in ("heuristic", "ml"):
            scores["ensemble"] = int(ens_correct)

        if scores:
            max_score = max(scores.values())
            winners = [k for k, v in scores.items() if v == max_score]
            winner = winners[0] if len(winners) == 1 else "tie"
        else:
            winner = None

        rec.actual_return_5d = actual_return
        rec.heuristic_correct = h_correct
        rec.ml_correct = ml_correct
        rec.ensemble_correct = ens_correct
        rec.winner = winner
        filled += 1

    if filled > 0:
        db.commit()
    return filled


# ── Leaderboard ───────────────────────────────────────────────────────────────

def build_leaderboard(db: Session) -> list[EnsembleLeaderboard]:
    results = []
    for asset_row in list_assets(db):
        records = list_ensemble_records(db, asset_row.id, limit=500)
        evaluated = [r for r in records if r.winner is not None]
        if not evaluated:
            results.append(EnsembleLeaderboard(
                asset_id=asset_row.id, name=asset_row.name,
                total_records=len(records),
                heuristic_wins=0, ml_wins=0, ensemble_wins=0, ties=0,
                heuristic_win_rate=0.0, ml_win_rate=0.0, ensemble_win_rate=0.0,
                recommended_mode="ensemble_weighted",
                avg_heuristic_confidence=0.0, avg_ml_confidence=0.0,
                last_updated=None,
            ))
            continue

        h_wins   = sum(1 for r in evaluated if r.winner == "heuristic")
        ml_wins  = sum(1 for r in evaluated if r.winner == "ml")
        ens_wins = sum(1 for r in evaluated if r.winner == "ensemble")
        ties     = sum(1 for r in evaluated if r.winner == "tie")
        total    = len(evaluated)

        rates = {"heuristic": h_wins / total, "ml": ml_wins / total, "ensemble": ens_wins / total}
        recommended = max(rates, key=rates.get)

        avg_h_conf  = mean(r.heuristic_confidence for r in records if r.heuristic_confidence) if records else 0.0
        avg_ml_conf = mean(r.ml_confidence for r in records if r.ml_confidence) if records else 0.0
        last = max((ensure_utc(r.created_at) for r in records), default=None)

        results.append(EnsembleLeaderboard(
            asset_id=asset_row.id, name=asset_row.name,
            total_records=len(records),
            heuristic_wins=h_wins, ml_wins=ml_wins, ensemble_wins=ens_wins, ties=ties,
            heuristic_win_rate=round(rates["heuristic"], 3),
            ml_win_rate=round(rates["ml"], 3),
            ensemble_win_rate=round(rates["ensemble"], 3),
            recommended_mode=recommended,
            avg_heuristic_confidence=round(avg_h_conf, 1),
            avg_ml_confidence=round(avg_ml_conf, 1),
            last_updated=last,
        ))

    results.sort(key=lambda r: -(r.ml_win_rate + r.ensemble_win_rate))
    return results
