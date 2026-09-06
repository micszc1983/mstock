"""
sms_alert_config.py — konfiguracja alertów SMS przechowywana w JSON.

Plik konfiguracyjny: backend/sms_alert_config.json
Czytany na żądanie (bez potrzeby restartu backendu).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "sms_alert_config.json"
_lock = threading.Lock()

_DEFAULTS: dict[str, Any] = {
    "alert_rules": {
        "fragility_high":             {"enabled": True,  "threshold": 60.0,  "cooldown_minutes": 120},
        "dominant_narrative_changed": {"enabled": True,  "cooldown_minutes": 180},
        "forecast_downgrade":         {"enabled": True,  "cooldown_minutes": 180},
        "signal_flip_kup_sprzedaj":   {"enabled": True,  "cooldown_minutes": 1440},
        "price_drop_session":         {"enabled": True,  "threshold": -5.0,  "cooldown_minutes": 1440},
        "dead_data":                  {"enabled": False, "cooldown_minutes": 240},
        "data_quality_low":           {"enabled": False, "threshold": 50.0,  "cooldown_minutes": 1440},
        "ml_bearish_divergence":      {"enabled": True,  "threshold": 0.4,   "cooldown_minutes": 360},
    },
    "top_picks_sms": {
        "enabled": True,
    },
    "paper_trading_sms": {
        "enabled": True,
    },
    "portfolio_sell_urgent": {
        "enabled": True,
        "cooldown_minutes": 360,
    },
    "premarket_gap": {
        "enabled": True,
        "portfolio_threshold_pct": 3.0,
        "watchlist_threshold_pct": 5.0,
    },
    "intraday_sms": {
        "enabled": True,
        "min_strength": 60,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config() -> dict[str, Any]:
    """Zwraca aktualną konfigurację (defaults + overrides z pliku JSON)."""
    if not _CONFIG_PATH.exists():
        return _DEFAULTS

    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            overrides = json.load(f)
        return _deep_merge(_DEFAULTS, overrides)
    except Exception as exc:
        print(f"[sms_alert_config] Błąd odczytu {_CONFIG_PATH}: {exc} — używam defaults")
        return _DEFAULTS


def save_config(cfg: dict[str, Any]) -> None:
    """Zapisuje konfigurację do pliku JSON."""
    with _lock:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_alert_rule(alert_type: str) -> dict[str, Any]:
    cfg = load_config()
    defaults = _DEFAULTS["alert_rules"].get(alert_type, {"enabled": True, "cooldown_minutes": 60})
    rule = cfg.get("alert_rules", {}).get(alert_type, {})
    return _deep_merge(defaults, rule)


def is_alert_enabled(alert_type: str) -> bool:
    return bool(get_alert_rule(alert_type).get("enabled", True))


def get_section(section: str) -> dict[str, Any]:
    cfg = load_config()
    defaults = _DEFAULTS.get(section, {})
    override = cfg.get(section, {})
    return _deep_merge(defaults, override)
