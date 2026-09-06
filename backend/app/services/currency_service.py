"""Currency conversion for portfolio accounting (base currency: PLN)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

import httpx

from app.core.config import settings


@lru_cache(maxsize=512)
def _nbp_rate(currency: str, effective_date: str | None) -> float:
    code = currency.upper()
    if code == "PLN":
        return 1.0
    if settings.testing:
        return 1.0
    suffix = f"/{effective_date}" if effective_date else ""
    url = f"https://api.nbp.pl/api/exchangerates/rates/a/{code.lower()}{suffix}/"
    response = httpx.get(
        url,
        params={"format": "json"},
        timeout=settings.sync_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    rates = payload.get("rates") or []
    if not rates or not rates[0].get("mid"):
        raise ValueError(f"NBP nie zwrócił kursu {code}/PLN")
    return float(rates[0]["mid"])


def pln_rate(currency: str, on_date: date | None = None) -> float:
    """Return PLN paid for one currency unit, using prior NBP day if needed."""
    code = (currency or "PLN").upper()
    if code == "PLN":
        return 1.0
    day = on_date or datetime.now(timezone.utc).date()
    last_error: Exception | None = None
    for _ in range(8):
        try:
            return _nbp_rate(code, day.isoformat())
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            day -= timedelta(days=1)
    raise ValueError(f"Brak kursu NBP {code}/PLN dla {on_date}: {last_error}")


def to_pln(value: float | None, currency: str, on_date: date | None = None) -> float | None:
    if value is None:
        return None
    return float(value) * pln_rate(currency, on_date)
