from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.portfolio import AggregateDashboardResponse, CompareAssetsResponse
from app.services.aggregate_dashboard import build_asset_overview_for_ids, compare_assets
from app.repositories.portfolio_positions import delete_position, list_positions, upsert_position

router = APIRouter(tags=["portfolio"])


# ── Aggregate dashboard (istniejące) ─────────────────────────────────────────

@router.get("/dashboard/aggregate", response_model=AggregateDashboardResponse)
def aggregate_dashboard(asset_ids: str = Query(...), db: Session = Depends(get_db)) -> AggregateDashboardResponse:
    ids = [item.strip().lower() for item in asset_ids.split(",") if item.strip()]
    return AggregateDashboardResponse(asset_ids=ids, rows=build_asset_overview_for_ids(db, ids))


@router.get("/compare/assets", response_model=CompareAssetsResponse)
def compare_assets_endpoint(asset_ids: str = Query(...), db: Session = Depends(get_db)) -> CompareAssetsResponse:
    ids = [item.strip().lower() for item in asset_ids.split(",") if item.strip()]
    return compare_assets(db, ids)


# ── Portfolio positions ───────────────────────────────────────────────────────

class PositionPayload(BaseModel):
    quantity: float
    avg_buy_price: Optional[float] = None


class PositionResponse(BaseModel):
    asset_id: str
    quantity: float
    avg_buy_price: Optional[float]


@router.get("/portfolio/positions", response_model=list[PositionResponse])
def get_positions(db: Session = Depends(get_db)) -> list[PositionResponse]:
    return [PositionResponse(asset_id=p.asset_id, quantity=p.quantity, avg_buy_price=p.avg_buy_price)
            for p in list_positions(db)]


@router.put("/portfolio/positions/{asset_id}", response_model=PositionResponse)
def set_position(asset_id: str, payload: PositionPayload, db: Session = Depends(get_db)) -> PositionResponse:
    row = upsert_position(db, asset_id.lower(), payload.quantity, payload.avg_buy_price)
    db.commit()
    db.refresh(row)
    return PositionResponse(asset_id=row.asset_id, quantity=row.quantity, avg_buy_price=row.avg_buy_price)


@router.delete("/portfolio/positions/{asset_id}", status_code=204)
def remove_position(asset_id: str, db: Session = Depends(get_db)) -> None:
    delete_position(db, asset_id.lower())
    db.commit()


# ── Portfolio report + email ──────────────────────────────────────────────────

class SendReportPayload(BaseModel):
    to_email: str = "dev@coad.pl"
    recommendations: dict  # {asset_id: {recommendation, ml_prediction, forecast_dir_5d, forecast_dir_20d, last_price, currency}}


@router.post("/portfolio/send-report")
def send_report(payload: SendReportPayload, db: Session = Depends(get_db)) -> dict:
    from app.services.portfolio_report import send_portfolio_report
    result = send_portfolio_report(db, payload.recommendations, to_email=payload.to_email)
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result["detail"])
    return result


@router.post("/portfolio/preview-report")
def preview_report(payload: SendReportPayload, db: Session = Depends(get_db)):
    """Zwraca PDF jako bajty (do podglądu / pobrania)."""
    from fastapi.responses import Response
    from app.services.portfolio_report import build_portfolio_pdf
    pdf = build_portfolio_pdf(db, payload.recommendations)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=mstock_portfel.pdf"},
    )
