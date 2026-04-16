from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.mappers import alert_rule_to_schema, alert_to_schema
from app.repositories.alerts import get_alert, insert_alert_rule, list_alert_rules, list_alerts, list_alerts_for_asset
from app.repositories.assets import get_asset
from app.schemas.alerts import AlertResponse, AlertRuleCreate, AlertRuleResponse

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=list[AlertResponse])
def get_alerts(limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)) -> list[AlertResponse]:
    return [alert_to_schema(row) for row in list_alerts(db, limit=limit)]


@router.get("/assets/{asset_id}/alerts", response_model=list[AlertResponse])
def get_asset_alerts(asset_id: str, limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)) -> list[AlertResponse]:
    if get_asset(db, asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset: {asset_id}")
    return [alert_to_schema(row) for row in list_alerts_for_asset(db, asset_id, limit=limit)]


@router.post("/alerts/{alert_id}/mark-seen", response_model=AlertResponse)
def mark_seen(alert_id: int, db: Session = Depends(get_db)) -> AlertResponse:
    row = get_alert(db, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown alert: {alert_id}")
    row.status = "seen"
    db.commit()
    db.refresh(row)
    return alert_to_schema(row)


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(alert_id: int, db: Session = Depends(get_db)) -> AlertResponse:
    row = get_alert(db, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown alert: {alert_id}")
    row.status = "resolved"
    db.commit()
    db.refresh(row)
    return alert_to_schema(row)


@router.get("/alert-rules", response_model=list[AlertRuleResponse])
def get_rules(db: Session = Depends(get_db)) -> list[AlertRuleResponse]:
    return [alert_rule_to_schema(row) for row in list_alert_rules(db)]


@router.post("/alert-rules", response_model=AlertRuleResponse)
def create_rule(payload: AlertRuleCreate, db: Session = Depends(get_db)) -> AlertRuleResponse:
    row = insert_alert_rule(
        db,
        rule_name=payload.rule_name,
        is_enabled=payload.is_enabled,
        alert_type=payload.alert_type,
        asset_scope=payload.asset_scope,
        threshold_json=payload.threshold_json,
        severity=payload.severity,
        cooldown_minutes=payload.cooldown_minutes,
    )
    db.commit()
    db.refresh(row)
    return alert_rule_to_schema(row)
