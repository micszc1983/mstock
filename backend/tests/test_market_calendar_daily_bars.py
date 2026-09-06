from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.market_calendar import (
    is_daily_bar_complete,
    is_market_open,
    market_for_symbol,
)


def test_gpw_daily_bar_is_incomplete_until_market_close():
    bar = datetime(2026, 8, 12, 9, 0, tzinfo=ZoneInfo("Europe/Warsaw"))

    assert not is_daily_bar_complete(
        "PKN.WA", bar,
        datetime(2026, 8, 12, 16, 59, tzinfo=ZoneInfo("Europe/Warsaw")),
    )
    assert is_daily_bar_complete(
        "PKN.WA", bar,
        datetime(2026, 8, 12, 17, 0, tzinfo=ZoneInfo("Europe/Warsaw")),
    )


def test_us_daily_bar_is_incomplete_until_nyse_close():
    bar = datetime(2026, 8, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    assert not is_daily_bar_complete(
        "AAPL", bar,
        datetime(2026, 8, 12, 15, 59, tzinfo=ZoneInfo("America/New_York")),
    )
    assert is_daily_bar_complete(
        "AAPL", bar,
        datetime(2026, 8, 12, 16, 0, tzinfo=ZoneInfo("America/New_York")),
    )


def test_london_etfs_use_lse_hours_not_nyse_hours():
    bar = datetime(2026, 8, 12, 0, 0, tzinfo=ZoneInfo("Europe/London"))

    assert market_for_symbol("NUCL.L") == "LSE"
    assert is_market_open(
        "NUCL.L",
        datetime(2026, 8, 12, 15, 0, tzinfo=ZoneInfo("Europe/London")),
    )
    assert not is_daily_bar_complete(
        "NUCL.L", bar,
        datetime(2026, 8, 12, 16, 29, tzinfo=ZoneInfo("Europe/London")),
    )
    assert is_daily_bar_complete(
        "NUCL.L", bar,
        datetime(2026, 8, 12, 16, 30, tzinfo=ZoneInfo("Europe/London")),
    )


def test_previous_session_bar_remains_complete_during_next_session():
    bar = datetime(2026, 8, 11, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    now = datetime(2026, 8, 12, 10, 0, tzinfo=ZoneInfo("America/New_York"))

    assert is_daily_bar_complete("AAPL", bar, now)


def test_metals_future_bar_waits_for_cme_settlement():
    bar = datetime(2026, 8, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    assert market_for_symbol("GC=F") == "CME"
    assert not is_daily_bar_complete(
        "GC=F", bar,
        datetime(2026, 8, 12, 15, 59, tzinfo=ZoneInfo("America/Chicago")),
    )
    assert is_daily_bar_complete(
        "GC=F", bar,
        datetime(2026, 8, 12, 16, 0, tzinfo=ZoneInfo("America/Chicago")),
    )
