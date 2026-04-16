"""
heuristic.py — keyword-based NLP backend.

Zawsze dostępny, nie wymaga dodatkowych zależności.
Używany jako fallback gdy transformers nie są zainstalowane.
"""
from __future__ import annotations

from app.schemas.common import AssetType, NarrativeLabel
from app.services.nlp_backends.base import NLPBackend


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


_POSITIVE = ["strong", "beats", "beat", "support", "growth", "record", "upgrades",
             "improves", "bullish", "surge", "rally", "outperform", "upgrade",
             "profit", "revenue beat", "positive", "robust", "resilient"]
_NEGATIVE = ["risk", "miss", "missed", "cut", "pressure", "decline", "lawsuit",
             "weak", "bearish", "drop", "downgrade", "loss", "warning", "concern",
             "uncertainty", "slump", "sell-off", "default", "bankruptcy"]

_HIGH_IMPACT = ["earnings", "guidance", "lawsuit", "fed", "tariff", "export",
                "acquisition", "central bank", "rate hike", "rate cut", "gdp",
                "inflation", "merger", "bankruptcy", "sec", "investigation"]

_FINANCIAL_TERMS = ["revenue", "earnings", "eps", "guidance", "margin", "capex",
                    "dividend", "buyback", "debt", "cash flow", "valuation",
                    "forward pe", "upgrade", "downgrade", "target price", "analyst",
                    "fiscal", "quarterly", "annual report", "10-k", "10-q"]


class HeuristicNLPBackend(NLPBackend):

    @property
    def model_name(self) -> str:
        return "heuristic_nlp_v3"

    def classify_sentiment(self, title: str, body: str) -> dict:
        text = f"{title} {body}".lower()
        pos = sum(1 for w in _POSITIVE if w in text)
        neg = sum(1 for w in _NEGATIVE if w in text)
        raw = (pos - neg) / max(1, pos + neg + 2)
        score = _clamp(raw * 2.0)
        if score > 0.15:
            label = "positive"
        elif score < -0.15:
            label = "negative"
        else:
            label = "neutral"
        confidence = min(0.92, 0.45 + abs(score) * 0.5)
        return {"score": round(score, 4), "label": label, "confidence": round(confidence, 4)}

    def classify_narratives(self, title: str, body: str, asset_type: AssetType) -> list[dict]:
        text = f"{title} {body}".lower()
        scores: dict[NarrativeLabel, float] = {}

        def hit(label: NarrativeLabel, keywords: list[str], base: float = 0.72) -> None:
            hits = sum(1 for kw in keywords if kw in text)
            if hits:
                scores[label] = min(0.97, base + hits * 0.07)

        if asset_type == AssetType.STOCK:
            hit(NarrativeLabel.AI_GROWTH,
                ["ai", "artificial intelligence", "data center", "gpu", "llm",
                 "generative ai", "machine learning", "neural network"])
            hit(NarrativeLabel.MARGIN_PRESSURE,
                ["margin", "cost pressure", "pricing pressure", "input cost",
                 "supply chain cost", "gross margin"])
            hit(NarrativeLabel.DEMAND_STRENGTH,
                ["demand", "orders", "growth", "capex", "backlog", "pipeline",
                 "record revenue", "record orders"])
            hit(NarrativeLabel.DEMAND_SLOWDOWN,
                ["slowdown", "weak demand", "soft demand", "declining orders",
                 "inventory build", "channel inventory"])
            hit(NarrativeLabel.REGULATION_RISK,
                ["regulation", "antitrust", "export restriction", "lawsuit",
                 "probe", "investigation", "ban", "sanction", "compliance"])
            hit(NarrativeLabel.VALUATION_STRETCH,
                ["valuation", "overvalued", "multiple expansion", "premium",
                 "pe ratio", "expensive", "bubble"])
        else:
            hit(NarrativeLabel.SAFE_HAVEN,
                ["safe haven", "geopolitical", "flight to safety", "uncertainty",
                 "risk off", "volatility", "crisis", "war", "conflict"])
            hit(NarrativeLabel.RATES_PRESSURE,
                ["rates", "yield", "real yield", "fed", "interest rate",
                 "monetary policy", "rate hike", "rate cut", "treasury"])
            hit(NarrativeLabel.DOLLAR_PRESSURE,
                ["dollar", "usd", "dxy", "dollar strength", "dollar weakness"])
            hit(NarrativeLabel.CENTRAL_BANK_BUYING,
                ["central bank", "reserve diversification", "official sector",
                 "sovereign", "pbc", "rbi", "boj gold"])
            hit(NarrativeLabel.INDUSTRIAL_DEMAND,
                ["industrial demand", "manufacturing", "electronics", "automotive",
                 "solar", "renewable", "chip", "green energy"])
            hit(NarrativeLabel.SUPPLY_DISRUPTION,
                ["mine", "supply disruption", "production cut", "sanction",
                 "strike", "flooding", "closure", "shortage"])

        if not scores:
            default = NarrativeLabel.DEMAND_STRENGTH if asset_type == AssetType.STOCK else NarrativeLabel.SAFE_HAVEN
            scores[default] = 0.28

        results = [
            {
                "narrative_label": lbl.value if hasattr(lbl, "value") else str(lbl),
                "score": round(s, 4),
                "confidence": round(min(0.9, s * 0.85), 4),
            }
            for lbl, s in scores.items()
        ]
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def score_relevance(
        self,
        title: str,
        body: str,
        asset_name: str,
        symbol: str,
        sector: str | None,
    ) -> float:
        text = f"{title} {body}".lower()
        name_l = asset_name.lower()
        sym_l = symbol.lower()

        score = 0.20  # base
        # Wzmianka nazwy
        name_hits = text.count(name_l)
        if name_hits >= 1:
            score += 0.30 + min(0.10, (name_hits - 1) * 0.03)
        # Wzmianka symbolu
        if f" {sym_l} " in f" {text} ":
            score += 0.20
        # Wzmianka sektora
        if sector and sector.lower() in text:
            score += 0.10
        # Gęstość języka finansowego
        fin_hits = sum(1 for term in _FINANCIAL_TERMS if term in text)
        score += min(0.15, fin_hits * 0.02)
        # Kara za krótki tekst (mogą być placeholder newsy)
        if len(text) < 100:
            score *= 0.7

        return round(min(1.0, score), 4)
