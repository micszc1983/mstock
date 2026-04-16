from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AlertORM, AlertRuleORM


def insert_alert(
    db: Session,
    asset_id: str,
    created_at,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    status: str,
    trigger_value: float,
    threshold_value: float,
    snapshot_json: str,
) -> AlertORM:
    row = AlertORM(
        asset_id=asset_id,
        created_at=created_at,
        alert_type=alert_type,
        severity=severity,
        title=title,
        message=message,
        status=status,
        trigger_value=trigger_value,
        threshold_value=threshold_value,
        snapshot_json=snapshot_json,
    )
    db.add(row)
    db.flush()
    return row


def list_alerts(db: Session, limit: int = 100) -> list[AlertORM]:
    stmt = select(AlertORM).order_by(AlertORM.created_at.desc()).limit(limit)
    return db.scalars(stmt).all()


def list_alerts_for_asset(db: Session, asset_id: str, limit: int = 100) -> list[AlertORM]:
    stmt = (
        select(AlertORM)
        .where(AlertORM.asset_id == asset_id)
        .order_by(AlertORM.created_at.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()


def get_recent_similar_alert(db: Session, asset_id: str, alert_type: str):
    stmt = (
        select(AlertORM)
        .where(AlertORM.asset_id == asset_id, AlertORM.alert_type == alert_type)
        .order_by(AlertORM.created_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def get_alert(db: Session, alert_id: int) -> AlertORM | None:
    return db.get(AlertORM, alert_id)


def insert_alert_rule(
    db: Session,
    rule_name: str,
    is_enabled: bool,
    alert_type: str,
    asset_scope: str,
    threshold_json: str,
    severity: str,
    cooldown_minutes: int,
) -> AlertRuleORM:
    row = AlertRuleORM(
        rule_name=rule_name,
        is_enabled=is_enabled,
        alert_type=alert_type,
        asset_scope=asset_scope,
        threshold_json=threshold_json,
        severity=severity,
        cooldown_minutes=cooldown_minutes,
    )
    db.add(row)
    db.flush()
    return row


def list_alert_rules(db: Session) -> list[AlertRuleORM]:
    stmt = select(AlertRuleORM).order_by(AlertRuleORM.id.asc())
    return db.scalars(stmt).all()
