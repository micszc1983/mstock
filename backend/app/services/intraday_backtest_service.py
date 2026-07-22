from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.db.models import IntradayCandleORM, IntradayBacktestORM

# ── Signal detection ─────────────────────────────────────────────────────────

def _detect_signal(
    candles: list,
    idx: int,
    rsi_oversold: float,
    rsi_overbought: float,
    vol_threshold: float = 1.5,
) -> tuple[Optional[str], float]:
    """Returns (signal_type, strength) at candles[idx]. signal_type: 'BUY'|'SELL'|None."""
    if idx < 2:
        return None, 0.0
    c = candles[idx]
    p = candles[idx - 1]
    if c.rsi is None:
        return None, 0.0

    # ── BUY ──────────────────────────────────────────────────────────────────
    buy_reasons = 0
    if c.rsi < rsi_oversold:
        buy_reasons += 1
    if (c.macd is not None and c.macd_signal is not None
            and p.macd is not None and p.macd_signal is not None
            and p.macd <= p.macd_signal and c.macd > c.macd_signal):
        buy_reasons += 1
    if (c.vwap is not None and p.vwap is not None
            and p.close < p.vwap and c.close > c.vwap):
        buy_reasons += 1
    if c.volume_ratio is not None and c.volume_ratio >= vol_threshold:
        buy_reasons += 1
    if (c.ema9 is not None and c.ema20 is not None
            and p.ema9 is not None and p.ema20 is not None
            and p.ema9 <= p.ema20 and c.ema9 > c.ema20):
        buy_reasons += 1

    if c.rsi < rsi_oversold and buy_reasons >= 2:
        return "BUY", min(buy_reasons * 0.22, 0.92)

    # ── SELL ─────────────────────────────────────────────────────────────────
    sell_reasons = 0
    if c.rsi > rsi_overbought:
        sell_reasons += 1
    if (c.macd is not None and c.macd_signal is not None
            and p.macd is not None and p.macd_signal is not None
            and p.macd >= p.macd_signal and c.macd < c.macd_signal):
        sell_reasons += 1
    if (c.vwap is not None and p.vwap is not None
            and p.close > p.vwap and c.close < c.vwap):
        sell_reasons += 1
    if c.volume_ratio is not None and c.volume_ratio >= vol_threshold:
        sell_reasons += 1
    if (c.ema9 is not None and c.ema20 is not None
            and p.ema9 is not None and p.ema20 is not None
            and p.ema9 >= p.ema20 and c.ema9 < c.ema20):
        sell_reasons += 1

    if c.rsi > rsi_overbought and sell_reasons >= 2:
        return "SELL", min(sell_reasons * 0.22, 0.92)

    return None, 0.0


# ── Trade simulation ──────────────────────────────────────────────────────────

def _simulate_trades(
    candles: list,
    rsi_oversold: float,
    rsi_overbought: float,
    sl_pct: float,
    tp_pct: float,
    max_hold_bars: int = 12,
    round_trip_cost_pct: float = 0.10,
) -> list[dict]:
    trades: list[dict] = []
    in_trade = False
    entry_idx = 0
    entry_price = 0.0
    direction = ""

    for i in range(2, len(candles)):
        c = candles[i]

        if in_trade:
            bars_held = i - entry_idx
            if direction == "BUY":
                tp_price = entry_price * (1 + tp_pct / 100)
                sl_price = entry_price * (1 - sl_pct / 100)
                # OHLC nie mówi, który poziom został dotknięty pierwszy. Gdy
                # oba są w tej samej świecy, przyjmujemy wariant konserwatywny.
                if c.low <= sl_price:
                    pct, result = -sl_pct, "SL"
                elif c.high >= tp_price:
                    pct, result = tp_pct, "TP"
                elif bars_held >= max_hold_bars:
                    pct = (c.close - entry_price) / entry_price * 100
                    result = "TIMEOUT"
                else:
                    continue
            else:  # SELL (short)
                tp_price = entry_price * (1 - tp_pct / 100)
                sl_price = entry_price * (1 + sl_pct / 100)
                if c.high >= sl_price:
                    pct, result = -sl_pct, "SL"
                elif c.low <= tp_price:
                    pct, result = tp_pct, "TP"
                elif bars_held >= max_hold_bars:
                    pct = (entry_price - c.close) / entry_price * 100
                    result = "TIMEOUT"
                else:
                    continue

            pct -= round_trip_cost_pct
            ts = candles[entry_idx].timestamp
            trades.append({
                "direction": direction,
                "entry_price": round(entry_price, 4),
                "pct": round(pct, 3),
                "result": result,
                "bars_held": bars_held,
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            })
            in_trade = False

        if not in_trade:
            signal, strength = _detect_signal(candles, i, rsi_oversold, rsi_overbought)
            if signal and strength >= 0.44 and i + 1 < len(candles):
                entry_price = candles[i + 1].open
                entry_idx = i + 1
                direction = signal
                in_trade = True

    # Nie pomijaj otwartej pozycji na końcu próbki.
    if in_trade:
        last = candles[-1]
        pct = ((last.close - entry_price) / entry_price * 100
               if direction == "BUY"
               else (entry_price - last.close) / entry_price * 100)
        pct -= round_trip_cost_pct
        ts = candles[entry_idx].timestamp
        trades.append({
            "direction": direction,
            "entry_price": round(entry_price, 4),
            "pct": round(pct, 3),
            "result": "END_OF_DATA",
            "bars_held": len(candles) - 1 - entry_idx,
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
        })

    return trades


# ── Statistics ────────────────────────────────────────────────────────────────

def _stats(trades: list[dict]) -> dict:
    if not trades:
        return {
            "total_signals": 0, "win_count": 0, "loss_count": 0, "timeout_count": 0,
            "win_rate": None, "avg_win_pct": None, "avg_loss_pct": None,
            "avg_return_pct": None, "total_return_pct": None, "expectancy": None,
        }
    wins    = [t for t in trades if t["pct"] > 0]
    losses  = [t for t in trades if t["pct"] <= 0]
    timeouts = [t for t in trades if t["result"] == "TIMEOUT"]
    n = len(trades)
    wr = len(wins) / n
    avg_win  = sum(t["pct"] for t in wins)   / len(wins)   if wins   else 0.0
    avg_loss = sum(t["pct"] for t in losses) / len(losses) if losses else 0.0
    return {
        "total_signals":   n,
        "win_count":       len(wins),
        "loss_count":      len(losses),
        "timeout_count":   len(timeouts),
        "win_rate":        round(wr, 4),
        "avg_win_pct":     round(avg_win,  3),
        "avg_loss_pct":    round(avg_loss, 3),
        "avg_return_pct":  round(sum(t["pct"] for t in trades) / n, 3),
        "total_return_pct":round((math.prod(1 + t["pct"] / 100 for t in trades) - 1) * 100, 3),
        "expectancy":      round(wr * avg_win + (1 - wr) * avg_loss, 4),
    }


def _portfolio_metrics(
    trades: list[dict], initial_capital: float, sl_pct: float,
    risk_per_trade_pct: float = 1.0, max_position_pct: float = 25.0,
    commission_pct: float = 0.05, slippage_pct: float = 0.05,
) -> dict:
    equity = float(initial_capital)
    peak = equity
    max_drawdown = 0.0
    pnl_values: list[float] = []
    returns: list[float] = []
    equity_curve = [{"trade": 0, "equity": round(equity, 2)}]
    enriched = []
    total_costs = 0.0
    for idx, trade in enumerate(trades, 1):
        risk_budget = equity * risk_per_trade_pct / 100
        risk_position = risk_budget / max(sl_pct / 100, 1e-9)
        position_value = min(risk_position, equity * max_position_pct / 100)
        quantity = position_value / max(float(trade["entry_price"]), 1e-9)
        gross_pnl = position_value * float(trade["pct"]) / 100
        # Koszt wejścia i wyjścia; slippage modelowany symetrycznie dla obu nóg.
        costs = position_value * 2 * (commission_pct + slippage_pct) / 100
        pnl = gross_pnl - costs
        total_costs += costs
        before = equity
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak * 100 if peak else 0)
        pnl_values.append(pnl)
        returns.append(pnl / before if before else 0.0)
        enriched.append({**trade, "quantity": round(quantity, 6), "position_value": round(position_value, 2),
                         "gross_pnl": round(gross_pnl, 2), "costs": round(costs, 2),
                         "pnl": round(pnl, 2), "equity_after": round(equity, 2)})
        equity_curve.append({"trade": idx, "equity": round(equity, 2)})
    avg = sum(returns) / len(returns) if returns else 0.0
    variance = sum((x - avg) ** 2 for x in returns) / max(len(returns) - 1, 1)
    downside = [x for x in returns if x < 0]
    down_var = sum(x * x for x in downside) / len(downside) if downside else 0.0
    sharpe = avg / math.sqrt(variance) * math.sqrt(252) if variance > 0 else 0.0
    sortino = avg / math.sqrt(down_var) * math.sqrt(252) if down_var > 0 else 0.0
    gross_profit = sum(x for x in pnl_values if x > 0)
    gross_loss = abs(sum(x for x in pnl_values if x < 0))
    return {
        "initial_capital": round(initial_capital, 2), "final_capital": round(equity, 2),
        "net_profit": round(equity - initial_capital, 2),
        "return_pct": round((equity / initial_capital - 1) * 100, 3),
        "max_drawdown_pct": round(max_drawdown, 3), "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
        "risk_per_trade_pct": risk_per_trade_pct, "max_position_pct": max_position_pct,
        "commission_pct": commission_pct, "slippage_pct": slippage_pct,
        "total_costs": round(total_costs, 2),
        "equity_curve": equity_curve, "trades": enriched,
    }


# ── Calibration grid search ───────────────────────────────────────────────────

def _calibrate(candles: list) -> dict:
    best_exp = -999.0
    best: dict = {
        "rsi_oversold": 32.0, "rsi_overbought": 68.0,
        "sl_pct": 1.5, "tp_pct": 2.0,
    }
    for rsi_os in [28, 32, 36, 40]:
        for rsi_ob in [60, 64, 68, 72]:
            if rsi_ob - rsi_os < 20:
                continue
            for sl in [0.8, 1.0, 1.5, 2.0]:
                for tp in [1.5, 2.0, 2.5, 3.0]:
                    if tp < sl:
                        continue
                    t = _simulate_trades(candles, float(rsi_os), float(rsi_ob), sl, tp)
                    if len(t) < 5:
                        continue
                    s = _stats(t)
                    exp = s["expectancy"] or -999.0
                    if exp > best_exp:
                        best_exp = exp
                        best = {
                            "rsi_oversold":   float(rsi_os),
                            "rsi_overbought": float(rsi_ob),
                            "sl_pct":         sl,
                            "tp_pct":         tp,
                        }
    return best


# ── Public API ────────────────────────────────────────────────────────────────

def _to_response(row: IntradayBacktestORM) -> dict:
    return {
        "id": row.id,
        "asset_id": row.asset_id,
        "resolution": row.resolution,
        "run_at": row.run_at.isoformat() if row.run_at else None,
        "lookback_days": row.lookback_days,
        "candles_count": row.candles_count,
        "total_signals": row.total_signals,
        "win_count": row.win_count,
        "loss_count": row.loss_count,
        "timeout_count": row.timeout_count,
        "win_rate": row.win_rate,
        "avg_win_pct": row.avg_win_pct,
        "avg_loss_pct": row.avg_loss_pct,
        "avg_return_pct": row.avg_return_pct,
        "total_return_pct": row.total_return_pct,
        "expectancy": row.expectancy,
        "calibrated": {
            "rsi_oversold":   row.rsi_oversold,
            "rsi_overbought": row.rsi_overbought,
            "sl_pct":         row.sl_pct,
            "tp_pct":         row.tp_pct,
        },
        "default": {
            "total_signals":  row.default_signals,
            "win_rate":       row.default_win_rate,
            "expectancy":     row.default_expectancy,
        },
        "trades": json.loads(row.trades_json) if row.trades_json else [],
        "portfolio": json.loads(row.metrics_json) if row.metrics_json else {},
    }


def get_latest(db: Session, asset_id: str, resolution: str = "15") -> Optional[dict]:
    row = db.scalars(
        select(IntradayBacktestORM)
        .where(
            IntradayBacktestORM.asset_id == asset_id,
            IntradayBacktestORM.resolution == resolution,
        )
        .order_by(desc(IntradayBacktestORM.run_at))
        .limit(1)
    ).first()
    return _to_response(row) if row else None


def run_backtest(
    db: Session,
    asset_id: str,
    resolution: str = "15",
    lookback_days: int = 30,
    initial_capital: float = 10000.0,
    risk_per_trade_pct: float = 1.0,
    max_position_pct: float = 25.0,
    commission_pct: float = 0.05,
    slippage_pct: float = 0.05,
) -> dict:
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    rows = db.scalars(
        select(IntradayCandleORM)
        .where(
            IntradayCandleORM.asset_id == asset_id,
            IntradayCandleORM.resolution == resolution,
            IntradayCandleORM.timestamp >= cutoff,
        )
        .order_by(IntradayCandleORM.timestamp)
    ).all()

    if len(rows) < 60:
        return {"error": "Za mało danych — wymagane min. 60 świec do podziału kalibracja/test"}

    # Chronologiczny holdout: parametrów nie wolno dobierać na okresie testowym.
    split = max(40, int(len(rows) * 0.70))
    calibration_rows = rows[:split]
    test_rows = rows[split:]
    if len(test_rows) < 20:
        return {"error": "Za mało danych w okresie testowym (min. 20 świec)"}
    best = _calibrate(calibration_rows)

    # Raportowane wyniki pochodzą wyłącznie z niewidzianego okresu testowego.
    trades = _simulate_trades(test_rows, best["rsi_oversold"], best["rsi_overbought"],
                              best["sl_pct"], best["tp_pct"])
    s = _stats(trades)
    portfolio = _portfolio_metrics(
        trades, initial_capital, best["sl_pct"], risk_per_trade_pct,
        max_position_pct, commission_pct, slippage_pct,
    )

    # Baseline with defaults
    def_trades = _simulate_trades(test_rows, 32.0, 68.0, 1.5, 2.0)
    def_s = _stats(def_trades)

    record = IntradayBacktestORM(
        asset_id=asset_id,
        resolution=resolution,
        run_at=datetime.utcnow(),
        lookback_days=lookback_days,
        candles_count=len(test_rows),
        total_signals=s["total_signals"],
        win_count=s["win_count"],
        loss_count=s["loss_count"],
        timeout_count=s["timeout_count"],
        win_rate=s["win_rate"],
        avg_win_pct=s["avg_win_pct"],
        avg_loss_pct=s["avg_loss_pct"],
        avg_return_pct=s["avg_return_pct"],
        total_return_pct=s["total_return_pct"],
        expectancy=s["expectancy"],
        rsi_oversold=best["rsi_oversold"],
        rsi_overbought=best["rsi_overbought"],
        sl_pct=best["sl_pct"],
        tp_pct=best["tp_pct"],
        default_signals=def_s["total_signals"],
        default_win_rate=def_s["win_rate"],
        default_expectancy=def_s["expectancy"],
        trades_json=json.dumps(trades[-50:]),
        initial_capital=initial_capital,
        metrics_json=json.dumps(portfolio),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _to_response(record)
