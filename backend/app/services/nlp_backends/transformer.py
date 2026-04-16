"""
transformer.py — FinBERT + sentence-transformers NLP backend.

Wymagania (zainstaluj ręcznie lub dodaj do requirements.txt):
  pip install transformers torch sentence-transformers

Modele pobierane automatycznie przy pierwszym użyciu (cache w ~/.cache/huggingface):
  ProsusAI/finbert                    (~440 MB)  — sentiment finansowy
  sentence-transformers/all-MiniLM-L6-v2 (~80 MB) — embeddingi do narracji i relevance

Wzorzec: lazy singleton — modele ładowane raz przy pierwszym wywołaniu,
potem trzymane w pamięci. Backend działa w tym samym procesie co FastAPI.

Czas pierwszego ładowania: ~10–30s (zależnie od sprzętu).
Czas inferencji per news: ~50–200ms (CPU), ~10–30ms (GPU).
"""
from __future__ import annotations

import math
from typing import Optional

from app.schemas.common import AssetType, NarrativeLabel
from app.services.nlp_backends.base import NLPBackend


# ── Opisy narracji do porównania semantycznego ────────────────────────────────
# Dłuższe opisy → lepszy embedding → wyższa jakość klasyfikacji
_NARRATIVE_DESCRIPTIONS: dict[NarrativeLabel, str] = {
    NarrativeLabel.AI_GROWTH: (
        "artificial intelligence growth, AI infrastructure demand, data center expansion, "
        "GPU orders, large language models, generative AI adoption, machine learning investment"
    ),
    NarrativeLabel.MARGIN_PRESSURE: (
        "margin compression, rising input costs, pricing pressure, gross margin decline, "
        "cost inflation, supply chain costs, operating leverage negative"
    ),
    NarrativeLabel.DEMAND_STRENGTH: (
        "strong customer demand, record orders, robust revenue growth, backlog expansion, "
        "capex investment cycle, positive business momentum, sales acceleration"
    ),
    NarrativeLabel.DEMAND_SLOWDOWN: (
        "weak demand environment, declining orders, inventory buildup, channel stuffing, "
        "soft consumer spending, business investment slowdown, demand destruction"
    ),
    NarrativeLabel.REGULATION_RISK: (
        "regulatory investigation, antitrust lawsuit, export restrictions, government probe, "
        "compliance risk, regulatory ban, sanctions, legal settlement"
    ),
    NarrativeLabel.VALUATION_STRETCH: (
        "overvalued stock, stretched valuation multiples, premium to peers, "
        "high price-to-earnings ratio, bubble concerns, expensive relative to growth"
    ),
    NarrativeLabel.SAFE_HAVEN: (
        "safe haven demand, geopolitical uncertainty, flight to safety, risk-off sentiment, "
        "global crisis, war conflict, market volatility spike, investor fear"
    ),
    NarrativeLabel.RATES_PRESSURE: (
        "interest rate hikes, rising bond yields, real yield increase, Federal Reserve tightening, "
        "monetary policy, treasury yields, rate expectations hawkish"
    ),
    NarrativeLabel.DOLLAR_PRESSURE: (
        "US dollar strength, DXY index, dollar appreciation, strong greenback, "
        "currency headwinds, forex pressure, dollar dominance"
    ),
    NarrativeLabel.CENTRAL_BANK_BUYING: (
        "central bank gold purchases, official sector buying, reserve diversification, "
        "sovereign wealth fund, de-dollarization, reserve accumulation"
    ),
    NarrativeLabel.INDUSTRIAL_DEMAND: (
        "industrial consumption, manufacturing demand, electronics production, automotive sector, "
        "renewable energy, solar panels, green transition, chip manufacturing"
    ),
    NarrativeLabel.SUPPLY_DISRUPTION: (
        "mine supply disruption, production cuts, sanctions on supply, labor strike, "
        "natural disaster impact, output shortage, supply chain breakdown"
    ),
}

_STOCK_NARRATIVES = {
    NarrativeLabel.AI_GROWTH,
    NarrativeLabel.MARGIN_PRESSURE,
    NarrativeLabel.DEMAND_STRENGTH,
    NarrativeLabel.DEMAND_SLOWDOWN,
    NarrativeLabel.REGULATION_RISK,
    NarrativeLabel.VALUATION_STRETCH,
}
_METAL_NARRATIVES = {
    NarrativeLabel.SAFE_HAVEN,
    NarrativeLabel.RATES_PRESSURE,
    NarrativeLabel.DOLLAR_PRESSURE,
    NarrativeLabel.CENTRAL_BANK_BUYING,
    NarrativeLabel.INDUSTRIAL_DEMAND,
    NarrativeLabel.SUPPLY_DISRUPTION,
}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class TransformerNLPBackend(NLPBackend):
    """
    Lazy-loaded transformer backend.
    Modele ładowane przy pierwszym użyciu.
    """

    def __init__(self) -> None:
        self._finbert_pipeline = None
        self._st_model = None
        self._narrative_embeddings: Optional[dict[NarrativeLabel, list[float]]] = None

    @property
    def model_name(self) -> str:
        return "finbert_minilm_v1"

    # ── Private loaders ──────────────────────────────────────────────────────

    def _load_finbert(self):
        if self._finbert_pipeline is not None:
            return self._finbert_pipeline
        from transformers import pipeline
        print("[NLP] Ładowanie FinBERT (ProsusAI/finbert)…")
        self._finbert_pipeline = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            top_k=3,        # zwróć wszystkie 3 klasy
            truncation=True,
            max_length=512,
        )
        print("[NLP] FinBERT załadowany.")
        return self._finbert_pipeline

    def _load_st(self):
        if self._st_model is not None:
            return self._st_model
        from sentence_transformers import SentenceTransformer
        print("[NLP] Ładowanie SentenceTransformer (all-MiniLM-L6-v2)…")
        self._st_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        print("[NLP] SentenceTransformer załadowany.")
        return self._st_model

    def _get_narrative_embeddings(self) -> dict[NarrativeLabel, list[float]]:
        """Pre-compute i cache'uj embeddingi opisów narracji."""
        if self._narrative_embeddings is not None:
            return self._narrative_embeddings
        model = self._load_st()
        descriptions = {lbl: desc for lbl, desc in _NARRATIVE_DESCRIPTIONS.items()}
        texts = list(descriptions.values())
        labels = list(descriptions.keys())
        embeddings = model.encode(texts, convert_to_numpy=False, show_progress_bar=False)
        self._narrative_embeddings = {
            lbl: emb.tolist() for lbl, emb in zip(labels, embeddings)
        }
        return self._narrative_embeddings

    # ── Public methods ───────────────────────────────────────────────────────

    def classify_sentiment(self, title: str, body: str) -> dict:
        """
        FinBERT zwraca {positive, negative, neutral} z prawdopodobieństwami.
        Score = positive_prob - negative_prob → [-1, +1].
        """
        text = f"{title}. {body}"[:512]
        try:
            pipe = self._load_finbert()
            results = pipe(text)[0]  # lista [{label, score}, ...]
            probs = {r["label"].lower(): r["score"] for r in results}
            pos = probs.get("positive", 0.0)
            neg = probs.get("negative", 0.0)
            neu = probs.get("neutral", 0.0)
            score = pos - neg
            if score > 0.10:
                label = "positive"
            elif score < -0.10:
                label = "negative"
            else:
                label = "neutral"
            confidence = 1.0 - neu  # pewność tym wyższa im mniej neutralne
            confidence = min(0.97, max(0.40, confidence))
            return {
                "score": round(float(score), 4),
                "label": label,
                "confidence": round(float(confidence), 4),
            }
        except Exception as exc:
            print(f"[NLP] FinBERT error: {exc}, fallback to heuristic")
            from app.services.nlp_backends.heuristic import HeuristicNLPBackend
            return HeuristicNLPBackend().classify_sentiment(title, body)

    def classify_narratives(self, title: str, body: str, asset_type: AssetType) -> list[dict]:
        """
        Porównuje embedding newsa z embeddingami opisów narracji przez cosine similarity.
        Filtruje narracje nieodpowiednie dla danego typu aktywa.
        """
        target_labels = _STOCK_NARRATIVES if asset_type == AssetType.STOCK else _METAL_NARRATIVES
        text = f"{title}. {body}"[:1024]
        try:
            model = self._load_st()
            narrative_embs = self._get_narrative_embeddings()
            news_emb = model.encode(text, convert_to_numpy=False, show_progress_bar=False).tolist()
            results = []
            for lbl in target_labels:
                if lbl not in narrative_embs:
                    continue
                sim = _cosine(news_emb, narrative_embs[lbl])
                # Cosine similarity w zakresie [-1, 1] → przeskaluj do [0, 1]
                # Przy tekstach finansowych typowe wartości to 0.15–0.65
                # Próg 0.30 = "słaba zbieżność", >0.50 = "silna"
                score = max(0.0, sim)
                # Normalizacja: zakres [0.25, 0.75] → [0.0, 1.0]
                normalized = min(1.0, max(0.0, (score - 0.25) / 0.50))
                if normalized < 0.08:
                    continue  # pomiń bardzo słabe dopasowania
                confidence = min(0.95, normalized * 0.9 + 0.05)
                results.append({
                    "narrative_label": lbl.value if hasattr(lbl, "value") else str(lbl),
                    "score": round(normalized, 4),
                    "confidence": round(confidence, 4),
                })
            results.sort(key=lambda x: x["score"], reverse=True)
            if not results:
                # Fallback — dodaj domyślną narrację z niskim score
                from app.services.nlp_backends.heuristic import HeuristicNLPBackend
                return HeuristicNLPBackend().classify_narratives(title, body, asset_type)
            return results[:6]  # max 6 narracji per news
        except Exception as exc:
            print(f"[NLP] Narrative embedding error: {exc}, fallback to heuristic")
            from app.services.nlp_backends.heuristic import HeuristicNLPBackend
            return HeuristicNLPBackend().classify_narratives(title, body, asset_type)

    def score_relevance(
        self,
        title: str,
        body: str,
        asset_name: str,
        symbol: str,
        sector: str | None,
    ) -> float:
        """
        Trzyskładnikowy scoring:
          1. Entity mention score — bezpośrednie wzmiankowania nazwy/symbolu
          2. Semantic similarity — embedding newsa vs opis aktywa
          3. Financial language density — gęstość terminologii finansowej
        """
        text = f"{title} {body}".lower()
        name_l = asset_name.lower()
        sym_l = symbol.lower()

        # 1. Entity mentions (waga 0.55)
        entity_score = 0.0
        name_hits = text.count(name_l)
        if name_hits >= 1:
            entity_score += 0.45 + min(0.10, (name_hits - 1) * 0.04)
        sym_hits = text.count(f" {sym_l} ") + text.count(f"({sym_l})")
        if sym_hits >= 1:
            entity_score += 0.30 + min(0.05, (sym_hits - 1) * 0.02)
        if sector and sector.lower() in text:
            entity_score += 0.10
        entity_score = min(1.0, entity_score)

        # 2. Semantic similarity (waga 0.30)
        # Opis aktywa = "nazwa sektor" np. "NVIDIA Semiconductors"
        try:
            model = self._load_st()
            asset_desc = f"{asset_name} {symbol} {sector or ''}".strip()
            news_text = f"{title}. {body}"[:512]
            embs = model.encode([news_text, asset_desc], convert_to_numpy=False, show_progress_bar=False)
            semantic_score = max(0.0, _cosine(embs[0].tolist(), embs[1].tolist()))
            # Normalizacja: zakres [0.2, 0.8] → [0, 1]
            semantic_score = min(1.0, max(0.0, (semantic_score - 0.20) / 0.60))
        except Exception:
            semantic_score = entity_score * 0.5  # fallback

        # 3. Financial language density (waga 0.15)
        fin_terms = ["revenue", "earnings", "eps", "guidance", "margin", "capex",
                     "dividend", "buyback", "analyst", "target price", "upgrade",
                     "downgrade", "forecast", "outlook", "quarterly", "annual"]
        fin_hits = sum(1 for t in fin_terms if t in text)
        fin_score = min(1.0, fin_hits / 5.0)

        # Kara za bardzo krótkie teksty
        length_penalty = 1.0 if len(text) >= 150 else max(0.5, len(text) / 150)

        composite = (
            entity_score  * 0.55 +
            semantic_score * 0.30 +
            fin_score      * 0.15
        ) * length_penalty

        return round(min(1.0, max(0.0, composite)), 4)
