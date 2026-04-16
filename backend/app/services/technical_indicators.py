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


# ── Makro: VIX, DXY, 10Y Treasury ────────────────────────────────────────────

_macro_cache: Dict[date, Dict[str, float]] = {}
_macro_fetched_at: float = 0.0
_MACRO_TTL = 3600.0  # 1 h


def _fetch_cboe_vix(days: int = 520) -> Dict[date, float]:
    """Pobiera VIX z CBOE (darmowe, bez klucza). Format: MM/DD/YYYY,OPEN,HIGH,LOW,CLOSE."""
    try:
        import httpx
        r = httpx.get(
            "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
            timeout=15.0,
        )
        result: Dict[date, float] = {}
        for line in r.text.splitlines()[1:]:  # pomiń nagłówek
            parts = line.strip().split(",")
            if len(parts) < 5:
                continue
            try:
                d = date(int(parts[0][6:10]), int(parts[0][:2]), int(parts[0][3:5]))
                result[d] = float(parts[4])  # CLOSE
            except Exception:
                continue
        return dict(sorted(result.items())[-days:])
    except Exception:
        return {}


def _fetch_fred_series(series_id: str, days: int = 520) -> Dict[date, float]:
    """Pobiera szereg czasowy z FRED (darmowe, bez klucza). Format CSV: date,value."""
    try:
        import httpx
        r = httpx.get(
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
            timeout=15.0,
        )
        result: Dict[date, float] = {}
        for line in r.text.splitlines()[1:]:
            parts = line.strip().split(",")
            if len(parts) < 2 or parts[1] == ".":
                continue
            try:
                result[date.fromisoformat(parts[0])] = float(parts[1])
            except Exception:
                continue
        raw = dict(sorted(result.items()))

        # FRED może mieć luki (weekendy/miesiące) — forward-fill do dziś
        if not raw:
            return {}
        all_dates = sorted(raw.keys())
        filled: Dict[date, float] = {}
        last_val = raw[all_dates[0]]
        current = all_dates[0]
        end = date.today()  # forward-fill aż do dziś (nie tylko do ostatniego FRED punktu)
        while current <= end:
            if current in raw:
                last_val = raw[current]
            filled[current] = last_val
            current = current + timedelta(days=1)

        return dict(sorted(filled.items())[-days:])
    except Exception:
        return {}


def fetch_macro_data(days: int = 520) -> Dict[date, Dict[str, float]]:
    """
    Pobiera dane makro i zwraca słownik {date: {vix, dxy, treasury_10y, ...}}.
    Źródła: CBOE (VIX), FRED GS10 (10Y Treasury), FRED DTWEXBGS (DXY/USD index).
    Cachuje wynik na 1h. Nie rzuca wyjątku — przy błędzie zwraca pusty słownik.
    """
    global _macro_cache, _macro_fetched_at
    if time.time() - _macro_fetched_at < _MACRO_TTL and _macro_cache:
        return _macro_cache

    try:
        vix_data     = _fetch_cboe_vix(days)
        treasury_data = _fetch_fred_series("GS10", days)   # 10Y yield (monthly, forward-filled)
        dxy_data      = _fetch_fred_series("DTWEXBGS", days)  # Trade-weighted USD index

        # Wyznacz zakres dat — unia wszystkich serii
        all_dates = sorted(
            set(vix_data.keys()) | set(treasury_data.keys()) | set(dxy_data.keys())
        )

        result: Dict[date, Dict[str, float]] = {}
        for d in all_dates:
            vix = vix_data.get(d)
            if vix is None:
                continue  # VIX jako główna seria — tylko dni gdy mamy VIX
            result[d] = {
                "vix":          vix,
                "treasury_10y": treasury_data.get(d, 0.0),
                "dxy":          dxy_data.get(d, 0.0),
            }

        _macro_cache = result
        _macro_fetched_at = time.time()
        print(f"[macro] dane makro załadowane: {len(result)} dni")
        return result
    except Exception:
        return {}


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
    macro_data: Optional[Dict[date, Dict[str, float]]] = None,
    sector_closes: Optional[List[float]] = None,
) -> Dict[str, float]:
    """
    Liczy wszystkie wskaźniki techniczne dla danego punktu czasowego.
    Przyjmuje ceny/wolumeny POSORTOWANE rosnąco (od najstarszej do snap_date włącznie).

    macro_data    — słownik {date: {vix, treasury_10y, dxy}} z fetch_macro_data()
    sector_closes — lista cen zamknięcia ETF sektora (SOXX/QQQ), posortowana rosnąco
    """
    spy_ret = spy_returns.get(snap_date, None)

    alpha = None
    if asset_return_5d is not None and spy_ret is not None:
        alpha = asset_return_5d - spy_ret

    # ── Makro ─────────────────────────────────────────────────────────────────
    macro = macro_data.get(snap_date) if macro_data else None

    vix_level    = macro["vix"]          if macro else 20.0   # neutralna wartość
    treasury_10y = macro["treasury_10y"] if macro else 0.0
    dxy_return   = 0.0
    vix_change   = 0.0

    if macro_data and len(macro_data) >= 6:
        # VIX change 5d: porównaj z wartością ~5 dni temu
        sorted_macro_dates = sorted(macro_data.keys())
        idx = sorted_macro_dates.index(snap_date) if snap_date in sorted_macro_dates else -1
        if idx >= 5:
            prev = macro_data[sorted_macro_dates[idx - 5]]
            if prev["vix"] and prev["vix"] != 0:
                vix_change = (vix_level - prev["vix"]) / prev["vix"] * 100

            # DXY 5d return
            curr_dxy = macro["dxy"] if macro else 0.0
            prev_dxy = prev["dxy"]
            if prev_dxy and prev_dxy != 0 and curr_dxy:
                dxy_return = (curr_dxy - prev_dxy) / prev_dxy * 100

    # ── Siła sektora ──────────────────────────────────────────────────────────
    sector_return_5d = 0.0
    sector_vs_spy    = 0.0
    if sector_closes and len(sector_closes) >= 6:
        c_now  = sector_closes[-1]
        c_prev = sector_closes[-6]
        if c_prev and c_prev != 0:
            sector_return_5d = (c_now - c_prev) / c_prev * 100
            if spy_ret is not None:
                sector_vs_spy = sector_return_5d - spy_ret

    return {
        "rsi_14":             calc_rsi(closes),
        "macd_histogram":     calc_macd_histogram(closes),
        "bb_pct":             calc_bb_pct(closes),
        "volume_ratio_20d":   calc_volume_ratio(volumes),
        "price_vs_52w_high":  calc_price_vs_52w_high(closes),
        "above_sma200":       calc_above_sma(closes),
        "spy_return_5d":      spy_ret if spy_ret is not None else 0.0,
        "alpha_vs_spy_5d":    alpha  if alpha  is not None else 0.0,
        # Makro
        "vix_level":          float(vix_level),
        "vix_change_5d":      float(vix_change),
        "treasury_10y":       float(treasury_10y),
        "dxy_return_5d":      float(dxy_return),
        # Siła sektora
        "sector_return_5d":   float(sector_return_5d),
        "sector_vs_spy_5d":   float(sector_vs_spy),
    }
