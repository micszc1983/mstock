"""
Wskaźniki techniczne obliczane z historii cen OHLCV.
Wszystkie funkcje przyjmują zwykłe listy/tablice i są niezależne od ORM.
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np


# ── Podstawowe wskaźniki ─────────────────────────────────────────────────────

def calc_rsi(closes: List[float], period: int = 14) -> float:
    """RSI Wildera. Zwraca wartość 0–100. Wymaga co najmniej period+1 wartości."""
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-(period + 1):])
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def calc_ema(values: List[float], period: int) -> List[float]:
    """Exponential Moving Average — zwraca listę tej samej długości co values."""
    if not values:
        return []
    k = 2.0 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def calc_macd_histogram(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float:
    """
    MACD histogram = MACD_line - signal_line.
    Dodatni → momentum wzrostowy. Ujemny → spadkowy.
    Zwraca 0.0 gdy za mało danych.
    """
    if len(closes) < slow + signal:
        return 0.0
    ema_fast   = calc_ema(closes, fast)
    ema_slow   = calc_ema(closes, slow)
    macd_line  = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = calc_ema(macd_line, signal)
    histogram   = macd_line[-1] - signal_line[-1]
    # Normalizuj do ceny żeby był porównywalny między aktywami
    price = closes[-1] if closes[-1] != 0 else 1.0
    return float(histogram / price * 100)


def calc_bb_pct(closes: List[float], period: int = 20) -> float:
    """
    Bollinger Band %B: pozycja ceny wewnątrz pasm.
    0 = dolne pasmo, 0.5 = środek (SMA), 1 = górne pasmo.
    Może wyjść poza 0–1 gdy cena przebija pasma.
    """
    if len(closes) < period:
        return 0.5
    window = closes[-period:]
    sma  = np.mean(window)
    std  = np.std(window, ddof=1)
    if std == 0:
        return 0.5
    upper = sma + 2 * std
    lower = sma - 2 * std
    price = closes[-1]
    return float((price - lower) / (upper - lower))


def calc_volume_ratio(volumes: List[float], period: int = 20) -> float:
    """
    Stosunek bieżącego wolumenu do średniej z ostatnich `period` dni.
    > 1 = wyższy niż normalnie (sygnał aktywności). Zwraca 1.0 gdy brak danych.
    """
    if len(volumes) < period + 1:
        return 1.0
    avg = np.mean(volumes[-(period + 1):-1])
    if avg == 0:
        return 1.0
    return float(volumes[-1] / avg)


def calc_price_vs_52w_high(closes: List[float], period: int = 252) -> float:
    """
    Cena jako % rocznego maksimum. 1.0 = na szczycie, <1 = poniżej.
    Przydatny do oceny momentum długoterminowego.
    """
    if len(closes) < 2:
        return 1.0
    window = closes[-period:]
    high = max(window)
    if high == 0:
        return 1.0
    return float(closes[-1] / high)


def calc_above_sma(closes: List[float], period: int = 200) -> float:
    """1.0 jeśli cena > SMA(period), 0.0 w przeciwnym razie."""
    if len(closes) < period:
        return 0.5  # nieznany
    sma = np.mean(closes[-period:])
    return 1.0 if closes[-1] > sma else 0.0


# ── SPY jako benchmark rynku ─────────────────────────────────────────────────

_spy_cache: Dict[date, float] = {}   # date → 5d return (%)
_spy_fetched_at: float = 0.0
_SPY_TTL = 3600.0  # 1 h


def fetch_spy_returns(api_key: str, days: int = 520) -> Dict[date, float]:
    """
    Pobiera dzienne ceny SPY z Twelvedata i zwraca słownik {date: return_5d_pct}.
    Cachuje wynik na 1h. Nie rzuca wyjątku — przy błędzie zwraca pusty słownik.
    """
    global _spy_cache, _spy_fetched_at
    if time.time() - _spy_fetched_at < _SPY_TTL and _spy_cache:
        return _spy_cache

    try:
        import httpx
        r = httpx.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol": "SPY", "interval": "1day", "outputsize": days, "apikey": api_key},
            timeout=15.0,
        )
        data = r.json()
        if data.get("status") != "ok":
            return {}
        values = data.get("values", [])
        # values: [{"datetime": "YYYY-MM-DD", "close": "..."}] — newest first
        closes: List[Tuple[date, float]] = []
        for v in reversed(values):
            try:
                d = date.fromisoformat(v["datetime"])
                c = float(v["close"])
                closes.append((d, c))
            except Exception:
                continue

        # Zbuduj słownik date → 5d forward return
        result: Dict[date, float] = {}
        date_list  = [d for d, _ in closes]
        close_list = [c for _, c in closes]
        for i, (d, c) in enumerate(closes):
            if i + 5 < len(closes):
                future = close_list[i + 5]
                result[d] = (future - c) / c * 100.0
            else:
                result[d] = 0.0  # brak przyszłości — nie używane w predykcji

        _spy_cache = result
        _spy_fetched_at = time.time()
        return result
    except Exception:
        return {}


def compute_all(
    closes: List[float],
    volumes: List[float],
    spy_returns: Dict[date, float],
    snap_date: date,
    asset_return_5d: Optional[float],
) -> Dict[str, float]:
    """
    Liczy wszystkie wskaźniki techniczne dla danego punktu czasowego.
    Przyjmuje ceny/wolumeny POSORTOWANE rosnąco (od najstarszej do snap_date włącznie).
    """
    spy_ret = spy_returns.get(snap_date, None)

    alpha = None
    if asset_return_5d is not None and spy_ret is not None:
        alpha = asset_return_5d - spy_ret

    return {
        "rsi_14":           calc_rsi(closes),
        "macd_histogram":   calc_macd_histogram(closes),
        "bb_pct":           calc_bb_pct(closes),
        "volume_ratio_20d": calc_volume_ratio(volumes),
        "price_vs_52w_high": calc_price_vs_52w_high(closes),
        "above_sma200":     calc_above_sma(closes),
        "spy_return_5d":    spy_ret if spy_ret is not None else 0.0,
        "alpha_vs_spy_5d":  alpha if alpha is not None else 0.0,
    }
