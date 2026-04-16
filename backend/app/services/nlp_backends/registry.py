"""
registry.py — singleton loader backendu NLP.

Konfiguracja w .env:
  NLP_BACKEND=auto         # (domyślnie) spróbuj transformer, fallback na heuristic
  NLP_BACKEND=transformer  # wymusza transformer (error jeśli brak zależności)
  NLP_BACKEND=heuristic    # zawsze heuristic (szybki, bez GPU/modeli)

Modele są ładowane leniwie — nie spowalniają startu serwera.
"""
from __future__ import annotations

import os
from typing import Optional

from app.services.nlp_backends.base import NLPBackend

_backend_instance: Optional[NLPBackend] = None


def _create_backend() -> NLPBackend:
    mode = os.getenv("NLP_BACKEND", "auto").lower().strip()

    if mode == "heuristic":
        from app.services.nlp_backends.heuristic import HeuristicNLPBackend
        print("[NLP] Tryb: heuristic (ustawiony w NLP_BACKEND)")
        return HeuristicNLPBackend()

    if mode == "transformer":
        from app.services.nlp_backends.transformer import TransformerNLPBackend
        print("[NLP] Tryb: transformer (ustawiony w NLP_BACKEND)")
        return TransformerNLPBackend()

    # mode == "auto" — próbuj transformer, fallback na heuristic
    try:
        import transformers  # noqa: F401
        import sentence_transformers  # noqa: F401
        from app.services.nlp_backends.transformer import TransformerNLPBackend
        print("[NLP] Tryb: transformer (wykryto transformers + sentence-transformers)")
        return TransformerNLPBackend()
    except ImportError as e:
        from app.services.nlp_backends.heuristic import HeuristicNLPBackend
        print(f"[NLP] Tryb: heuristic (brak modeli: {e})")
        print("[NLP] Aby włączyć lepszy NLP, zainstaluj:")
        print("[NLP]   pip install transformers torch sentence-transformers")
        print("[NLP]   lub dodaj NLP_BACKEND=transformer do .env")
        return HeuristicNLPBackend()


def get_nlp_backend() -> NLPBackend:
    """Zwraca singleton backendu NLP. Tworzy przy pierwszym wywołaniu."""
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = _create_backend()
    return _backend_instance


def reset_nlp_backend() -> None:
    """Resetuje singleton (przydatne w testach lub po zmianie NLP_BACKEND)."""
    global _backend_instance
    _backend_instance = None
