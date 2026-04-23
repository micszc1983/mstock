from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SignalVote(BaseModel):
    """Głos pojedynczego systemu (heurystyka lub ML)."""
    source: str                  # "heuristic" | "ml_5d" | "ml_20d" | "ml_thesis"
    source_label: str            # czytelna nazwa
    direction: str               # "up" | "down" | "neutral"
    confidence: float            # 0-100
    probability_up: float        # 0-100
    reasoning: str               # 1-zdaniowe uzasadnienie
    available: bool              # False gdy brak modelu/danych


class EnsembleSignal(BaseModel):
    """Wynik łączenia głosów — tryb ensemble."""
    asset_id: str
    snapshot_at: datetime

    # Tryb aktywny
    mode: str                    # "heuristic" | "ml" | "ensemble_weighted" | "ensemble_majority"
    mode_label: str

    # Głosy osobne
    votes: list[SignalVote]

    # Wynik zbiorczy
    final_direction: str         # "up" | "down" | "neutral"
    final_confidence: float      # 0-100
    final_probability_up: float  # 0-100
    consensus: str               # "pełny" | "częściowy" | "brak" | "n/a"
    consensus_score: float       # 0-1: ile głosów po tej samej stronie

    # Wagi ensemble
    heuristic_weight: float      # 0-1
    ml_weight: float             # 0-1
    weights_dynamic: bool = False         # True gdy wagi obliczone z historii trafności
    weights_method: str = "default"       # "proportional_accuracy" | "default"
    weights_evaluated_records: int = 0   # ile rekordów posłużyło do obliczenia wag

    # Rekomendacja
    action: str                  # "KUP" | "SPRZEDAJ" | "TRZYMAJ"
    rationale: str


class DynamicWeightInfo(BaseModel):
    """Dynamiczne wagi ensemble obliczone z historycznej trafności."""
    asset_id: str
    heuristic_weight: float
    ml_weight: float
    is_dynamic: bool              # False gdy za mało danych — użyto domyślnych wag
    evaluated_records: int        # ile ocenionych rekordów posłużyło do obliczeń
    heuristic_accuracy: float     # historyczna trafność heurystyki (0-1)
    ml_accuracy: float            # historyczna trafność ML (0-1)
    method: str                   # "proportional_accuracy" | "default"
    min_records_required: int     # minimalna liczba rekordów do aktywacji dynamicznych wag


class EnsembleRecord(BaseModel):
    """Historyczny wpis śledzenia wyników ensemble."""
    id: int
    asset_id: str
    created_at: datetime
    mode: str
    heuristic_direction: Optional[str]
    ml_direction: Optional[str]
    ensemble_direction: Optional[str]
    heuristic_confidence: float
    ml_confidence: float
    ensemble_confidence: float
    # Outcome (wypełniany po fakcie przez outcome evaluator)
    actual_return_5d: Optional[float]
    heuristic_correct: Optional[bool]
    ml_correct: Optional[bool]
    ensemble_correct: Optional[bool]
    winner: Optional[str]        # "heuristic" | "ml" | "ensemble" | "tie" | None


class EnsembleLeaderboard(BaseModel):
    """Podsumowanie trafności per aktywo."""
    asset_id: str
    name: str
    total_records: int
    evaluated_records: int        # rekordy z wypełnionym wynikiem (outcome po 5d)
    heuristic_accuracy: float     # % poprawnych predykcji heurystyki (0-1)
    ml_accuracy: float            # % poprawnych predykcji ML (0-1)
    ensemble_accuracy: float      # % poprawnych predykcji ensemble (0-1)
    recommended_mode: str         # tryb z najwyższą historyczną trafnością
    avg_heuristic_confidence: float
    avg_ml_confidence: float
    last_updated: Optional[datetime]


class EnsembleConfig(BaseModel):
    """Konfiguracja trybów ensemble."""
    mode: str                    # "heuristic" | "ml" | "ensemble_weighted" | "ensemble_majority"
    heuristic_weight: float = 0.5
    ml_weight: float = 0.5
    ml_targets: list[str] = ["target_up_5d"]   # które modele ML biorą udział
