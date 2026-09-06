from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import AssetORM, PricePointORM
from app.db.session import get_db
from app.schemas.portfolio import AggregateDashboardResponse, CompareAssetsResponse
from app.services.aggregate_dashboard import build_asset_overview_for_ids, compare_assets
from app.services.currency_service import to_pln
from app.repositories.portfolio_positions import (
    add_purchase_to_position,
    delete_position,
    get_position,
    list_positions,
    update_position,
    upsert_position,
)

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
    quantity: float = Field(gt=0, le=1_000_000_000_000_000)
    avg_buy_price: Optional[float] = Field(default=None, gt=0, le=1_000_000_000_000_000)


class PositionUpdatePayload(BaseModel):
    asset_id: str = Field(min_length=1, max_length=64)
    quantity: float = Field(gt=0, le=1_000_000_000_000_000)
    avg_buy_price: Optional[float] = Field(default=None, gt=0, le=1_000_000_000_000_000)
    purchase_date: Optional[date] = None


class PositionResponse(BaseModel):
    asset_id: str
    quantity: float
    avg_buy_price: Optional[float]
    purchase_date: Optional[date] = None
    invested_amount: Optional[float] = None
    cost_currency: str = "PLN"
    updated_at: datetime


class PortfolioValuationResponse(BaseModel):
    asset_id: str
    source_currency: str
    fx_rate_to_pln: float
    last_price_source: Optional[float]
    last_price_pln: Optional[float]
    current_value_pln: Optional[float]


class HistoricalPurchasePayload(BaseModel):
    purchase_date: date
    invested_amount: float = Field(gt=0, le=1_000_000_000_000_000)
    purchase_price: Optional[float] = Field(default=None, gt=0, le=1_000_000_000_000_000)


def _position_response(db: Session, row) -> PositionResponse:
    avg_buy_price = row.avg_buy_price
    invested_amount = row.invested_amount
    if row.cost_currency != "PLN":
        asset = db.get(AssetORM, row.asset_id)
        source_currency = asset.currency if asset is not None else "PLN"
        if source_currency != "PLN":
            try:
                rate = float(to_pln(1.0, source_currency, row.purchase_date) or 1.0)
                avg_buy_price = avg_buy_price * rate if avg_buy_price is not None else None
                invested_amount = invested_amount * rate if invested_amount is not None else None
            except ValueError:
                # Nie zgaduj kursu: koszt pozostaje nieznany zamiast fałszywego PLN.
                avg_buy_price = None
                invested_amount = None
    return PositionResponse(
        asset_id=row.asset_id,
        quantity=row.quantity,
        avg_buy_price=avg_buy_price,
        purchase_date=row.purchase_date,
        invested_amount=invested_amount,
        cost_currency="PLN",
        updated_at=row.updated_at,
    )


@router.get("/portfolio/positions", response_model=list[PositionResponse])
def get_positions(db: Session = Depends(get_db)) -> list[PositionResponse]:
    return [_position_response(db, p) for p in list_positions(db)]


@router.get("/portfolio/valuations", response_model=list[PortfolioValuationResponse])
def get_portfolio_valuations(db: Session = Depends(get_db)) -> list[PortfolioValuationResponse]:
    results: list[PortfolioValuationResponse] = []
    for position in list_positions(db):
        asset = db.get(AssetORM, position.asset_id)
        if asset is None:
            continue
        latest = (
            db.query(PricePointORM)
            .filter(PricePointORM.asset_id == position.asset_id)
            .order_by(PricePointORM.timestamp.desc())
            .first()
        )
        try:
            rate = 1.0 if asset.currency == "PLN" else float(to_pln(1.0, asset.currency) or 1.0)
        except ValueError:
            rate = 0.0
        source_price = float(latest.close) if latest is not None else None
        price_pln = source_price * rate if source_price is not None and rate > 0 else None
        results.append(PortfolioValuationResponse(
            asset_id=position.asset_id,
            source_currency=asset.currency,
            fx_rate_to_pln=rate,
            last_price_source=source_price,
            last_price_pln=price_pln,
            current_value_pln=position.quantity * price_pln if price_pln is not None else None,
        ))
    return results


@router.put("/portfolio/positions/{asset_id}", response_model=PositionResponse)
def set_position(asset_id: str, payload: PositionPayload, db: Session = Depends(get_db)) -> PositionResponse:
    normalized_asset_id = asset_id.lower()
    if db.get(AssetORM, normalized_asset_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono aktywa.")
    row = upsert_position(db, normalized_asset_id, payload.quantity, payload.avg_buy_price)
    db.commit()
    db.refresh(row)
    return _position_response(db, row)


@router.patch("/portfolio/positions/{asset_id}", response_model=PositionResponse)
def edit_position(
    asset_id: str,
    payload: PositionUpdatePayload,
    db: Session = Depends(get_db),
) -> PositionResponse:
    current_id = asset_id.lower()
    new_asset_id = payload.asset_id.strip().lower()
    if get_position(db, current_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono pozycji w portfelu.")
    if db.get(AssetORM, new_asset_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono wybranego aktywa.")
    if new_asset_id != current_id and get_position(db, new_asset_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="Wybrane aktywo jest już w portfelu. Usuń duplikat albo użyj funkcji dokupienia.",
        )
    if payload.purchase_date and payload.purchase_date > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=422, detail="Data zakupu nie może być z przyszłości.")

    row = update_position(
        db,
        current_id,
        new_asset_id=new_asset_id,
        quantity=payload.quantity,
        avg_buy_price=payload.avg_buy_price,
        purchase_date=payload.purchase_date,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono pozycji w portfelu.")
    db.commit()
    db.refresh(row)
    return _position_response(db, row)


@router.post("/portfolio/positions/{asset_id}/historical-purchase", response_model=PositionResponse)
def add_historical_purchase(
    asset_id: str,
    payload: HistoricalPurchasePayload,
    db: Session = Depends(get_db),
) -> PositionResponse:
    normalized_asset_id = asset_id.lower()
    if db.get(AssetORM, normalized_asset_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono aktywa.")
    if payload.purchase_date > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=422, detail="Data zakupu nie może być z przyszłości.")

    purchase_price = payload.purchase_price
    if purchase_price is None:
        start = datetime.combine(payload.purchase_date, time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        price_point = (
            db.query(PricePointORM)
            .filter(
                PricePointORM.asset_id == normalized_asset_id,
                PricePointORM.timestamp >= start,
                PricePointORM.timestamp < end,
            )
            .order_by(PricePointORM.timestamp.desc())
            .first()
        )
        if price_point is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Brak notowania dla wskazanej daty. Wybierz dzień sesyjny "
                    "albo podaj własną cenę wykonania z potwierdzenia transakcji."
                ),
            )
        asset = db.get(AssetORM, normalized_asset_id)
        try:
            purchase_price = to_pln(
                price_point.close,
                asset.currency if asset is not None else "PLN",
                payload.purchase_date,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Nie udało się pobrać historycznego kursu walutowego: {exc}",
            ) from exc

    quantity = payload.invested_amount / purchase_price
    existing = get_position(db, normalized_asset_id)
    if existing is not None and existing.cost_currency != "PLN":
        asset = db.get(AssetORM, normalized_asset_id)
        source_currency = asset.currency if asset is not None else "PLN"
        try:
            legacy_rate = float(to_pln(
                1.0,
                source_currency,
                existing.purchase_date or payload.purchase_date,
            ) or 1.0)
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Nie udało się przeliczyć dotychczasowej pozycji na PLN: {exc}",
            ) from exc
        if existing.avg_buy_price is not None:
            existing.avg_buy_price *= legacy_rate
        if existing.invested_amount is not None:
            existing.invested_amount *= legacy_rate
        existing.cost_currency = "PLN"
    try:
        row = add_purchase_to_position(
            db,
            normalized_asset_id,
            quantity,
            purchase_price,
            payload.purchase_date,
            payload.invested_amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return _position_response(db, row)


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
