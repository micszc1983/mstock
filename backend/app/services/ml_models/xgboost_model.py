"""XGBoost — gradient boosting, najlepszy dla danych tabelarycznych."""
from __future__ import annotations

import joblib
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score


def check_available():
    import xgboost  # noqa — rzuci ImportError jeśli niezainstalowany


def train(
    X_train: list, y_train: list,
    X_test: list,  y_test: list,
    feature_names: list[str],
    model_path: str,
) -> dict:
    from xgboost import XGBClassifier
    import numpy as np

    # Oblicz scale_pos_weight dla niezbalansowanych klas (odpowiednik class_weight='balanced')
    y_arr = np.array(y_train)
    neg = max(1, int((y_arr == 0).sum()))
    pos = max(1, int((y_arr == 1).sum()))
    scale = neg / pos

    model = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )
    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1].tolist()

    # Feature importances (gain-based)
    importances = model.get_booster().get_score(importance_type="gain")
    fi = {feature_names[int(k.replace("f", ""))]: float(v)
          for k, v in importances.items() if k.startswith("f")}

    joblib.dump({"model": model, "feature_names": feature_names}, model_path)
    return {
        "accuracy":  float(accuracy_score(y_test, preds)),
        "precision": float(precision_score(y_test, preds, zero_division=0)),
        "recall":    float(recall_score(y_test, preds, zero_division=0)),
        "f1":        float(f1_score(y_test, preds, zero_division=0)),
        "avg_probability_up": float(sum(probs) / len(probs)) if probs else 0.5,
        "feature_importances": fi,
    }


def predict_proba(model_path: str, X: list) -> float:
    bundle = joblib.load(model_path)
    model = bundle["model"]
    feature_names = bundle["feature_names"]
    row = X[-1]  # użyj ostatniego wiersza (aktualny snapshot)
    x = [[float(row.get(k, 0.0)) if isinstance(row, dict) else float(row[i])
          for i, k in enumerate(feature_names)]]
    return float(model.predict_proba(x)[0][1])
