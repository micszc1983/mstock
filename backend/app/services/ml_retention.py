"""Ograniczona, referencyjnie bezpieczna retencja przebiegów modeli ML."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import delete, func, select, union
from sqlalchemy.orm import Session

from app.db.models import (
    MLBacktestResultORM,
    MLModelMonitorORM,
    MLModelRunORM,
    MLPredictionORM,
)


@dataclass(frozen=True)
class ModelRunRetentionReport:
    keep_per_group: int
    total_before: int
    recent_run_ids: int
    referenced_run_ids: int
    active_run_ids: int
    protected_run_ids: int
    would_delete: int
    deleted: int

    def to_dict(self) -> dict:
        return asdict(self)


def _protected_ids(keep_per_group: int):
    ranked = select(
        MLModelRunORM.id.label("id"),
        func.row_number().over(
            partition_by=(
                MLModelRunORM.asset_id,
                MLModelRunORM.market_segment,
                MLModelRunORM.target_name,
                MLModelRunORM.model_name,
            ),
            order_by=(MLModelRunORM.trained_at.desc(), MLModelRunORM.id.desc()),
        ).label("retention_rank"),
    ).subquery()
    recent = select(ranked.c.id).where(ranked.c.retention_rank <= keep_per_group)
    active = select(MLModelRunORM.id).where(MLModelRunORM.is_active.is_(True))
    predictions = select(MLPredictionORM.model_run_id.label("id"))
    backtests = select(MLBacktestResultORM.model_run_id.label("id"))
    monitors = select(MLModelMonitorORM.model_run_id.label("id"))
    return ranked, union(recent, active, predictions, backtests, monitors).subquery()


def prune_model_runs(
    db: Session,
    *,
    keep_per_group: int = 15,
    dry_run: bool = True,
) -> ModelRunRetentionReport:
    """Zostawia N najnowszych runów na zakres/cel/model oraz wszystkie referencje.

    Zakres jest zdefiniowany przez ``asset_id`` lub ``market_segment``. Aktywny
    champion nigdy nie jest usuwany, nawet gdy z powodu niespójnych historycznych
    dat wypadłby poza limit. Zachowanie referencji pozwala później włączyć klucze
    obce PostgreSQL bez utraty predykcji, backtestów ani monitoringu.
    """
    keep = max(1, int(keep_per_group))
    ranked, protected = _protected_ids(keep)
    total = int(db.scalar(select(func.count()).select_from(MLModelRunORM)) or 0)
    recent_count = int(db.scalar(
        select(func.count()).select_from(ranked).where(ranked.c.retention_rank <= keep)
    ) or 0)
    active_count = int(db.scalar(
        select(func.count()).select_from(MLModelRunORM).where(MLModelRunORM.is_active.is_(True))
    ) or 0)
    referenced = union(
        select(MLPredictionORM.model_run_id.label("id")),
        select(MLBacktestResultORM.model_run_id.label("id")),
        select(MLModelMonitorORM.model_run_id.label("id")),
    ).subquery()
    referenced_count = int(db.scalar(select(func.count()).select_from(referenced)) or 0)
    protected_count = int(db.scalar(select(func.count()).select_from(protected)) or 0)
    delete_filter = MLModelRunORM.id.not_in(select(protected.c.id))
    delete_count = int(db.scalar(
        select(func.count()).select_from(MLModelRunORM).where(delete_filter)
    ) or 0)
    deleted = 0
    if not dry_run and delete_count:
        result = db.execute(
            delete(MLModelRunORM).where(delete_filter).execution_options(synchronize_session=False)
        )
        deleted = int(result.rowcount or delete_count)
        db.commit()
    return ModelRunRetentionReport(
        keep_per_group=keep,
        total_before=total,
        recent_run_ids=recent_count,
        referenced_run_ids=referenced_count,
        active_run_ids=active_count,
        protected_run_ids=protected_count,
        would_delete=delete_count,
        deleted=deleted,
    )
