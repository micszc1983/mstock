from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def _easter(year: int) -> date:
    """Gregorian Easter Sunday (Meeus/Jones/Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f, g = (b + 8) // 25, (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return date(year, month, (h + l - 7 * m + 114) % 31 + 1)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    first_next = date(year + (1 if month == 12 else 0), month % 12 + 1, 1)
    last = first_next - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def nyse_holidays(year: int) -> set[date]:
    easter = _easter(year)
    holidays = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),          # MLK
        _nth_weekday(year, 2, 0, 3),          # Presidents' Day
        easter - timedelta(days=2),           # Good Friday
        _last_weekday(year, 5, 0),            # Memorial Day
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),          # Labor Day
        _nth_weekday(year, 11, 3, 4),         # Thanksgiving
        _observed(date(year, 12, 25)),
    }
    if year >= 2022:
        holidays.add(_observed(date(year, 6, 19)))
    next_new_year_observed = _observed(date(year + 1, 1, 1))
    if next_new_year_observed.year == year:
        holidays.add(next_new_year_observed)
    return holidays


def gpw_holidays(year: int) -> set[date]:
    easter = _easter(year)
    return {
        date(year, 1, 1), date(year, 1, 6),
        easter + timedelta(days=1),
        date(year, 5, 1), date(year, 5, 3),
        easter + timedelta(days=60),
        date(year, 8, 15), date(year, 11, 1), date(year, 11, 11),
        date(year, 12, 24), date(year, 12, 25), date(year, 12, 26),
    }


def market_for_symbol(symbol: str) -> str:
    return "GPW" if symbol.upper().endswith(".WA") else "NYSE"


def _nyse_close_minutes(day: date) -> int:
    """13:00 ET w typowe skrócone sesje, w pozostałe dni 16:00 ET."""
    thanksgiving = _nth_weekday(day.year, 11, 3, 4)
    early = {
        thanksgiving + timedelta(days=1),
        date(day.year, 12, 24),
    }
    july_3 = date(day.year, 7, 3)
    if july_3.weekday() < 5:
        early.add(july_3)
    return 13 * 60 if day in early else 16 * 60


def is_market_open(symbol: str, now: datetime | None = None) -> bool:
    market = market_for_symbol(symbol)
    zone = ZoneInfo("Europe/Warsaw" if market == "GPW" else "America/New_York")
    local = (now or datetime.now(ZoneInfo("UTC"))).astimezone(zone)
    if local.weekday() >= 5:
        return False
    holidays = gpw_holidays(local.year) if market == "GPW" else nyse_holidays(local.year)
    if local.date() in holidays:
        return False
    minutes = local.hour * 60 + local.minute
    if market == "GPW":
        return 9 * 60 <= minutes < 17 * 60
    return 9 * 60 + 30 <= minutes < _nyse_close_minutes(local.date())


def any_supported_market_open(now: datetime | None = None) -> bool:
    return is_market_open("PKN.WA", now) or is_market_open("AAPL", now)
