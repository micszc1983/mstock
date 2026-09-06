from __future__ import annotations

from datetime import date, datetime, time, timedelta
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


def lse_holidays(year: int) -> set[date]:
    """Regular London Stock Exchange bank holidays."""
    easter = _easter(year)
    new_year = _observed(date(year, 1, 1))
    christmas = date(year, 12, 25)
    boxing_day = date(year, 12, 26)
    if christmas.weekday() == 5:       # Saturday -> Monday, Boxing Day -> Tuesday
        christmas_observed = date(year, 12, 27)
        boxing_observed = date(year, 12, 28)
    elif christmas.weekday() == 6:     # Sunday -> Tuesday; Boxing Day is Monday
        christmas_observed = date(year, 12, 27)
        boxing_observed = date(year, 12, 26)
    else:
        christmas_observed = christmas
        boxing_observed = _observed(boxing_day)
    return {
        new_year,
        easter - timedelta(days=2),
        easter + timedelta(days=1),
        _nth_weekday(year, 5, 0, 1),
        _last_weekday(year, 5, 0),
        _last_weekday(year, 8, 0),
        christmas_observed,
        boxing_observed,
    }


def market_for_symbol(symbol: str) -> str:
    upper = symbol.upper()
    if upper.endswith(".WA"):
        return "GPW"
    if upper.endswith(".L"):
        return "LSE"
    if upper.endswith("=F"):
        return "CME"
    return "NYSE"


def _market_zone(market: str) -> ZoneInfo:
    return ZoneInfo(
        "Europe/Warsaw" if market == "GPW"
        else "Europe/London" if market == "LSE"
        else "America/Chicago" if market == "CME"
        else "America/New_York"
    )


def _market_holidays(market: str, year: int) -> set[date]:
    if market == "GPW":
        return gpw_holidays(year)
    if market == "LSE":
        return lse_holidays(year)
    if market == "CME":
        return nyse_holidays(year)
    return nyse_holidays(year)


def _market_hours(market: str, day: date) -> tuple[int, int]:
    if market == "GPW":
        return 9 * 60, 17 * 60
    if market == "LSE":
        return 8 * 60, 16 * 60 + 30
    if market == "CME":
        # Metals futures: almost 24h session with the daily settlement/close
        # at 16:00 Chicago time (17:00 restart after maintenance break).
        return 17 * 60, 16 * 60
    return 9 * 60 + 30, _nyse_close_minutes(day)


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
    zone = _market_zone(market)
    local = (now or datetime.now(ZoneInfo("UTC"))).astimezone(zone)
    if local.weekday() >= 5:
        return False
    if local.date() in _market_holidays(market, local.year):
        return False
    minutes = local.hour * 60 + local.minute
    open_minutes, close_minutes = _market_hours(market, local.date())
    if market == "CME":
        if local.weekday() == 5:
            return False
        if local.weekday() == 6:
            return minutes >= open_minutes
        if local.weekday() == 4:
            return minutes < close_minutes
        return minutes < close_minutes or minutes >= open_minutes
    return open_minutes <= minutes < close_minutes


def market_session_date(symbol: str, timestamp: datetime) -> date:
    """Trading date represented by a provider's daily-bar timestamp."""
    # Providers label daily bars by date, while the exact hour only reflects
    # their timestamp convention. Preserve that label instead of converting a
    # London midnight to the preceding UTC calendar day.
    return timestamp.date()


def market_session_close(symbol: str, session_day: date) -> datetime:
    """Scheduled close of a regular daily session, returned as aware datetime."""
    market = market_for_symbol(symbol)
    _, close_minutes = _market_hours(market, session_day)
    return datetime.combine(
        session_day,
        time(hour=close_minutes // 60, minute=close_minutes % 60),
        tzinfo=_market_zone(market),
    )


def is_daily_bar_complete(
    symbol: str,
    timestamp: datetime,
    now: datetime | None = None,
) -> bool:
    """True only after the represented exchange session has closed.

    Daily providers commonly expose today's OHLCV from the opening auction.
    Such a row is useful for intraday views but must not enter daily features.
    """
    market = market_for_symbol(symbol)
    zone = _market_zone(market)
    current = (now or datetime.now(ZoneInfo("UTC"))).astimezone(zone)
    session_day = market_session_date(symbol, timestamp)
    if session_day < current.date():
        return True
    if session_day > current.date():
        return False
    if session_day.weekday() >= 5 or session_day in _market_holidays(market, session_day.year):
        return False
    return current >= market_session_close(symbol, session_day)


def any_supported_market_open(now: datetime | None = None) -> bool:
    return is_market_open("PKN.WA", now) or is_market_open("AAPL", now)
