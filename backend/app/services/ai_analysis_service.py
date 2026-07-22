"""
ai_analysis_service.py

Holograficzny kontekst — analiza intraday na żądanie przez Claude.
Zbiera wszystkie dostępne sygnały (świece, wskaźniki, anomalia, insider,
PEAD, kalibracja backtestingu) i generuje rekomendację po polsku.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AssetORM
from app.services.intraday_service import get_candles, get_latest_signals


_MODEL = "claude-opus-4-7"
_MAX_TOKENS = 700

_SYSTEM_PROMPT = """Jesteś asystentem inwestycyjnym specjalizującym się w analizie technicznej intraday.
Twoim zadaniem jest synteza wszystkich dostępnych sygnałów rynkowych i wydanie konkretnej rekomendacji tradingowej.

Zasady interpretacji wskaźników:
- RSI < 35 → wyprzedanie (potencjalne odbicie); RSI > 65 → wykupienie (ryzyko korekty)
- MACD crossover w górę przy niskim RSI → silny sygnał BUY; crossover w dół przy wysokim RSI → SELL
- Cena powyżej VWAP → przewaga kupujących; poniżej VWAP → presja sprzedających
- volume_ratio > 1.5 potwierdza ruch kierunkowy (breakout/breakdown)
- EMA9 > EMA20 → krótkoterminowy trend wzrostowy; EMA9 < EMA20 → trend spadkowy
- anomaly_score > 0.6 → ostrzeżenie przed nieoczekiwanym ruchem cenowym
- insider_sentiment > 0 → pozytywny sygnał fundamentalny (zakupy zarządu)
- PEAD drift > 0 → kontynuacja wzrostu po pozytywnych wynikach kwartalnych
- Kalibracja backtestingu podaje historycznie optymalne progi dla konkretnego aktywa

Przy wyznaczaniu poziomów:
- stop_loss: cena_wejścia × (1 − sl_pct / 100) dla BUY; cena_wejścia × (1 + sl_pct / 100) dla SELL
- take_profit: cena_wejścia × (1 + tp_pct / 100) dla BUY; cena_wejścia × (1 − tp_pct / 100) dla SELL
- Użyj sl_pct i tp_pct z kalibracji backtestingu jeśli dostępne; w przeciwnym razie SL=1%, TP=2%

Odpowiadaj WYŁĄCZNIE jako poprawny JSON, bez markdown, bez dodatkowego tekstu."""


def _candles_summary(candles: list) -> list[dict]:
    last = candles[-20:] if len(candles) > 20 else candles
    result = []
    for c in last:
        result.append({
            "t": c.timestamp.strftime("%H:%M"),
            "c": round(c.close, 2) if c.close else None,
            "v": int(c.volume) if c.volume else None,
            "rsi": round(c.rsi, 1) if c.rsi else None,
            "ema9": round(c.ema9, 2) if c.ema9 else None,
            "ema20": round(c.ema20, 2) if c.ema20 else None,
            "macd": round(c.macd, 4) if c.macd else None,
            "macd_sig": round(c.macd_signal, 4) if c.macd_signal else None,
            "vwap": round(c.vwap, 2) if c.vwap else None,
            "vol_r": round(c.volume_ratio, 2) if c.volume_ratio else None,
        })
    return result


def analyze_intraday(db: Session, asset: AssetORM, resolution: str = "15") -> dict:
    """Generuje holograficzną analizę intraday. Zwraca dict gotowy do JSON."""
    if not settings.anthropic_api_key:
        return {"error": "Brak ANTHROPIC_API_KEY — analiza AI niedostępna"}

    try:
        import anthropic
    except ImportError:
        return {"error": "Brak pakietu 'anthropic' — zainstaluj: pip install anthropic"}

    candles = get_candles(db, asset.id, resolution=resolution, limit=50)
    if not candles:
        return {"error": "Brak danych świec — uruchom synchronizację intraday"}

    signals_data = get_latest_signals(db, asset.id, resolution=resolution)

    anomaly: Optional[dict] = None
    try:
        from app.services.anomaly_service import get_latest as _get_anomaly
        raw = _get_anomaly(db, asset.id)
        if raw:
            anomaly = {
                "score": round(raw.score, 3) if hasattr(raw, "score") else None,
                "is_anomaly": raw.is_anomaly if hasattr(raw, "is_anomaly") else None,
                "reason": raw.reason if hasattr(raw, "reason") else None,
            }
    except Exception:
        pass

    insider: Optional[dict] = None
    try:
        from app.services.insider_service import get_insider_sentiment
        raw_i = get_insider_sentiment(db, asset.id)
        if isinstance(raw_i, dict):
            insider = {
                "sentiment": round(raw_i.get("net_sentiment", 0), 3),
                "buy_count": raw_i.get("buy_count"),
                "sell_count": raw_i.get("sell_count"),
                "signal": raw_i.get("signal"),
            }
    except Exception:
        pass

    pead: Optional[dict] = None
    try:
        from app.services.pead_service import analyze_pead
        raw_p = analyze_pead(db, asset.id)
        if isinstance(raw_p, dict):
            pead = {
                "drift_pct": round(raw_p.get("drift_pct", 0), 2),
                "days_since_earnings": raw_p.get("days_since_earnings"),
                "expected_direction": raw_p.get("expected_direction"),
            }
    except Exception:
        pass

    backtest: Optional[dict] = None
    try:
        from app.services.intraday_backtest_service import get_latest as _get_bt
        bt = _get_bt(db, asset.id, resolution)
        if bt:
            backtest = {
                "rsi_oversold": bt.rsi_oversold,
                "rsi_overbought": bt.rsi_overbought,
                "sl_pct": bt.sl_pct,
                "tp_pct": bt.tp_pct,
                "win_rate_pct": round(bt.win_rate * 100, 1) if bt.win_rate else None,
                "expectancy": round(bt.expectancy, 3) if bt.expectancy else None,
            }
    except Exception:
        pass

    last_candle = candles[-1]
    data_payload = {
        "aktywo": {"id": asset.id, "nazwa": asset.name, "symbol": asset.symbol, "waluta": asset.currency},
        "resolution_min": resolution,
        "ostatnia_cena": round(last_candle.close, 2) if last_candle.close else None,
        "ostatni_timestamp": last_candle.timestamp.strftime("%Y-%m-%d %H:%M"),
        "swiece_ostatnie_20": _candles_summary(candles),
        "sygnaly": signals_data,
        "anomalia": anomaly,
        "insider": insider,
        "pead": pead,
        "kalibracja": backtest,
    }

    expected_format = """{
  "decyzja": "KUP",
  "pewnosc": 72,
  "uzasadnienie": "...",
  "kluczowe_argumenty": ["...", "...", "..."],
  "ryzyka": ["...", "..."],
  "poziomy": {"wejscie": 185.40, "stop_loss": 183.54, "take_profit": 189.11},
  "horyzont": "2-4 godziny"
}"""

    user_message = (
        f"Przeanalizuj dane intraday i wydaj rekomendację:\n\n"
        f"```json\n{json.dumps(data_payload, ensure_ascii=False, indent=2)}\n```\n\n"
        f"Odpowiedz TYLKO tym JSON-em (wartości decyzja: KUP | TRZYMAJ | SPRZEDAJ):\n{expected_format}"
    )

    raw = ""
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_message}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown fences if Claude wrapped it
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:].strip()
        data = json.loads(raw)
        data["_model"] = _MODEL
        cached_tokens = getattr(message.usage, "cache_read_input_tokens", 0) or 0
        data["_cached"] = cached_tokens > 0
        return data
    except json.JSONDecodeError as exc:
        return {"error": f"Nieprawidłowy JSON od Claude: {exc}", "_raw": raw}
    except Exception as exc:
        return {"error": f"Błąd Claude API: {exc}"}
