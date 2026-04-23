from __future__ import annotations

from datetime import date, datetime, timezone

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AssetORM, InsiderTradeORM, ShortInterestORM
from app.repositories.insider import upsert_insider_trade, upsert_short_interest

# Finnhub transaction code → simplified type
_CODE_TO_TYPE: dict[str, str] = {
    "P": "buy",   # Purchase
    "S": "sell",  # Sale
    "D": "sell",  # Disposal
    "M": "other", # Exercise/conversion
    "F": "other", # Tax withholding
    "G": "other", # Gift
    "J": "other", # Other (court order etc.)
    "A": "other", # Grant/award
    "U": "other", # Return of shares
    "W": "other", # Will/inheritance
    "X": "other", # Exercise of derivative
    "Z": "other", # Deposit/withdrawal from voting trust
}


def _sync_insider_finnhub(db: Session, asset: AssetORM) -> int:
    if not settings.finnhub_api_key or asset.type != "stock":
        return 0

    symbol = (asset.price_symbol or asset.symbol).upper()
    # Strip exchange suffix (.WA, .L etc.) — Finnhub uses bare tickers
    if "." in symbol:
        symbol = symbol.split(".")[0]

    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/stock/insider-transactions",
            params={"symbol": symbol, "token": settings.finnhub_api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[insider] Finnhub error for {symbol}: {exc}")
        return 0

    count = 0
    for t in data.get("data") or []:
        try:
            tx_str = t.get("transactionDate") or t.get("filingDate")
            if not tx_str:
                continue
            tx_date = date.fromisoformat(str(tx_str)[:10])
            fl_str = t.get("filingDate")
            filing_date = date.fromisoformat(str(fl_str)[:10]) if fl_str else None
            code = str(t.get("transactionCode") or "").upper()[:4]
            shares_raw = t.get("change") if t.get("change") is not None else t.get("share")
            price_raw = t.get("transactionPrice")
            shares = float(shares_raw) if shares_raw is not None else None
            price = float(price_raw) if price_raw is not None else None
            value = (shares * price) if (shares is not None and price is not None) else None

            trade = InsiderTradeORM(
                asset_id=asset.id,
                transaction_date=tx_date,
                filing_date=filing_date,
                name=str(t.get("name") or "Unknown")[:200],
                transaction_code=code or "?",
                transaction_type=_CODE_TO_TYPE.get(code, "other"),
                shares=shares,
                price=price,
                value=value,
                source="finnhub",
            )
            upsert_insider_trade(db, trade)
            count += 1
        except Exception as exc:
            print(f"[insider] trade parse error: {exc}")

    db.commit()
    return count


def _sync_short_interest_yfinance(db: Session, asset: AssetORM) -> int:
    if asset.type != "stock":
        return 0

    symbol = (asset.price_symbol or asset.symbol).upper()
    try:
        import yfinance as yf  # type: ignore
        ticker = yf.Ticker(symbol)
        info = ticker.info
        shares_short = info.get("sharesShort")
        short_ratio = info.get("shortRatio")
        short_pct = info.get("shortPercentOfFloat")

        if shares_short is None and short_ratio is None and short_pct is None:
            return 0

        si = ShortInterestORM(
            asset_id=asset.id,
            report_date=date.today(),
            shares_short=float(shares_short) if shares_short is not None else None,
            short_percent_float=float(short_pct) if short_pct is not None else None,
            short_ratio=float(short_ratio) if short_ratio is not None else None,
        )
        upsert_short_interest(db, si)
        db.commit()
        return 1
    except Exception as exc:
        print(f"[insider] short interest error for {symbol}: {exc}")
        return 0


def sync_insider_data(db: Session, asset: AssetORM) -> dict[str, int]:
    trades = _sync_insider_finnhub(db, asset)
    si = _sync_short_interest_yfinance(db, asset)
    return {"insider_trades": trades, "short_interest": si}


def sync_all_insider_data(db: Session) -> dict[str, dict[str, int]]:
    from app.repositories.assets import list_assets
    results: dict[str, dict[str, int]] = {}
    for asset in list_assets(db):
        try:
            results[asset.id] = sync_insider_data(db, asset)
        except Exception as exc:
            print(f"[insider] sync error for {asset.id}: {exc}")
    return results
