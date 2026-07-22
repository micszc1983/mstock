"""
anomaly_service.py — Isolation Forest na dziennych cechach ML.

Dla każdego aktywa trenuje IF na historycznych wektorach cech (MLTrainingRowORM)
i ocenia, czy bieżący snapshot jest anomalny względem normy historycznej.

Wynik 0-100 (100 = najbardziej anomalny). is_anomaly=True gdy IF klasyfikuje jako -1.
Top-5 cech: te o najwyższym Z-score względem mediany historycznej.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.db.models import AnomalyScoreORM
from app.services.ml_foundation import _FEATURE_NAMES, _feature_vector


# ── Stałe ─────────────────────────────────────────────────────────────────────

_MIN_ROWS = 20          # minimalna liczba wierszy do trenowania
_CONTAMINATION = 0.1    # zakładany odsetek anomalii w danych treningowych


# ── Pomocnicze ────────────────────────────────────────────────────────────────

def _check_available() -> None:
    import sklearn.ensemble  # noqa — rzuci ImportError jeśli brak scikit-learn


def _to_x(feature_json: str) -> list[float]:
    d = json.loads(feature_json)
    return [float(d.get(k, 0.0)) for k in _FEATURE_NAMES]


def _raw_to_score(decision_value: float) -> float:
    """Konwertuje decision_function IF (typowo ok. [-0.5, 0.5]) na skalę 0-100.
    Niższy decision_value → bardziej anomalny → wyższy anomaly_score."""
    return max(0.0, min(100.0, round((0.5 - decision_value) * 100.0, 1)))


# ── Główna funkcja ─────────────────────────────────────────────────────────────

def train_and_score(db: Session, asset_id: str) -> dict:
    """Trenuje Isolation Forest i ocenia bieżący wektor cech dla asset_id.
    Zwraca dict z wynikiem i zapisuje go do anomaly_scores."""
    from sklearn.ensemble import IsolationForest
    from app.repositories.ml import list_training_rows_for_target

    rows = list_training_rows_for_target(db, "target_up_5d", asset_id=asset_id)
    if len(rows) < _MIN_ROWS:
        return {
            "asset_id": asset_id,
            "anomaly_score": None,
            "is_anomaly": False,
            "trained_on_rows": len(rows),
            "error": f"Za mało danych ({len(rows)}/{_MIN_ROWS})",
        }

    X = [_to_x(r.feature_json) for r in rows]

    contamination = min(_CONTAMINATION, max(0.01, 2.0 / len(X)))
    model = IsolationForest(
        n_estimators=100,
        contamination=contamination,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X)

    current = X[-1]
    raw = float(model.decision_function([current])[0])
    # sklearn zwraca numpy.bool_; FastAPI nie serializuje go jak zwykłego bool.
    is_anomaly = bool(model.predict([current])[0] == -1)
    score = _raw_to_score(raw)

    # Top-5 cech wg Z-score vs historyczna mediana
    import statistics
    top_features = _top_contributing_features(current, X[:-1])

    scored_at = datetime.now(timezone.utc)
    _persist(db, asset_id, scored_at, score, is_anomaly, len(X), top_features, raw)

    return {
        "asset_id": asset_id,
        "scored_at": scored_at.isoformat(),
        "anomaly_score": score,
        "is_anomaly": is_anomaly,
        "trained_on_rows": len(X),
        "top_features": top_features,
    }


def _top_contributing_features(
    current: list[float],
    historical: list[list[float]],
    n: int = 5,
) -> list[dict]:
    """Zwraca n cech z najwyższym Z-score względem mediany historycznej."""
    if not historical:
        return []

    import statistics

    contributions = []
    for i, name in enumerate(_FEATURE_NAMES):
        hist_col = [row[i] for row in historical]
        try:
            med = statistics.median(hist_col)
            std = statistics.stdev(hist_col) if len(hist_col) > 1 else 0.0
        except Exception:
            continue
        z = abs(current[i] - med) / std if std > 0 else 0.0
        contributions.append({
            "feature": name,
            "value": round(current[i], 4),
            "median": round(med, 4),
            "z_score": round(z, 2),
        })

    contributions.sort(key=lambda x: x["z_score"], reverse=True)
    return contributions[:n]


def _persist(
    db: Session,
    asset_id: str,
    scored_at: datetime,
    score: float,
    is_anomaly: bool,
    trained_on_rows: int,
    top_features: list[dict],
    raw_decision_value: float | None = None,
) -> None:
    # Usuń poprzedni wpis na ten sam dzień
    from sqlalchemy import func as _func
    db.execute(
        delete(AnomalyScoreORM).where(
            AnomalyScoreORM.asset_id == asset_id,
            _func.date(AnomalyScoreORM.scored_at) == scored_at.date(),
        )
    )
    db.add(AnomalyScoreORM(
        asset_id=asset_id,
        scored_at=scored_at,
        anomaly_score=score,
        is_anomaly=is_anomaly,
        trained_on_rows=trained_on_rows,
        top_features_json=json.dumps(top_features, ensure_ascii=False),
        raw_response=json.dumps({"decision_value": raw_decision_value}),
    ))
    db.commit()


# ── Pobieranie wyników ─────────────────────────────────────────────────────────

def get_latest(db: Session, asset_id: str) -> dict | None:
    row = db.scalars(
        select(AnomalyScoreORM)
        .where(AnomalyScoreORM.asset_id == asset_id)
        .order_by(AnomalyScoreORM.scored_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return {
        "asset_id": row.asset_id,
        "scored_at": row.scored_at.isoformat(),
        "anomaly_score": row.anomaly_score,
        "is_anomaly": row.is_anomaly,
        "trained_on_rows": row.trained_on_rows,
        "top_features": json.loads(row.top_features_json),
    }


def get_history(db: Session, asset_id: str, limit: int = 30) -> list[dict]:
    rows = db.scalars(
        select(AnomalyScoreORM)
        .where(AnomalyScoreORM.asset_id == asset_id)
        .order_by(AnomalyScoreORM.scored_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "scored_at": r.scored_at.isoformat(),
            "anomaly_score": r.anomaly_score,
            "is_anomaly": r.is_anomaly,
        }
        for r in reversed(rows)
    ]


# ── Batch ──────────────────────────────────────────────────────────────────────

def score_all_assets(db: Session) -> dict[str, float | None]:
    from app.repositories.assets import list_assets
    results: dict[str, float | None] = {}
    for asset in list_assets(db):
        if asset.type != "stock":
            continue
        try:
            r = train_and_score(db, asset.id)
            results[asset.id] = r.get("anomaly_score")
        except Exception as exc:
            # Flush jednego aktywa nie może pozostawić sesji w stanie failed i
            # zablokować całej reszty batcha/schedulera.
            db.rollback()
            print(f"[anomaly] {asset.id}: {exc}")
            results[asset.id] = None
    return results
