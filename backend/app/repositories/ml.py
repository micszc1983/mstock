from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import MLBacktestResultORM, MLModelRunORM, MLPredictionORM, MLSettingORM, MLTrainingRowORM
from app.utils.datetime import now_utc


def upsert_setting(db: Session, key: str, value: str) -> MLSettingORM:
    row = db.scalar(select(MLSettingORM).where(MLSettingORM.setting_key == key))
    if row:
        row.setting_value = value
        row.updated_at = now_utc()
        return row
    row = MLSettingORM(setting_key=key, setting_value=value, updated_at=now_utc())
    db.add(row)
    db.flush()
    return row


def get_setting(db: Session, key: str) -> MLSettingORM | None:
    return db.scalar(select(MLSettingORM).where(MLSettingORM.setting_key == key))


def insert_training_row(db: Session, **kwargs) -> MLTrainingRowORM:
    row = MLTrainingRowORM(**kwargs)
    db.add(row)
    db.flush()
    return row


def delete_training_row_for_timestamp(db: Session, asset_id: str, snapshot_at) -> None:
    db.execute(delete(MLTrainingRowORM).where(MLTrainingRowORM.asset_id == asset_id, MLTrainingRowORM.snapshot_at == snapshot_at))


def count_training_rows(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(MLTrainingRowORM)) or 0


def list_training_rows(db: Session, limit: int = 10000) -> list[MLTrainingRowORM]:
    return db.scalars(select(MLTrainingRowORM).order_by(MLTrainingRowORM.snapshot_at.asc()).limit(limit)).all()


def list_training_rows_for_target(
    db: Session, target_name: str, asset_id: str | None = None, limit: int = 10000
) -> list[MLTrainingRowORM]:
    column = getattr(MLTrainingRowORM, target_name)
    q = select(MLTrainingRowORM).where(column.is_not(None))
    if asset_id is not None:
        q = q.where(MLTrainingRowORM.asset_id == asset_id)
    return db.scalars(q.order_by(MLTrainingRowORM.snapshot_at.asc()).limit(limit)).all()


def insert_model_run(
    db: Session, model_name: str, target_name: str, dataset_rows: int,
    metrics_json: str, model_path: str, is_active: bool,
    asset_id: str | None = None,
) -> MLModelRunORM:
    if is_active:
        # Dezaktywuj tylko poprzednie wersje tego samego modelu (nie innych typów)
        q = select(MLModelRunORM).where(
            MLModelRunORM.model_name == model_name,
            MLModelRunORM.target_name == target_name,
        )
        if asset_id is not None:
            q = q.where(MLModelRunORM.asset_id == asset_id)
        for row in db.scalars(q).all():
            row.is_active = False
    row = MLModelRunORM(
        model_name=model_name,
        target_name=target_name,
        asset_id=asset_id,
        trained_at=now_utc(),
        dataset_rows=dataset_rows,
        metrics_json=metrics_json,
        model_path=model_path,
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


def list_model_runs(db: Session, limit: int = 100) -> list[MLModelRunORM]:
    return db.scalars(select(MLModelRunORM).order_by(MLModelRunORM.trained_at.desc()).limit(limit)).all()


def get_active_model_run(
    db: Session, target_name: str, asset_id: str | None = None
) -> MLModelRunORM | None:
    """Szuka aktywnego modelu per-asset, fallback do globalnego."""
    if asset_id is not None:
        per_asset = db.scalar(
            select(MLModelRunORM)
            .where(MLModelRunORM.target_name == target_name,
                   MLModelRunORM.asset_id == asset_id,
                   MLModelRunORM.is_active == True)
            .order_by(MLModelRunORM.trained_at.desc()).limit(1)
        )
        if per_asset:
            return per_asset
    return db.scalar(
        select(MLModelRunORM)
        .where(MLModelRunORM.target_name == target_name,
               MLModelRunORM.is_active == True)
        .order_by(MLModelRunORM.trained_at.desc()).limit(1)
    )


def get_all_active_model_runs(
    db: Session, target_name: str, asset_id: str | None = None
) -> list[MLModelRunORM]:
    """Zwraca wszystkie aktywne modele dla danego targetu (jeden per model_name)."""
    q = select(MLModelRunORM).where(
        MLModelRunORM.target_name == target_name,
        MLModelRunORM.is_active == True,  # noqa: E712
    )
    if asset_id is not None:
        q = q.where(MLModelRunORM.asset_id == asset_id)
    return list(db.scalars(q.order_by(MLModelRunORM.trained_at.desc())).all())


def insert_backtest_result(db: Session, model_run_id: int, result_json: str) -> MLBacktestResultORM:
    row = MLBacktestResultORM(model_run_id=model_run_id, created_at=now_utc(), result_json=result_json)
    db.add(row)
    db.flush()
    return row


def list_backtest_results(db: Session, limit: int = 100) -> list[MLBacktestResultORM]:
    return db.scalars(select(MLBacktestResultORM).order_by(MLBacktestResultORM.created_at.desc()).limit(limit)).all()


def insert_prediction(db: Session, **kwargs) -> MLPredictionORM:
    row = MLPredictionORM(**kwargs)
    db.add(row)
    db.flush()
    return row


def get_latest_prediction(db: Session, asset_id: str, target_name: str) -> MLPredictionORM | None:
    return db.scalar(select(MLPredictionORM).where(MLPredictionORM.asset_id == asset_id, MLPredictionORM.target_name == target_name).order_by(MLPredictionORM.snapshot_at.desc()).limit(1))
