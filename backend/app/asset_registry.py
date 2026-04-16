"""
asset_registry.py — centralny rejestr aktywów.

Plik konfiguracyjny: backend/assets.json

Aby dodać aktywo:
  1. Dodaj wpis do assets.json
  2. Zrestartuj backend — nowe aktywo pojawi się automatycznie w seederze
     i w konfiguracji providerów

Pola w assets.json:
  id              — unikalny identyfikator (małe litery, bez spacji)
  symbol          — ticker giełdowy
  name            — wyświetlana nazwa
  type            — "stock" lub "metal"
  sector          — sektor (opcjonalne)
  description     — opis (opcjonalne)
  seed_price      — cena startowa do generowania fikcyjnych danych
  price_symbol    — symbol do Alpha Vantage (np. "AAPL"); null = brak
  news_symbol     — symbol do Finnhub company-news; null = użyj news_term
  news_term       — słowo kluczowe do Alpha Vantage news search
  metal_price_fn  — funkcja Alpha Vantage do metali (np. "GOLD"); null = brak
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_ASSETS_FILE = Path(__file__).parent.parent / "assets.json"


@dataclass(frozen=True)
class AssetDefinition:
    id: str
    symbol: str
    name: str
    type: str                        # "stock" | "metal"
    currency: str                    # waluta w której przechowywane są ceny: "USD" | "PLN"
    sector: Optional[str]
    description: Optional[str]
    seed_price: float
    price_symbol: Optional[str]      # Alpha Vantage stock symbol
    news_symbol: Optional[str]       # Finnhub symbol
    news_term: str                   # Alpha Vantage news keyword
    metal_price_fn: Optional[str]    # Alpha Vantage metal function


def _load() -> list[AssetDefinition]:
    if not _ASSETS_FILE.exists():
        raise FileNotFoundError(
            f"Nie znaleziono pliku konfiguracji aktywów: {_ASSETS_FILE}\n"
            f"Utwórz plik assets.json w katalogu backend/ według wzoru w dokumentacji."
        )
    raw = json.loads(_ASSETS_FILE.read_text(encoding="utf-8"))
    assets = []
    for entry in raw:
        # Waluta: explicite z pola "currency", fallback: .WA → PLN, metal → USD, reszta → USD
        def _infer_currency(e: dict) -> str:
            if e.get("currency"):
                return e["currency"]
            if (e.get("price_symbol") or "").upper().endswith(".WA"):
                return "PLN"
            return "USD"

        assets.append(AssetDefinition(
            id=entry["id"],
            symbol=entry["symbol"],
            name=entry["name"],
            type=entry["type"],
            currency=_infer_currency(entry),
            sector=entry.get("sector"),
            description=entry.get("description"),
            seed_price=float(entry.get("seed_price", 100)),
            price_symbol=entry.get("price_symbol"),
            news_symbol=entry.get("news_symbol"),
            news_term=entry.get("news_term", entry["name"]),
            metal_price_fn=entry.get("metal_price_fn"),
        ))
    return assets


# Ładowany raz przy imporcie modułu
ASSET_DEFINITIONS: list[AssetDefinition] = _load()

# Mapa id → definicja (do szybkiego lookup)
ASSET_MAP: dict[str, AssetDefinition] = {a.id: a for a in ASSET_DEFINITIONS}

# Konfiguracja providerów w formacie oczekiwanym przez config.py
PROVIDER_CONFIG: dict[str, dict] = {
    a.id: {
        "price_symbol":   a.price_symbol,
        "news_symbol":    a.news_symbol,
        "news_term":      a.news_term,
        "metal_price_fn": a.metal_price_fn,
    }
    for a in ASSET_DEFINITIONS
}
