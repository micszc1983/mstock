from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ensemble import DynamicWeightInfo, EnsembleConfig, EnsembleLeaderboard, EnsembleSignal
from app.services.ensemble_engine import (
    DEFAULT_CONFIG,
    build_ensemble_signal,
    build_leaderboard,
    compute_dynamic_weights,
    fill_ensemble_outcomes,
)

router = APIRouter(tags=["ensemble"])


@router.get("/assets/{asset_id}/ensemble", response_model=EnsembleSignal)
def get_ensemble_signal(
    asset_id: str,
    mode: str = "ensemble_weighted",
    heuristic_weight: float = 0.45,
    ml_weight: float = 0.55,
    save: bool = False,
    db: Session = Depends(get_db),
) -> EnsembleSignal:
    """Sygnał ensemble dla aktywa (bez zapisu do historii)."""
    config = EnsembleConfig(
        mode=mode,
        heuristic_weight=heuristic_weight,
        ml_weight=ml_weight,
        ml_targets=["target_up_5d", "target_up_20d"],
    )
    result = build_ensemble_signal(db, asset_id, config, save_record=save)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Brak danych dla {asset_id}")
    return result


@router.post("/assets/{asset_id}/ensemble/record", response_model=EnsembleSignal)
def record_ensemble_signal(
    asset_id: str,
    config: EnsembleConfig = DEFAULT_CONFIG,
    db: Session = Depends(get_db),
) -> EnsembleSignal:
    """Generuje i zapisuje sygnał ensemble do historii śledzenia."""
    result = build_ensemble_signal(db, asset_id, config, save_record=True)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Brak danych dla {asset_id}")
    return result


@router.get("/assets/{asset_id}/ensemble/weights", response_model=DynamicWeightInfo)
def get_dynamic_weights(asset_id: str, db: Session = Depends(get_db)) -> DynamicWeightInfo:
    """Dynamiczne wagi ensemble dla aktywa — obliczone z historycznej trafności."""
    return compute_dynamic_weights(db, asset_id)


@router.get("/ensemble/leaderboard", response_model=list[EnsembleLeaderboard])
def get_leaderboard(db: Session = Depends(get_db)) -> list[EnsembleLeaderboard]:
    """Leaderboard: który tryb wygrywa per aktywo."""
    return build_leaderboard(db)


@router.post("/ensemble/fill-outcomes")
def fill_outcomes(db: Session = Depends(get_db)) -> dict:
    """Wypełnia outcomes dla pending ensemble records."""
    filled = fill_ensemble_outcomes(db)
    return {"filled": filled}
