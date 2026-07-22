"""Kalibracja prawdopodobieństw na osobnym, późniejszym oknie czasowym."""
from __future__ import annotations


def expected_calibration_error(y_true, probabilities, bins: int = 10) -> float:
    import numpy as np

    y = np.asarray(y_true, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    if not len(y):
        return 0.0
    error = 0.0
    edges = np.linspace(0, 1, bins + 1)
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (p >= low) & (p < high if high < 1 else p <= high)
        if mask.any():
            error += float(mask.mean()) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(error)


def calibrate_fitted_model(model, X_cal: list, y_cal: list):
    """Kalibruje bez ponownego uczenia bazowego modelu na późniejszym oknie."""
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.frozen import FrozenEstimator
    from sklearn.metrics import brier_score_loss, log_loss

    class_counts = {label: y_cal.count(label) for label in set(y_cal)}
    if len(X_cal) < 20 or len(class_counts) < 2 or min(class_counts.values()) < 5:
        return model, {
            "calibration_method": "none",
            "calibration_rows": len(X_cal),
            "calibration_reason": "insufficient_class_support",
        }
    raw = model.predict_proba(X_cal)[:, 1]
    method = "isotonic" if len(X_cal) >= 200 else "sigmoid"
    calibrated = CalibratedClassifierCV(FrozenEstimator(model), method=method)
    calibrated.fit(X_cal, y_cal)
    adjusted = calibrated.predict_proba(X_cal)[:, 1]
    return calibrated, {
        "calibration_method": method,
        "calibration_rows": len(X_cal),
        "calibration_brier_before": round(float(brier_score_loss(y_cal, raw)), 6),
        "calibration_brier_after": round(float(brier_score_loss(y_cal, adjusted)), 6),
        "calibration_log_loss": round(float(log_loss(y_cal, adjusted, labels=[0, 1])), 6),
        "calibration_ece": round(expected_calibration_error(y_cal, adjusted), 6),
    }
