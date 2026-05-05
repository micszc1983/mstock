from __future__ import annotations

from fastapi import APIRouter
from app.core.config import settings
from app.services.sms_alert_config import load_config, save_config, _DEFAULTS

router = APIRouter(prefix="/admin", tags=["sms-config"])

ALERT_RULE_LABELS = {
    "fragility_high":             "Wysoka kruchość",
    "dominant_narrative_changed": "Zmiana dominującej narracji",
    "forecast_downgrade":         "Obniżenie prognozy",
    "signal_flip_kup_sprzedaj":   "Zmiana sygnału KUP → SPRZEDAJ",
    "price_drop_session":         "Duży spadek ceny na sesji",
    "dead_data":                  "Brak aktualizacji danych",
    "data_quality_low":           "Niska jakość danych",
    "ml_bearish_divergence":      "Dywergencja ML (bearish)",
}

ALERT_RULE_DESCRIPTIONS = {
    "fragility_high":             "Fragility score przekroczył próg (0–100). Alert przy każdym cyklu schedulera.",
    "dominant_narrative_changed": "Narracja rynkowa zmieniła się względem poprzedniego snapshotu.",
    "forecast_downgrade":         "Prognoza kierunkowa została obniżona.",
    "signal_flip_kup_sprzedaj":   "Rekomendacja zmieniła się z KUP na SPRZEDAJ.",
    "price_drop_session":         "Cena spadła o więcej niż próg % w stosunku do poprzedniego zamknięcia.",
    "dead_data":                  "Dane nie były aktualizowane przez X godzin.",
    "data_quality_low":           "Ogólny wynik jakości danych poniżej progu.",
    "ml_bearish_divergence":      "ML prob_up < próg przy zielonych heurystykach — możliwa dywergencja.",
}

THRESHOLD_LABELS = {
    "fragility_high":        "Próg fragility (0–100)",
    "price_drop_session":    "Próg spadku ceny (%, wartość ujemna)",
    "dead_data":             "Próg braku danych (godziny)",
    "data_quality_low":      "Próg jakości danych (0–100)",
    "ml_bearish_divergence": "Próg prob_up (0.0–1.0, gdy poniżej = alert)",
}


@router.get("/sms-alert-config")
def get_sms_alert_config():
    cfg = load_config()
    return {
        "sms_status": {
            "enabled": settings.sms_enabled,
            "port": settings.sms_serial_port,
            "recipient": settings.sms_recipient_phone or "(nie skonfigurowany)",
            "finnhub_configured": bool(settings.finnhub_api_key),
        },
        "alert_rules": cfg.get("alert_rules", {}),
        "top_picks_sms": cfg.get("top_picks_sms", {}),
        "portfolio_sell_urgent": cfg.get("portfolio_sell_urgent", {}),
        "premarket_gap": cfg.get("premarket_gap", {}),
        "alert_rule_labels": ALERT_RULE_LABELS,
        "alert_rule_descriptions": ALERT_RULE_DESCRIPTIONS,
        "threshold_labels": THRESHOLD_LABELS,
        "defaults": _DEFAULTS,
    }


@router.post("/sms-alert-config")
def save_sms_alert_config(body: dict):
    allowed_keys = {"alert_rules", "top_picks_sms", "portfolio_sell_urgent", "premarket_gap"}
    filtered = {k: v for k, v in body.items() if k in allowed_keys}
    current = load_config()
    merged = {**current, **filtered}
    save_config(merged)
    return {"ok": True, "saved": list(filtered.keys())}