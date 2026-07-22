"""
intraday_service.py — swing trading: dane 15-min, wskazniki techniczne, sygnaly.

Fetchuje swiece z Finnhub /stock/candle co 15 min podczas sesji NYSE.
Oblicza RSI, MACD, EMA, Bollinger Bands, volume spike, support/resistance.
Generuje sygnaly BUY/SELL dla swing tradingu.
Zapisuje dane jako ML dataset (cechy intraday) dla przyszlego treningu.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import yfinance as yf
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.db.models import AssetORM, IntradayCandleORM
from app.utils.datetime import now_utc


# ── Wskazniki techniczne ──────────────────────────────────────────────────────

def _ema(values: list[float], period: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return result
    k = 2.0 / (period + 1)
    sma = sum(values[:period]) / period
    result[period - 1] = sma
    for i in range(period, len(values)):
        result[i] = values[i] * k + result[i - 1] * (1 - k)
    return result


def _rsi(closes: list[float], period: int = 14) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return result
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    for i in range(period, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
        if avg_l == 0:
            result[i] = 100.0
        else:
            result[i] = 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return result


def _macd(closes: list[float], fast=12, slow=26, signal=9) -> tuple[list[Optional[float]], list[Optional[float]]]:
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line: list[Optional[float]] = []
    for f, s in zip(ema_fast, ema_slow):
        macd_line.append(f - s if f is not None and s is not None else None)
    non_none = [v for v in macd_line if v is not None]
    sig_raw = _ema(non_none, signal)
    sig_full: list[Optional[float]] = []
    idx = 0
    for v in macd_line:
        if v is None:
            sig_full.append(None)
        else:
            sig_full.append(sig_raw[idx])
            idx += 1
    return macd_line, sig_full


def _bollinger(closes: list[float], period=20, std_mult=2.0) -> tuple[list[Optional[float]], list[Optional[float]]]:
    upper: list[Optional[float]] = [None] * len(closes)
    lower: list[Optional[float]] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(variance)
        upper[i] = mean + std_mult * std
        lower[i] = mean - std_mult * std
    return upper, lower


def _volume_ratio(volumes: list[float], period=20) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(volumes)
    for i in range(period - 1, len(volumes)):
        avg = sum(volumes[i - period + 1 : i + 1]) / period
        result[i] = volumes[i] / avg if avg > 0 else None
    return result


# ── ADX ──────────────────────────────────────────────────────────────────────

def _adx(
    candles: list[IntradayCandleORM],
    period: int = 14,
) -> tuple[list[Optional[float]], list[Optional[float]], list[Optional[float]]]:
    """Wilder's ADX, +DI, -DI. Zwraca (adx, di_plus, di_minus) — listy dlugosci len(candles)."""
    n = len(candles)
    adx_out: list[Optional[float]] = [None] * n
    dip_out: list[Optional[float]] = [None] * n
    dim_out: list[Optional[float]] = [None] * n

    if n < period * 2 + 1:
        return adx_out, dip_out, dim_out

    trs: list[float] = []
    dm_ps: list[float] = []
    dm_ms: list[float] = []

    for i in range(1, n):
        h, l = candles[i].high, candles[i].low
        pc, ph, pl = candles[i - 1].close, candles[i - 1].high, candles[i - 1].low
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up, dn = h - ph, pl - l
        dm_ps.append(up if up > dn and up > 0 else 0.0)
        dm_ms.append(dn if dn > up and dn > 0 else 0.0)
        trs.append(tr)

    # Wilder initial sums (first `period` values)
    atr = sum(trs[:period])
    s_dp = sum(dm_ps[:period])
    s_dm = sum(dm_ms[:period])

    def _di_dx(atr_v: float, sdp: float, sdm: float) -> tuple[float, float, float]:
        dip = 100.0 * sdp / atr_v if atr_v > 0 else 0.0
        dim = 100.0 * sdm / atr_v if atr_v > 0 else 0.0
        den = dip + dim
        dx = 100.0 * abs(dip - dim) / den if den > 0 else 0.0
        return dip, dim, dx

    # First DI at candles[period] (trs[period-1] → candles[period])
    dip_v, dim_v, dx = _di_dx(atr, s_dp, s_dm)
    dip_out[period] = dip_v
    dim_out[period] = dim_v
    dx_vals: list[float] = [dx]

    for k in range(period, len(trs)):
        ci = k + 1  # candles index
        atr = atr - atr / period + trs[k]
        s_dp = s_dp - s_dp / period + dm_ps[k]
        s_dm = s_dm - s_dm / period + dm_ms[k]
        dip_v, dim_v, dx = _di_dx(atr, s_dp, s_dm)
        if ci < n:
            dip_out[ci] = dip_v
            dim_out[ci] = dim_v
        dx_vals.append(dx)

    # ADX = Wilder smoothing of DX over `period` bars
    if len(dx_vals) < period:
        return adx_out, dip_out, dim_out

    adx_val = sum(dx_vals[:period]) / period
    adx_start = period + period - 1  # candles index of first ADX
    if adx_start < n:
        adx_out[adx_start] = adx_val

    for k in range(period, len(dx_vals)):
        ci = period + k
        adx_val = (adx_val * (period - 1) + dx_vals[k]) / period
        if ci < n:
            adx_out[ci] = adx_val

    return adx_out, dip_out, dim_out


# ── Market Regime ──────────────────────────────────────────────────────────────

def detect_market_regime(candles: list[IntradayCandleORM]) -> dict:
    """Klasyfikuje reżim: trend_up | trend_down | range | volatile.
    ADX > 25 → trend; ADX < 20 + BB squeeze → range; inaczej volatile."""
    if len(candles) < 30:
        return {"regime": "unknown", "adx": None, "di_plus": None, "di_minus": None, "bb_squeeze": False, "description": "Za mało danych"}

    last = candles[-1]
    adx = last.adx
    di_plus = last.di_plus
    di_minus = last.di_minus
    bb_upper = last.bb_upper
    bb_lower = last.bb_lower
    close = last.close

    bb_squeeze = False
    if bb_upper is not None and bb_lower is not None and close > 0:
        bb_width_pct = (bb_upper - bb_lower) / close * 100
        bb_squeeze = bb_width_pct < 2.0

    if adx is None:
        regime = "range"
        desc = "Brak danych ADX"
    elif adx > 25:
        if di_plus is not None and di_minus is not None and di_plus > di_minus:
            regime = "trend_up"
            desc = f"Silny trend wzrostowy (ADX={adx:.0f}, +DI={di_plus:.0f} > -DI={di_minus:.0f})"
        elif di_plus is not None and di_minus is not None and di_minus > di_plus:
            regime = "trend_down"
            desc = f"Silny trend spadkowy (ADX={adx:.0f}, -DI={di_minus:.0f} > +DI={di_plus:.0f})"
        else:
            regime = "volatile"
            desc = f"Silny ruch, kierunek nieokreślony (ADX={adx:.0f})"
    elif adx > 20:
        regime = "range"
        sq = " + BB squeeze" if bb_squeeze else ""
        desc = f"Słaby trend / konsolidacja (ADX={adx:.0f}{sq})"
    else:
        if bb_squeeze:
            regime = "range"
            desc = f"Konsolidacja + BB squeeze (ADX={adx:.0f}) — możliwy wybuch zmienności"
        else:
            regime = "volatile"
            desc = f"Brak trendu, rynek chaotyczny (ADX={adx:.0f})"

    return {
        "regime": regime,
        "adx": round(adx, 1) if adx is not None else None,
        "di_plus": round(di_plus, 1) if di_plus is not None else None,
        "di_minus": round(di_minus, 1) if di_minus is not None else None,
        "bb_squeeze": bb_squeeze,
        "description": desc,
    }


# ── VWAP ─────────────────────────────────────────────────────────────────────

def _vwap(candles: list[IntradayCandleORM]) -> list[Optional[float]]:
    """VWAP resetuje sie na poczatku kazdego dnia sesyjnego."""
    result: list[Optional[float]] = [None] * len(candles)
    current_day = None
    cum_tp_vol = 0.0
    cum_vol = 0.0
    for i, c in enumerate(candles):
        day = c.timestamp.date()
        if day != current_day:
            current_day = day
            cum_tp_vol = 0.0
            cum_vol = 0.0
        tp = (c.high + c.low + c.close) / 3.0
        cum_tp_vol += tp * c.volume
        cum_vol += c.volume
        result[i] = cum_tp_vol / cum_vol if cum_vol > 0 else None
    return result


# ── Opening Range ─────────────────────────────────────────────────────────────

def detect_opening_range(
    candles: list[IntradayCandleORM],
    resolution: str = "15",
) -> dict:
    """Opening Range = pierwsze 30 minut sesji biezacego dnia.
    Zwraca {high, low, breakout_up, breakout_down} lub pusty dict."""
    if not candles:
        return {}
    # ile swiec to 30 min?
    candles_per_30min = max(1, 30 // int(resolution)) if resolution.isdigit() else 1
    today = datetime.now(timezone.utc).date()
    today_candles = [c for c in candles if c.timestamp.date() == today]
    if len(today_candles) < candles_per_30min:
        return {}
    or_candles = today_candles[:candles_per_30min]
    or_high = max(c.high for c in or_candles)
    or_low = min(c.low for c in or_candles)
    last_close = candles[-1].close
    return {
        "high": or_high,
        "low": or_low,
        "breakout_up": last_close > or_high,
        "breakout_down": last_close < or_low,
        "range_pct": round((or_high - or_low) / or_low * 100, 2) if or_low > 0 else 0,
    }


# ── Support / Resistance ──────────────────────────────────────────────────────

def detect_support_resistance(
    candles: list[IntradayCandleORM],
    window: int = 5,
    min_touches: int = 2,
    tolerance_pct: float = 0.004,
) -> dict[str, list[float]]:
    """Zwraca lokalne minima (support) i maksima (resistance) z historii swiec."""
    if len(candles) < window * 2 + 1:
        return {"support": [], "resistance": []}

    highs = [c.high for c in candles]
    lows = [c.low for c in candles]

    raw_res: list[float] = []
    raw_sup: list[float] = []

    for i in range(window, len(candles) - window):
        if highs[i] == max(highs[i - window : i + window + 1]):
            raw_res.append(highs[i])
        if lows[i] == min(lows[i - window : i + window + 1]):
            raw_sup.append(lows[i])

    def cluster(levels: list[float]) -> list[float]:
        if not levels:
            return []
        levels_sorted = sorted(levels)
        clusters: list[list[float]] = [[levels_sorted[0]]]
        for lv in levels_sorted[1:]:
            if abs(lv - clusters[-1][-1]) / clusters[-1][-1] <= tolerance_pct:
                clusters[-1].append(lv)
            else:
                clusters.append([lv])
        return [
            sum(c) / len(c)
            for c in clusters
            if len(c) >= min_touches
        ]

    return {
        "support": cluster(raw_sup)[-5:],      # ostatnie 5 poziomow support
        "resistance": cluster(raw_res)[-5:],    # ostatnie 5 poziomow resistance
    }


# ── Formacje świecowe ────────────────────────────────────────────────────────

def detect_candlestick_patterns(
    candles: list[IntradayCandleORM],
    lookback: int = 20,
) -> list[dict]:
    """Wykrywa formacje świecowe w ostatnich 'lookback' świecach."""
    if len(candles) < 3:
        return []

    recent = candles[-lookback:]
    patterns: list[dict] = []

    def _body(c: IntradayCandleORM) -> float:
        return abs(c.close - c.open)

    def _range(c: IntradayCandleORM) -> float:
        return c.high - c.low

    def _upper_wick(c: IntradayCandleORM) -> float:
        return c.high - max(c.close, c.open)

    def _lower_wick(c: IntradayCandleORM) -> float:
        return min(c.close, c.open) - c.low

    def _is_bull(c: IntradayCandleORM) -> bool:
        return c.close > c.open

    def _is_bear(c: IntradayCandleORM) -> bool:
        return c.close < c.open

    def _add(name: str, kind: str, desc: str, c: IntradayCandleORM, strength: int) -> None:
        patterns.append({
            "name": name,
            "type": kind,           # "bullish" | "bearish" | "neutral"
            "timestamp": c.timestamp.isoformat(),
            "price": c.close,
            "description": desc,
            "strength": strength,
        })

    for i, c in enumerate(recent):
        rng = _range(c)
        if rng < 1e-9:
            continue
        body = _body(c)
        uw = _upper_wick(c)
        lw = _lower_wick(c)
        body_pct = body / rng

        prev1 = recent[i - 1] if i >= 1 else None
        prev2 = recent[i - 2] if i >= 2 else None

        # ── 1-świecowe ────────────────────────────────────────────────────────

        # Doji
        if body_pct < 0.08 and rng > 0:
            _add("Doji", "neutral",
                 "Niezdecydowanie — byki i niedźwiedzie w równowadze, czekaj na potwierdzenie", c, 45)

        # Hammer (bullish reversal at low)
        if lw >= body * 2.0 and uw <= body * 0.5 and body_pct > 0.05:
            if i >= 2 and c.low <= min(r.low for r in recent[max(0, i-3):i]):
                kind = "bullish" if _is_bull(c) else "bullish"
                _add("Hammer", "bullish",
                     "Odrzucenie od dołu — potencjalne odwrócenie w górę", c, 65)

        # Inverted Hammer (bullish, at low)
        if uw >= body * 2.0 and lw <= body * 0.5 and body_pct > 0.05:
            if i >= 2 and c.low <= min(r.low for r in recent[max(0, i-3):i]):
                _add("Inverted Hammer", "bullish",
                     "Próba wzrostu od dołu — wymaga potwierdzenia następną świecą", c, 55)

        # Hanging Man (bearish, at high)
        if lw >= body * 2.0 and uw <= body * 0.5 and body_pct > 0.05:
            if i >= 2 and c.high >= max(r.high for r in recent[max(0, i-3):i]):
                _add("Hanging Man", "bearish",
                     "Odrzucenie od góry — potencjalne odwrócenie w dół", c, 60)

        # Shooting Star (bearish, at high)
        if uw >= body * 2.0 and lw <= body * 0.5 and body_pct > 0.05:
            if i >= 2 and c.high >= max(r.high for r in recent[max(0, i-3):i]):
                _add("Shooting Star", "bearish",
                     "Próba wzrostu odrzucona — niedźwiedzie przejęły kontrolę", c, 70)

        # Marubozu bullish (silna świeca bez knotów)
        if _is_bull(c) and body_pct > 0.85:
            _add("Bullish Marubozu", "bullish",
                 "Byki w pełnej kontroli przez cały interwał", c, 75)

        # Marubozu bearish
        if _is_bear(c) and body_pct > 0.85:
            _add("Bearish Marubozu", "bearish",
                 "Niedźwiedzie w pełnej kontroli przez cały interwał", c, 75)

        # ── 2-świecowe ────────────────────────────────────────────────────────

        if prev1 is not None:
            pb = _body(prev1)
            prng = _range(prev1)

            # Bullish Engulfing
            if (_is_bear(prev1) and _is_bull(c)
                    and c.open <= prev1.close and c.close >= prev1.open
                    and body > pb):
                _add("Bullish Engulfing", "bullish",
                     "Byki pochłonęły poprzednią świecę — silny sygnał odwrócenia", c, 80)

            # Bearish Engulfing
            if (_is_bull(prev1) and _is_bear(c)
                    and c.open >= prev1.close and c.close <= prev1.open
                    and body > pb):
                _add("Bearish Engulfing", "bearish",
                     "Niedźwiedzie pochłonęły poprzednią świecę — silny sygnał odwrócenia", c, 80)

            # Bullish Harami
            if (_is_bear(prev1) and _is_bull(c) and pb > 0
                    and c.open > prev1.close and c.close < prev1.open
                    and body < pb * 0.5):
                _add("Bullish Harami", "bullish",
                     "Mała bycza świeca wewnątrz niedźwiedziej — osłabienie sprzedaży", c, 60)

            # Bearish Harami
            if (_is_bull(prev1) and _is_bear(c) and pb > 0
                    and c.open < prev1.close and c.close > prev1.open
                    and body < pb * 0.5):
                _add("Bearish Harami", "bearish",
                     "Mała niedźwiedzia świeca wewnątrz byczej — osłabienie kupna", c, 60)

            # Tweezer Bottom
            if (abs(c.low - prev1.low) / max(c.low, 1e-9) < 0.002
                    and _is_bull(c) and _is_bear(prev1)):
                _add("Tweezer Bottom", "bullish",
                     "Identyczne dno dwie świece z rzędu — silny support", c, 70)

            # Tweezer Top
            if (abs(c.high - prev1.high) / max(c.high, 1e-9) < 0.002
                    and _is_bear(c) and _is_bull(prev1)):
                _add("Tweezer Top", "bearish",
                     "Identyczny szczyt dwie świece z rzędu — silna resistance", c, 70)

        # ── 3-świecowe ────────────────────────────────────────────────────────

        if prev1 is not None and prev2 is not None:
            b0, b1, b2 = _body(prev2), _body(prev1), body
            r0 = _range(prev2)

            # Morning Star
            if (_is_bear(prev2) and b0 > r0 * 0.4
                    and b1 < b0 * 0.4
                    and _is_bull(c) and b2 > b0 * 0.5
                    and c.close > (prev2.open + prev2.close) / 2):
                _add("Morning Star", "bullish",
                     "Formacja 3-świecowa: silne odwrócenie trendu spadkowego", c, 85)

            # Evening Star
            if (_is_bull(prev2) and b0 > r0 * 0.4
                    and b1 < b0 * 0.4
                    and _is_bear(c) and b2 > b0 * 0.5
                    and c.close < (prev2.open + prev2.close) / 2):
                _add("Evening Star", "bearish",
                     "Formacja 3-świecowa: silne odwrócenie trendu wzrostowego", c, 85)

            # Three White Soldiers
            if (all(_is_bull(x) for x in [prev2, prev1, c])
                    and prev1.open > prev2.open and prev1.close > prev2.close
                    and c.open > prev1.open and c.close > prev1.close
                    and all(_body(x) > _range(x) * 0.6 for x in [prev2, prev1, c])):
                _add("Three White Soldiers", "bullish",
                     "Trzy mocne bycze świece — trend wzrostowy nabiera siły", c, 80)

            # Three Black Crows
            if (all(_is_bear(x) for x in [prev2, prev1, c])
                    and prev1.open < prev2.open and prev1.close < prev2.close
                    and c.open < prev1.open and c.close < prev1.close
                    and all(_body(x) > _range(x) * 0.6 for x in [prev2, prev1, c])):
                _add("Three Black Crows", "bearish",
                     "Trzy mocne niedźwiedzie świece — trend spadkowy nabiera siły", c, 80)

    # Deduplikacja — zachowaj tylko ostatnią instancję każdej nazwy
    seen: set[str] = set()
    unique: list[dict] = []
    for p in reversed(patterns):
        if p["name"] not in seen:
            seen.add(p["name"])
            unique.append(p)
    return list(reversed(unique))


# ── Sygnaly swing ─────────────────────────────────────────────────────────────

def generate_swing_signals(
    candles: list[IntradayCandleORM],
    sr_levels: dict[str, list[float]],
    opening_range: dict | None = None,
    regime: dict | None = None,
) -> list[dict]:
    """Generuje sygnaly BUY/SELL z wagami dostosowanymi do reżimu rynkowego."""
    if not candles:
        return []

    signals = []
    last = candles[-1]
    prev = candles[-2] if len(candles) >= 2 else None

    rsi = last.rsi
    vol_ratio = last.volume_ratio
    close = last.close
    macd = last.macd
    macd_sig = last.macd_signal
    vwap = last.vwap

    supports = sr_levels.get("support", [])
    resistances = sr_levels.get("resistance", [])

    near_support = any(abs(close - s) / close < 0.015 for s in supports) if supports else False
    near_resistance = any(abs(close - r) / close < 0.015 for r in resistances) if resistances else False

    volume_spike = vol_ratio is not None and vol_ratio >= 1.8
    rsi_oversold = rsi is not None and rsi < 32
    rsi_overbought = rsi is not None and rsi > 68
    above_vwap = vwap is not None and close > vwap
    below_vwap = vwap is not None and close < vwap
    vwap_cross_up = (
        vwap is not None and prev is not None and prev.vwap is not None
        and close > vwap and prev.close <= prev.vwap
    )
    vwap_cross_down = (
        vwap is not None and prev is not None and prev.vwap is not None
        and close < vwap and prev.close >= prev.vwap
    )
    macd_bullish = (
        macd is not None and macd_sig is not None and macd > macd_sig
        and prev is not None and prev.macd is not None and prev.macd_signal is not None
        and prev.macd <= prev.macd_signal
    )
    macd_bearish = (
        macd is not None and macd_sig is not None and macd < macd_sig
        and prev is not None and prev.macd is not None and prev.macd_signal is not None
        and prev.macd >= prev.macd_signal
    )
    or_breakout_up = opening_range.get("breakout_up", False) if opening_range else False
    or_breakout_down = opening_range.get("breakout_down", False) if opening_range else False

    # ── BUY signal ──
    buy_reasons = []
    if rsi_oversold:
        buy_reasons.append(f"RSI={rsi:.0f} (wyprzedanie)")
    if near_support:
        lvl = min(supports, key=lambda s: abs(close - s))
        buy_reasons.append(f"cena przy support {lvl:.2f}")
    if macd_bullish:
        buy_reasons.append("MACD crossover bullish")
    if volume_spike and close > (prev.close if prev else close):
        buy_reasons.append(f"volume spike {vol_ratio:.1f}x")
    if vwap_cross_up:
        buy_reasons.append(f"przebicie VWAP {vwap:.2f} w górę")
    elif above_vwap and near_support:
        buy_reasons.append(f"cena nad VWAP {vwap:.2f}")
    if or_breakout_up and opening_range:
        buy_reasons.append(f"wybicie ORH {opening_range['high']:.2f}")

    regime_name = regime.get("regime", "unknown") if regime else "unknown"

    def _apply_regime(strength: int, signal_type: str) -> int:
        """Podnosi/obniża siłę sygnału zależnie od reżimu rynkowego."""
        if regime_name == "trend_up":
            return min(strength + 15, 95) if signal_type == "BUY" else max(strength - 15, 10)
        if regime_name == "trend_down":
            return min(strength + 15, 95) if signal_type == "SELL" else max(strength - 15, 10)
        if regime_name == "range":
            # RSI działa lepiej w konsolidacji
            if signal_type == "BUY" and rsi_oversold:
                return min(strength + 10, 95)
            if signal_type == "SELL" and rsi_overbought:
                return min(strength + 10, 95)
        return strength

    if len(buy_reasons) >= 2:
        strength = _apply_regime(min(len(buy_reasons) * 22, 92), "BUY")
        signals.append({
            "type": "BUY",
            "timestamp": last.timestamp.isoformat(),
            "price": close,
            "strength": strength,
            "reasons": buy_reasons,
            "rsi": rsi,
            "volume_ratio": vol_ratio,
            "vwap": vwap,
        })

    # ── SELL signal ──
    sell_reasons = []
    if rsi_overbought:
        sell_reasons.append(f"RSI={rsi:.0f} (wykupienie)")
    if near_resistance:
        lvl = min(resistances, key=lambda r: abs(close - r))
        sell_reasons.append(f"cena przy resistance {lvl:.2f}")
    if macd_bearish:
        sell_reasons.append("MACD crossover bearish")
    if volume_spike and close < (prev.close if prev else close):
        sell_reasons.append(f"volume spike {vol_ratio:.1f}x (sprzedaz)")
    if vwap_cross_down:
        sell_reasons.append(f"przebicie VWAP {vwap:.2f} w dół")
    elif below_vwap and near_resistance:
        sell_reasons.append(f"cena pod VWAP {vwap:.2f}")
    if or_breakout_down and opening_range:
        sell_reasons.append(f"wybicie ORL {opening_range['low']:.2f} w dół")

    if len(sell_reasons) >= 2:
        strength = _apply_regime(min(len(sell_reasons) * 22, 92), "SELL")
        signals.append({
            "type": "SELL",
            "timestamp": last.timestamp.isoformat(),
            "price": close,
            "strength": strength,
            "reasons": sell_reasons,
            "rsi": rsi,
            "volume_ratio": vol_ratio,
            "vwap": vwap,
        })

    return signals


# ── Yahoo Finance fetch ───────────────────────────────────────────────────────

_YF_RESOLUTION_MAP = {
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "60m",
    "D": "1d",
}


def fetch_intraday_candles_from_yfinance(
    symbol: str,
    resolution: str = "15",
    lookback_hours: int = 120,
) -> list[dict]:
    """Pobiera swiece intraday z Yahoo Finance. Zwraca liste dict {t,o,h,l,c,v}.
    Yahoo Finance przechowuje dane intraday do 60 dni (interwaly < 1h do 7 dni)."""
    interval = _YF_RESOLUTION_MAP.get(resolution, "15m")
    # Yahoo Finance: dane minutowe/godzinowe dostepne przez period "5d" lub "7d"
    days = max(1, min(lookback_hours // 24 + 1, 7 if interval != "1d" else 60))
    period = f"{days}d"
    print(f"[intraday] Fetchuje {symbol} interval={interval} period={period} (lookback={lookback_hours}h)")
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
    except Exception as exc:
        print(f"[intraday] Blad yfinance {symbol}: {exc}")
        return []

    if df is None or df.empty:
        print(f"[intraday] yfinance {symbol} interval={interval}: brak danych")
        return []

    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    now_dt = datetime.now(timezone.utc)
    interval_minutes = int(resolution) if resolution.isdigit() else None
    result = []
    for ts_idx, row in df.iterrows():
        # yfinance zwraca indeks jako Timestamp (moze byc timezone-aware lub naive)
        if hasattr(ts_idx, "tzinfo") and ts_idx.tzinfo is not None:
            ts_utc = ts_idx.to_pydatetime().astimezone(timezone.utc)
        else:
            ts_utc = ts_idx.to_pydatetime().replace(tzinfo=timezone.utc)
        if ts_utc < cutoff_dt:
            continue
        # Yahoo zwraca również aktualnie budowaną świecę. Sygnały wolno liczyć
        # dopiero po końcu interwału (z minutą bufora na finalizację danych).
        if interval_minutes is not None and ts_utc + timedelta(minutes=interval_minutes, seconds=60) > now_dt:
            continue
        if resolution == "D" and ts_utc.date() >= now_dt.date():
            continue
        result.append({
            "t": int(ts_utc.timestamp()),
            "o": float(row["Open"]),
            "h": float(row["High"]),
            "l": float(row["Low"]),
            "c": float(row["Close"]),
            "v": float(row.get("Volume", 0) or 0),
        })

    print(f"[intraday] yfinance {symbol} interval={interval}: {len(result)} swiec w oknie {lookback_hours}h")
    return result


# ── Zapis do DB + obliczanie wskaznikow ───────────────────────────────────────

def sync_intraday_candles(
    db: Session,
    asset: AssetORM,
    resolution: str = "15",
    lookback_hours: int = 120,
) -> dict:
    """Pobiera swiece z Finnhub i zapisuje do DB z obliczonymi wskaznikami.
    Zwraca dict: {new_candles, fetched_from_api, already_in_db}."""
    if asset.type != "stock":
        return {"new_candles": 0, "fetched_from_api": 0, "already_in_db": 0}
    fh_sym = (asset.price_symbol or asset.symbol or "").upper()
    if not fh_sym:
        return {"new_candles": 0, "fetched_from_api": 0, "already_in_db": 0}

    raw = fetch_intraday_candles_from_yfinance(fh_sym, resolution, lookback_hours)

    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=lookback_hours + 1)
    cutoff_naive = cutoff_dt.replace(tzinfo=None)
    existing_ts = set(
        db.scalars(
            select(IntradayCandleORM.timestamp)
            .where(
                IntradayCandleORM.asset_id == asset.id,
                IntradayCandleORM.resolution == resolution,
                IntradayCandleORM.timestamp >= cutoff_naive,
            )
        ).all()
    )
    # Normalize to naive UTC for comparison (SQLite returns naive datetimes)
    existing_ts_naive = {
        dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
        for dt in existing_ts
    }

    if not raw:
        return {"new_candles": 0, "fetched_from_api": 0, "already_in_db": len(existing_ts_naive)}

    new_rows: list[IntradayCandleORM] = []
    from app.services.ohlcv_validation import validate_bar
    for bar in raw:
        ts = datetime.fromtimestamp(bar["t"], tz=timezone.utc)
        ts_naive = ts.replace(tzinfo=None)
        if ts_naive in existing_ts_naive:
            continue
        candidate = IntradayCandleORM(
            asset_id=asset.id,
            resolution=resolution,
            timestamp=ts_naive,
            open=bar["o"],
            high=bar["h"],
            low=bar["l"],
            close=bar["c"],
            volume=bar["v"],
        )
        if any(issue.severity == "critical" for issue in validate_bar(candidate)):
            continue
        new_rows.append(candidate)

    if not new_rows:
        return {"new_candles": 0, "fetched_from_api": len(raw), "already_in_db": len(existing_ts_naive)}

    for row in new_rows:
        db.add(row)
    db.flush()

    _compute_and_update_indicators(db, asset.id, resolution)
    db.commit()
    return {"new_candles": len(new_rows), "fetched_from_api": len(raw), "already_in_db": len(existing_ts_naive)}


def _compute_and_update_indicators(db: Session, asset_id: str, resolution: str) -> None:
    """Oblicza wskazniki techniczne dla ostatnich 300 swiec i aktualizuje DB."""
    candles = db.scalars(
        select(IntradayCandleORM)
        .where(
            IntradayCandleORM.asset_id == asset_id,
            IntradayCandleORM.resolution == resolution,
        )
        .order_by(IntradayCandleORM.timestamp.desc())
        .limit(300)
    ).all()[::-1]

    if len(candles) < 2:
        return

    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]

    rsi_vals = _rsi(closes, 14)
    ema9_vals = _ema(closes, 9)
    ema20_vals = _ema(closes, 20)
    macd_vals, macd_sig_vals = _macd(closes)
    bb_up, bb_dn = _bollinger(closes, 20)
    vol_ratio_vals = _volume_ratio(volumes, 20)

    vwap_vals = _vwap(candles)
    adx_vals, dip_vals, dim_vals = _adx(candles, period=14)

    for i, candle in enumerate(candles):
        candle.rsi = rsi_vals[i]
        candle.ema9 = ema9_vals[i]
        candle.ema20 = ema20_vals[i]
        candle.macd = macd_vals[i]
        candle.macd_signal = macd_sig_vals[i]
        candle.bb_upper = bb_up[i]
        candle.bb_lower = bb_dn[i]
        candle.volume_ratio = vol_ratio_vals[i]
        candle.vwap = vwap_vals[i]
        candle.adx = adx_vals[i]
        candle.di_plus = dip_vals[i]
        candle.di_minus = dim_vals[i]


# ── Volume Profile (VPVR) ────────────────────────────────────────────────────

def compute_volume_profile(
    candles: list[IntradayCandleORM],
    num_bins: int = 60,
) -> dict:
    """Oblicza Volume Profile dla zadanego zbioru swiec.
    Zwraca POC, VAH, VAL oraz bins [{price, volume}] posortowane od dolu."""
    if len(candles) < 5:
        return {}

    price_low = min(c.low for c in candles)
    price_high = max(c.high for c in candles)
    if price_high <= price_low:
        return {}

    bin_size = (price_high - price_low) / num_bins
    bins = [0.0] * num_bins

    for c in candles:
        candle_range = c.high - c.low
        if candle_range < 1e-9:
            idx = min(int((c.close - price_low) / bin_size), num_bins - 1)
            bins[idx] += c.volume
            continue
        for i in range(num_bins):
            bin_lo = price_low + i * bin_size
            bin_hi = bin_lo + bin_size
            overlap = min(c.high, bin_hi) - max(c.low, bin_lo)
            if overlap > 0:
                bins[i] += c.volume * overlap / candle_range

    total_vol = sum(bins)
    if total_vol == 0:
        return {}

    # POC = bin z max wolumenem
    poc_idx = max(range(num_bins), key=lambda i: bins[i])
    poc_price = price_low + (poc_idx + 0.5) * bin_size

    # Value Area = 70% wolumenu wokol POC
    target = total_vol * 0.70
    va_lo = poc_idx
    va_hi = poc_idx
    va_vol = bins[poc_idx]
    while va_vol < target:
        can_down = va_lo > 0
        can_up = va_hi < num_bins - 1
        if not can_down and not can_up:
            break
        vol_down = bins[va_lo - 1] if can_down else -1
        vol_up = bins[va_hi + 1] if can_up else -1
        if vol_down >= vol_up:
            va_lo -= 1
            va_vol += bins[va_lo]
        else:
            va_hi += 1
            va_vol += bins[va_hi]

    vah = price_low + (va_hi + 1) * bin_size
    val = price_low + va_lo * bin_size
    max_vol = max(bins)

    return {
        "poc": round(poc_price, 4),
        "vah": round(vah, 4),
        "val": round(val, 4),
        "price_low": round(price_low, 4),
        "price_high": round(price_high, 4),
        "total_volume": round(total_vol, 2),
        "bins": [
            {
                "price": round(price_low + (i + 0.5) * bin_size, 4),
                "volume": round(bins[i], 2),
                "pct": round(bins[i] / max_vol * 100, 1) if max_vol > 0 else 0,
                "is_poc": i == poc_idx,
                "in_va": va_lo <= i <= va_hi,
            }
            for i in range(num_bins)
        ],
    }


def get_volume_profile(
    db: Session,
    asset_id: str,
    resolution: str = "15",
    limit: int = 300,
) -> dict:
    candles = get_candles(db, asset_id, resolution, limit=limit)
    return compute_volume_profile(candles)


# ── Pobieranie danych dla API ─────────────────────────────────────────────────

def get_relative_strength_intraday(
    db: Session,
    asset_id: str,
    resolution: str = "15",
    benchmark_id: str = "qqq",
) -> dict:
    """Oblicza sile wzgledna aktywa vs benchmark (QQQ) w ciagu sesji.
    RS = skumulowany zwrot aktywa - skumulowany zwrot benchmarku od otwarcia dnia.
    Zwraca: {data: [{timestamp, rs, asset_ret, bench_ret}], benchmark, current_rs}"""
    asset_candles = get_candles(db, asset_id, resolution, limit=200)
    bench_candles = get_candles(db, benchmark_id, resolution, limit=200)

    if len(asset_candles) < 3 or len(bench_candles) < 3:
        return {"data": [], "benchmark": benchmark_id, "current_rs": None}

    # Ostatni dzien handlowy dla ktorego mamy dane w obu seriach
    asset_days = sorted({c.timestamp.date() for c in asset_candles}, reverse=True)
    bench_days = sorted({c.timestamp.date() for c in bench_candles}, reverse=True)
    common_days = [d for d in asset_days if d in set(bench_days)]
    if not common_days:
        return {"data": [], "benchmark": benchmark_id, "current_rs": None}

    ref_day = common_days[0]
    asset_day = [c for c in asset_candles if c.timestamp.date() == ref_day]
    bench_day = [c for c in bench_candles if c.timestamp.date() == ref_day]
    if not asset_day or not bench_day:
        return {"data": [], "benchmark": benchmark_id, "current_rs": None}

    asset_open = asset_day[0].open
    bench_open = bench_day[0].open
    if asset_open == 0 or bench_open == 0:
        return {"data": [], "benchmark": benchmark_id, "current_rs": None}

    # Mapa timestamp -> close dla benchmarku
    bench_map: dict[datetime, float] = {c.timestamp: c.close for c in bench_day}

    result = []
    for c in asset_day:
        # Znajdz najblizszy timestamp benchmarku
        bench_close = bench_map.get(c.timestamp)
        if bench_close is None:
            nearest = min(bench_day, key=lambda b: abs((b.timestamp - c.timestamp).total_seconds()))
            bench_close = nearest.close
            nearest_open = bench_day[0].open
        else:
            nearest_open = bench_open

        asset_ret = (c.close - asset_open) / asset_open * 100
        bench_ret = (bench_close - nearest_open) / nearest_open * 100
        rs = round(asset_ret - bench_ret, 3)
        result.append({
            "timestamp": c.timestamp.isoformat(),
            "rs": rs,
            "asset_ret": round(asset_ret, 3),
            "bench_ret": round(bench_ret, 3),
        })

    current_rs = result[-1]["rs"] if result else None
    return {"data": result, "benchmark": benchmark_id, "current_rs": current_rs}


def get_candles(
    db: Session,
    asset_id: str,
    resolution: str = "15",
    limit: int = 200,
) -> list[IntradayCandleORM]:
    return db.scalars(
        select(IntradayCandleORM)
        .where(
            IntradayCandleORM.asset_id == asset_id,
            IntradayCandleORM.resolution == resolution,
        )
        .order_by(IntradayCandleORM.timestamp.desc())
        .limit(limit)
    ).all()[::-1]  # zwroc rosnaco


def get_latest_signals(
    db: Session,
    asset_id: str,
    resolution: str = "15",
) -> dict:
    candles = get_candles(db, asset_id, resolution, limit=100)
    if len(candles) < 30:
        return {"signals": [], "patterns": [], "support": [], "resistance": [], "candles_count": len(candles), "opening_range": {}, "current_vwap": None, "regime": {"regime": "unknown", "adx": None, "di_plus": None, "di_minus": None, "bb_squeeze": False, "description": "Za mało danych"}}
    sr = detect_support_resistance(candles)
    or_range = detect_opening_range(candles, resolution)
    regime = detect_market_regime(candles)
    signals = generate_swing_signals(candles, sr, or_range, regime)
    patterns = detect_candlestick_patterns(candles, lookback=20)
    last_vwap = candles[-1].vwap if candles else None
    return {
        "signals": signals,
        "patterns": patterns,
        "support": sr["support"],
        "resistance": sr["resistance"],
        "candles_count": len(candles),
        "opening_range": or_range,
        "current_vwap": last_vwap,
        "regime": regime,
    }


# ── Sync wszystkich aktywow ───────────────────────────────────────────────────

def sync_all_intraday(db: Session, resolutions: list[str] = ["15", "60"]) -> dict[str, int]:
    from app.services.market_calendar import is_market_open
    assets = db.scalars(
        select(AssetORM).where(AssetORM.type == "stock")
    ).all()
    results: dict[str, int] = {}
    for i, asset in enumerate(assets):
        symbol = asset.price_symbol or asset.symbol or ""
        if not is_market_open(symbol):
            continue
        if i > 0:
            time.sleep(0.6)  # Finnhub rate limit
        total = 0
        for res in resolutions:
            try:
                r = sync_intraday_candles(db, asset, resolution=res, lookback_hours=120)
                total += r["new_candles"]
            except Exception as exc:
                print(f"[intraday] Blad sync {asset.id}/{res}: {exc}")
        if total:
            results[asset.id] = total
    return results
