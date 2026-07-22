"""
insider_service.py — dane insiderów z SEC EDGAR Form 4 (primary) + Finnhub (fallback).

SEC EDGAR jest darmowy i oficjalny. Nie wymaga klucza API.
Form 4 = obowiązek raportowania transakcji przez: dyrektorów, menedżerów 10%+ akcji.

Pipeline:
  1. Pobierz CIK dla tickera (jednorazowo, cache w pamięci).
  2. Pobierz listę Form 4 z EDGAR Submissions API.
  3. Parsuj XML każdego Form 4 → wyodrębnij transakcje.
  4. Zapisz do InsiderTradeORM (upsert by asset_id + date + name + shares).
  5. Fallback do Finnhub jeśli EDGAR nie działa i klucz skonfigurowany.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AssetORM, InsiderTradeORM, ShortInterestORM
from app.repositories.insider import upsert_insider_trade, upsert_short_interest

# SEC wymaga User-Agent z kontaktem
_SEC_UA = "MStock/1.0 micszc83@gmail.com"
_SEC_HEADERS = {"User-Agent": _SEC_UA, "Accept-Encoding": "gzip, deflate"}
_SEC_DELAY = 0.12   # 8 req/s limit SEC EDGAR

# ── Mapowania ─────────────────────────────────────────────────────────────────

_CODE_TO_TYPE: dict[str, str] = {
    "P": "buy",   # Purchase
    "S": "sell",  # Sale
    "D": "sell",  # Disposal / open-market sale
    "M": "other", # Exercise/conversion of derivative
    "F": "other", # Tax withholding (shares surrendered)
    "G": "other", # Gift
    "J": "other", # Other (court order etc.)
    "A": "other", # Grant / award
    "U": "other", # Return of shares
    "W": "other", # Will / inheritance
    "X": "other", # Exercise of derivative
    "Z": "other", # Deposit/withdrawal from voting trust
}

# ── CIK cache (ticker → CIK) ──────────────────────────────────────────────────

_cik_cache: dict[str, int | None] = {}
_cik_loaded_at: float = 0.0
_CIK_TTL = 7 * 24 * 3600  # odświeżaj raz w tygodniu


def _load_cik_map() -> dict[str, int]:
    """Pobiera mapowanie ticker→CIK z SEC EDGAR (jednorazowo)."""
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        resp = requests.get(url, headers=_SEC_HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return {v["ticker"].lower(): int(v["cik_str"]) for v in data.values()}
    except Exception as exc:
        print(f"[insider] CIK map load failed: {exc}")
        return {}


def _get_cik(ticker: str) -> int | None:
    global _cik_loaded_at
    raw = ticker.upper().split(".")[0].lower()  # AAPL.WA → aapl
    if raw in _cik_cache:
        return _cik_cache[raw]
    if time.time() - _cik_loaded_at > _CIK_TTL:
        cik_map = _load_cik_map()
        _cik_cache.update(cik_map)
        _cik_loaded_at = time.time()
    return _cik_cache.get(raw)


# ── SEC EDGAR submissions API ─────────────────────────────────────────────────

def _recent_form4_filings(cik: int, limit: int = 15) -> list[dict]:
    """Zwraca metadane ostatnich Form 4 dla spółki."""
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    time.sleep(_SEC_DELAY)
    try:
        resp = requests.get(url, headers=_SEC_HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[insider] EDGAR submissions error CIK={cik}: {exc}")
        return []

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    result = []
    for i, form in enumerate(forms):
        if form not in ("4", "4/A"):
            continue
        result.append({
            "filing_date": dates[i] if i < len(dates) else None,
            "accession": accessions[i] if i < len(accessions) else None,
            "primary_doc": primary_docs[i] if i < len(primary_docs) else None,
        })
        if len(result) >= limit:
            break
    return result


# ── Form 4 XML parser ─────────────────────────────────────────────────────────

def _parse_form4(cik: int, accession: str, filename: str) -> list[dict]:
    """Parsuje Form 4 XML. Zwraca listę transakcji {date, name, code, shares, price, value}."""
    acc_clean = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{filename}"
    time.sleep(_SEC_DELAY)
    try:
        resp = requests.get(url, headers=_SEC_HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as exc:
        print(f"[insider] Form 4 XML fetch error {url}: {exc}")
        return []

    # Nazwa insiders
    name = ""
    name_el = root.find(".//reportingOwner/reportingOwnerId/rptOwnerName")
    if name_el is not None and name_el.text:
        name = name_el.text.strip()

    # Stanowisko
    rel_el = root.find(".//reportingOwner/reportingOwnerRelationship")
    title = ""
    if rel_el is not None:
        for tag in ("officerTitle", "isDirector", "isOfficer", "isTenPercentOwner"):
            el = rel_el.find(tag)
            if el is not None and el.text and el.text.strip() not in ("", "0", "false"):
                title = tag if tag.startswith("is") else el.text.strip()
                break
    if name and title:
        name = f"{name} ({title})"

    # Filing date (z nagłówka)
    period_el = root.find(".//periodOfReport")
    filing_date_str = period_el.text.strip() if period_el is not None and period_el.text else None

    results = []

    def _val(el, path: str) -> str | None:
        found = el.find(path)
        return found.text.strip() if found is not None and found.text else None

    # Transakcje bezpośrednie (akcje zwykłe)
    for tx in root.findall(".//nonDerivativeTransaction"):
        try:
            tx_date_str = _val(tx, "transactionDate/value")
            code = (_val(tx, "transactionCoding/transactionCode") or "?").upper()
            shares_raw = _val(tx, "transactionAmounts/transactionShares/value")
            price_raw = _val(tx, "transactionAmounts/transactionPricePerShare/value")
            aod = (_val(tx, "transactionAmounts/transactionAcquiredDisposedCode/value") or "A").upper()

            tx_date = date.fromisoformat(tx_date_str) if tx_date_str else (
                date.fromisoformat(filing_date_str) if filing_date_str else date.today()
            )
            shares = float(shares_raw) if shares_raw else None
            price = float(price_raw) if price_raw else None
            # Disposed = sprzedaż → ujemna wartość shares dla czytelności
            if shares and aod == "D":
                shares = -shares
            value = abs(shares * price) if shares and price else None

            results.append({
                "date": tx_date,
                "name": name,
                "code": code,
                "shares": shares,
                "price": price,
                "value": value,
                "aod": aod,
            })
        except Exception:
            continue

    return results


# ── Główna funkcja synchronizacji SEC EDGAR ───────────────────────────────────

def _sync_insider_sec_edgar(db: Session, asset: AssetORM, limit: int = 15) -> int:
    """Pobiera transakcje insiderów z SEC EDGAR Form 4. Zwraca liczbę nowych rekordów."""
    if asset.type != "stock":
        return 0

    ticker = (asset.price_symbol or asset.symbol or "").upper().split(".")[0]
    if not ticker:
        return 0

    cik = _get_cik(ticker)
    if cik is None:
        print(f"[insider] CIK not found for {ticker}")
        return 0

    filings = _recent_form4_filings(cik, limit=limit)
    if not filings:
        return 0

    count = 0
    for filing in filings:
        acc = filing.get("accession")
        doc = filing.get("primary_doc")
        if not acc or not doc:
            continue
        # Parsuj tylko pliki XML
        if not doc.lower().endswith(".xml"):
            doc = doc.rsplit(".", 1)[0] + ".xml" if "." in doc else doc + ".xml"

        transactions = _parse_form4(cik, acc, doc)
        for tx in transactions:
            try:
                trade = InsiderTradeORM(
                    asset_id=asset.id,
                    transaction_date=tx["date"],
                    filing_date=date.fromisoformat(filing["filing_date"]) if filing.get("filing_date") else None,
                    name=tx["name"][:200],
                    transaction_code=tx["code"][:4],
                    transaction_type=_CODE_TO_TYPE.get(tx["code"], "other"),
                    shares=tx["shares"],
                    price=tx["price"],
                    value=tx["value"],
                    source="sec_edgar",
                )
                upsert_insider_trade(db, trade)
                count += 1
            except Exception as exc:
                print(f"[insider] upsert error: {exc}")

    if count:
        db.commit()
    return count


# ── Finnhub fallback ──────────────────────────────────────────────────────────

def _sync_insider_finnhub(db: Session, asset: AssetORM) -> int:
    if not settings.finnhub_api_key or asset.type != "stock":
        return 0
    symbol = (asset.price_symbol or asset.symbol).upper().split(".")[0]
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
            value = (abs(shares) * price) if (shares is not None and price is not None) else None
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
            print(f"[insider] finnhub parse error: {exc}")
    if count:
        db.commit()
    return count


# ── Short Interest ─────────────────────────────────────────────────────────────

def _sync_short_interest_yfinance(db: Session, asset: AssetORM) -> int:
    if asset.type != "stock":
        return 0
    symbol = (asset.price_symbol or asset.symbol).upper()
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info
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


# ── Sygnał / sentyment insiderów ──────────────────────────────────────────────

def get_insider_sentiment(db: Session, asset_id: str, days: int = 90) -> dict:
    """Oblicza sentyment insiderów za ostatnie N dni.
    Zwraca: net_shares, buy_value, sell_value, signal (bullish/bearish/neutral), recent_trades."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    rows = db.scalars(
        select(InsiderTradeORM)
        .where(
            InsiderTradeORM.asset_id == asset_id,
            InsiderTradeORM.transaction_date >= cutoff,
            InsiderTradeORM.transaction_type.in_(["buy", "sell"]),
        )
        .order_by(InsiderTradeORM.transaction_date.desc())
    ).all()

    buy_shares = sum(abs(r.shares or 0) for r in rows if r.transaction_type == "buy")
    sell_shares = sum(abs(r.shares or 0) for r in rows if r.transaction_type == "sell")
    buy_value = sum(r.value or 0 for r in rows if r.transaction_type == "buy")
    sell_value = sum(r.value or 0 for r in rows if r.transaction_type == "sell")
    net_shares = buy_shares - sell_shares

    n_buys = sum(1 for r in rows if r.transaction_type == "buy")
    n_sells = sum(1 for r in rows if r.transaction_type == "sell")

    if n_buys == 0 and n_sells == 0:
        signal = "neutral"
        signal_desc = "Brak transakcji insiderów"
    elif n_buys >= 2 and buy_value > sell_value * 1.5:
        signal = "bullish"
        signal_desc = f"{n_buys} zakupów insiderów ({_fmt_value(buy_value)}) — silny sygnał bychów"
    elif n_buys >= 1 and n_sells == 0:
        signal = "bullish"
        signal_desc = f"{n_buys} zakup(ów) insiderów, brak sprzedaży"
    elif n_sells >= 3 and sell_value > buy_value * 2:
        signal = "bearish"
        signal_desc = f"{n_sells} sprzedaży insiderów ({_fmt_value(sell_value)}) — realizacja zysku lub ostrzeżenie"
    elif n_sells > n_buys * 2:
        signal = "bearish"
        signal_desc = f"Przewaga sprzedaży: {n_sells} sell vs {n_buys} buy"
    else:
        signal = "neutral"
        signal_desc = f"{n_buys} zakupów, {n_sells} sprzedaży — brak wyraźnego sygnału"

    recent = [
        {
            "date": r.transaction_date.isoformat(),
            "name": r.name,
            "type": r.transaction_type,
            "code": r.transaction_code,
            "shares": r.shares,
            "price": r.price,
            "value": r.value,
        }
        for r in rows[:10]
    ]

    return {
        "asset_id": asset_id,
        "days": days,
        "signal": signal,
        "signal_description": signal_desc,
        "n_buys": n_buys,
        "n_sells": n_sells,
        "buy_shares": buy_shares,
        "sell_shares": sell_shares,
        "net_shares": net_shares,
        "buy_value": buy_value,
        "sell_value": sell_value,
        "recent_trades": recent,
    }


def _fmt_value(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.0f}"


# ── Publiczne API serwisu ──────────────────────────────────────────────────────

def sync_insider_data(db: Session, asset: AssetORM) -> dict[str, int]:
    """Próbuje SEC EDGAR, w razie braku wyników fallback do Finnhub."""
    trades = _sync_insider_sec_edgar(db, asset)
    if trades == 0:
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