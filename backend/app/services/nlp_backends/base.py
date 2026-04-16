"""
base.py — protokół warstwy NLP.

Każdy backend musi implementować trzy metody:
  classify_sentiment   → dict z score, label, confidence
  classify_narratives  → lista dict z narrative_label, score, confidence
  score_relevance      → float 0-1

Nowe backendy można dodać implementując NLPBackend i rejestrując
w nlp_registry.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.common import AssetType


class NLPBackend(ABC):

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identyfikator backendu zapisywany w bazie."""

    @abstractmethod
    def classify_sentiment(self, title: str, body: str) -> dict:
        """
        Zwraca dict:
          score: float [-1, +1]   pozytywny = bullish
          label: "positive" | "neutral" | "negative"
          confidence: float [0, 1]
        """

    @abstractmethod
    def classify_narratives(
        self,
        title: str,
        body: str,
        asset_type: AssetType,
    ) -> list[dict]:
        """
        Zwraca listę dict:
          narrative_label: str
          score: float [0, 1]
          confidence: float [0, 1]
        Posortowane malejąco po score.
        """

    @abstractmethod
    def score_relevance(
        self,
        title: str,
        body: str,
        asset_name: str,
        symbol: str,
        sector: str | None,
    ) -> float:
        """Zwraca float [0, 1] — jak bardzo news dotyczy danego aktywa."""
