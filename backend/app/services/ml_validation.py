"""Podziały czasowe bez przecieku dla nakładających się etykiet tradingowych."""
from __future__ import annotations

from collections.abc import Callable, Sequence


def purged_group_time_series_splits(
    groups: Sequence[object],
    *,
    n_splits: int = 5,
    purge_sessions: int = 20,
    min_train_sessions: int = 60,
) -> list[tuple[list[int], list[int]]]:
    """Expanding-window; jedna sesja nigdy nie trafia do dwóch części foldu."""
    ordered_groups = list(dict.fromkeys(groups))
    if len(ordered_groups) < min_train_sessions + purge_sessions + 20:
        return []
    n_splits = max(2, min(n_splits, 5))
    available = len(ordered_groups) - min_train_sessions - purge_sessions
    test_sessions = max(20, available // n_splits)
    first_test = len(ordered_groups) - test_sessions * n_splits
    splits: list[tuple[list[int], list[int]]] = []
    for fold in range(n_splits):
        test_start = first_test + fold * test_sessions
        test_end = len(ordered_groups) if fold == n_splits - 1 else test_start + test_sessions
        train_end = test_start - purge_sessions
        if train_end < min_train_sessions:
            continue
        train_groups = set(ordered_groups[:train_end])
        test_groups = set(ordered_groups[test_start:test_end])
        train_idx = [index for index, group in enumerate(groups) if group in train_groups]
        test_idx = [index for index, group in enumerate(groups) if group in test_groups]
        if train_idx and test_idx:
            splits.append((train_idx, test_idx))
    return splits


def evaluate_purged_cv(
    X: list,
    y: list,
    groups: Sequence[object],
    model_builder: Callable[[list[int]], object],
    *,
    n_splits: int = 5,
    purge_sessions: int = 20,
) -> dict:
    import numpy as np
    from sklearn.metrics import accuracy_score, f1_score

    splits = purged_group_time_series_splits(
        groups, n_splits=n_splits, purge_sessions=purge_sessions,
    )
    accuracy: list[float] = []
    f1: list[float] = []
    fold_details = []
    for train_idx, test_idx in splits:
        y_train = [y[index] for index in train_idx]
        if len(set(y_train)) < 2:
            continue
        model = model_builder(y_train)
        model.fit([X[index] for index in train_idx], y_train)
        y_test = [y[index] for index in test_idx]
        prediction = model.predict([X[index] for index in test_idx])
        fold_accuracy = float(accuracy_score(y_test, prediction))
        fold_f1 = float(f1_score(y_test, prediction, zero_division=0))
        accuracy.append(fold_accuracy)
        f1.append(fold_f1)
        fold_details.append({
            "train_rows": len(train_idx),
            "test_rows": len(test_idx),
            "train_last_group": str(groups[train_idx[-1]]),
            "test_first_group": str(groups[test_idx[0]]),
            "accuracy": round(fold_accuracy, 6),
            "f1": round(fold_f1, 6),
        })
    if not accuracy:
        return {}
    return {
        "cv_accuracy_mean": round(float(np.mean(accuracy)), 4),
        "cv_accuracy_std": round(float(np.std(accuracy)), 4),
        "cv_f1_mean": round(float(np.mean(f1)), 4),
        "cv_f1_std": round(float(np.std(f1)), 4),
        "cv_folds": len(accuracy),
        "cv_method": "purged_group_time_series",
        "cv_purge_sessions": purge_sessions,
        "cv_fold_details": fold_details,
    }


def combinatorial_purged_splits(
    groups: Sequence[object], *, blocks: int = 6, test_blocks: int = 2,
    purge_sessions: int = 10, max_splits: int = 10,
) -> list[tuple[list[int], list[int]]]:
    """CPCV: kombinacje bloków testowych z purge wokół każdego bloku."""
    from itertools import combinations

    ordered = list(dict.fromkeys(groups))
    if len(ordered) < blocks * 20:
        return []
    block_size = len(ordered) // blocks
    block_ranges = []
    for block in range(blocks):
        start = block * block_size
        end = len(ordered) if block == blocks - 1 else (block + 1) * block_size
        block_ranges.append((start, end))
    splits = []
    for chosen in list(combinations(range(blocks), test_blocks))[:max_splits]:
        test_positions = set()
        excluded = set()
        for block in chosen:
            start, end = block_ranges[block]
            test_positions.update(range(start, end))
            excluded.update(range(max(0, start - purge_sessions), min(len(ordered), end + purge_sessions)))
        train_groups = {ordered[pos] for pos in range(len(ordered)) if pos not in excluded}
        test_groups = {ordered[pos] for pos in test_positions}
        train_idx = [i for i, group in enumerate(groups) if group in train_groups]
        test_idx = [i for i, group in enumerate(groups) if group in test_groups]
        if train_idx and test_idx:
            splits.append((train_idx, test_idx))
    return splits


def evaluate_cpcv(
    X: list, y: list, groups: Sequence[object], model_builder: Callable[[list[int]], object],
    *, purge_sessions: int = 10,
) -> dict:
    import numpy as np
    from sklearn.metrics import f1_score

    scores = []
    for train_idx, test_idx in combinatorial_purged_splits(
        groups, purge_sessions=purge_sessions,
    ):
        y_train = [y[i] for i in train_idx]
        if len(set(y_train)) < 2:
            continue
        model = model_builder(y_train)
        model.fit([X[i] for i in train_idx], y_train)
        prediction = model.predict([X[i] for i in test_idx])
        scores.append(float(f1_score([y[i] for i in test_idx], prediction, zero_division=0)))
    return {
        "cpcv_f1_mean": round(float(np.mean(scores)), 6) if scores else None,
        "cpcv_f1_std": round(float(np.std(scores)), 6) if scores else None,
        "cpcv_paths": len(scores),
        "cpcv_scores": [round(score, 6) for score in scores],
    }


def probability_of_backtest_overfitting(candidate_metrics: list[dict]) -> float | None:
    """Szacuje PBO przez naprzemienne wybieranie championa na połowie ścieżek CV."""
    paths = [metrics.get("cpcv_scores") or [] for metrics in candidate_metrics]
    width = min((len(path) for path in paths), default=0)
    if len(paths) < 2 or width < 4:
        return None
    failures = 0
    trials = 0
    for parity in (0, 1):
        insample = [sum(path[parity:width:2]) for path in paths]
        winner = max(range(len(paths)), key=lambda index: insample[index])
        out_scores = [sum(path[1 - parity:width:2]) for path in paths]
        ordered = sorted(out_scores)
        median = ordered[len(ordered) // 2]
        failures += int(out_scores[winner] < median)
        trials += 1
    return round(failures / trials, 6) if trials else None


def deflated_sharpe_ratio(returns_pct: Sequence[float], trials: int = 3) -> dict:
    """Konserwatywna DSR uwzględniająca skośność, kurtozę i liczbę prób modeli."""
    import math
    from statistics import NormalDist
    import numpy as np

    values = np.asarray(returns_pct, dtype=float) / 100.0
    if len(values) < 3 or float(values.std(ddof=1)) <= 0:
        return {"holdout_sharpe": 0.0, "deflated_sharpe_ratio": 0.0}
    sharpe = float(values.mean() / values.std(ddof=1) * math.sqrt(252.0))
    centered = values - values.mean()
    sigma = float(values.std(ddof=0)) or 1.0
    skew = float(np.mean((centered / sigma) ** 3))
    kurtosis = float(np.mean((centered / sigma) ** 4))
    expected_max = math.sqrt(max(0.0, 2.0 * math.log(max(1, trials))))
    denominator = math.sqrt(max(1e-9, (1 - skew * sharpe + ((kurtosis - 1) / 4) * sharpe ** 2) / (len(values) - 1)))
    probability = NormalDist().cdf((sharpe - expected_max) / denominator)
    return {
        "holdout_sharpe": round(sharpe, 6),
        "deflated_sharpe_ratio": round(float(probability), 6),
        "holdout_skew": round(skew, 6),
        "holdout_kurtosis": round(kurtosis, 6),
    }
