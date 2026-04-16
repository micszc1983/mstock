"""
LSTM — sieć neuronowa pamietająca sekwencje czasowe.
Wymaga: torch>=2.0.0  (pip install torch --index-url https://download.pytorch.org/whl/cpu)
Aktywuje się automatycznie gdy torch jest zainstalowany.
Sensowny przy >1000 wierszy per aktywo (~4 lata dziennych danych).
"""
from __future__ import annotations

import json
from pathlib import Path
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score


def check_available():
    import torch  # noqa — rzuci ImportError jeśli niezainstalowany


# ── Architektura ──────────────────────────────────────────────────────────────

def _build_model(input_size: int, hidden_size: int = 64, num_layers: int = 2, dropout: float = 0.3):
    import torch.nn as nn

    class LSTMClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                dropout=dropout if num_layers > 1 else 0.0,
                batch_first=True,
            )
            self.dropout = nn.Dropout(dropout)
            self.fc      = nn.Linear(hidden_size, 2)

        def forward(self, x):
            out, _ = self.lstm(x)
            out = self.dropout(out[:, -1, :])  # ostatni krok czasowy
            return self.fc(out)

    return LSTMClassifier()


def _make_sequences(X: list[list[float]], y: list[int], seq_len: int = 20):
    """Zamień płaskie wiersze na sekwencje [seq_len, n_features]."""
    import torch
    Xs, ys = [], []
    for i in range(seq_len, len(X)):
        Xs.append(X[i - seq_len:i])
        ys.append(y[i])
    if not Xs:
        return None, None
    return torch.tensor(Xs, dtype=torch.float32), torch.tensor(ys, dtype=torch.long)


# ── Trening ───────────────────────────────────────────────────────────────────

SEQ_LEN    = 20    # 3 tygodnie danych wejściowych
EPOCHS     = 60
BATCH_SIZE = 32
LR         = 1e-3
MIN_SEQS   = 60    # minimum sekwencji do sensownego treningu


def train(
    X_train: list, y_train: list,
    X_test: list,  y_test: list,
    feature_names: list[str],
    model_path: str,
) -> dict:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    import numpy as np

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Normalizacja
    X_all   = np.array(X_train + X_test, dtype=np.float32)
    mean    = X_all.mean(axis=0)
    std     = X_all.std(axis=0) + 1e-8
    X_tr_n  = ((np.array(X_train, dtype=np.float32) - mean) / std).tolist()
    X_te_n  = ((np.array(X_test,  dtype=np.float32) - mean) / std).tolist()

    X_tr_t, y_tr_t = _make_sequences(X_tr_n, y_train, SEQ_LEN)
    X_te_t, y_te_t = _make_sequences(X_te_n, y_test,  SEQ_LEN)

    if X_tr_t is None or len(X_tr_t) < MIN_SEQS:
        raise ValueError(f"LSTM: za mało sekwencji ({len(X_tr_t) if X_tr_t is not None else 0}/{MIN_SEQS}). Potrzebujesz więcej danych historycznych.")

    n_features = X_tr_t.shape[2]
    model = _build_model(n_features).to(device)

    # Ważenie klas
    y_arr    = np.array(y_train)
    neg, pos = int((y_arr == 0).sum()), int((y_arr == 1).sum())
    weights  = torch.tensor([1.0, neg / max(1, pos)], dtype=torch.float32).to(device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    loader = DataLoader(
        TensorDataset(X_tr_t.to(device), y_tr_t.to(device)),
        batch_size=BATCH_SIZE, shuffle=False,
    )

    best_loss = float("inf")
    patience  = 10
    no_imp    = 0

    model.train()
    for epoch in range(EPOCHS):
        epoch_loss = 0.0
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            epoch_loss += loss.item()
        scheduler.step()

        if epoch_loss < best_loss:
            best_loss = epoch_loss
            no_imp = 0
            torch.save(model.state_dict(), model_path + ".best.pt")
        else:
            no_imp += 1
            if no_imp >= patience:
                break

    # Wczytaj najlepszy checkpoint
    if Path(model_path + ".best.pt").exists():
        model.load_state_dict(torch.load(model_path + ".best.pt", map_location=device))

    # Ewaluacja
    model.eval()
    preds_list, probs_list = [], []
    if X_te_t is not None and len(X_te_t) > 0:
        with torch.no_grad():
            logits = model(X_te_t.to(device))
            probs_t = torch.softmax(logits, dim=1)[:, 1]
            preds_list = (probs_t >= 0.5).long().cpu().tolist()
            probs_list = probs_t.cpu().tolist()
        y_te_list = y_te_t.tolist()
    else:
        y_te_list = []

    # Zapisz model + metadane
    bundle = {
        "state_dict":    model.state_dict(),
        "feature_names": feature_names,
        "n_features":    n_features,
        "mean":          mean.tolist(),
        "std":           std.tolist(),
        "seq_len":       SEQ_LEN,
    }
    import joblib
    joblib.dump(bundle, model_path)

    acc = float(accuracy_score(y_te_list, preds_list)) if preds_list else 0.5
    return {
        "accuracy":           acc,
        "precision":          float(precision_score(y_te_list, preds_list, zero_division=0)) if preds_list else 0.0,
        "recall":             float(recall_score(y_te_list, preds_list, zero_division=0)) if preds_list else 0.0,
        "f1":                 float(f1_score(y_te_list, preds_list, zero_division=0)) if preds_list else 0.0,
        "avg_probability_up": float(sum(probs_list) / len(probs_list)) if probs_list else 0.5,
        "device":             str(device),
        "epochs_trained":     EPOCHS - no_imp,
        "train_sequences":    len(X_tr_t),
    }


# ── Predykcja ─────────────────────────────────────────────────────────────────

def predict_proba(model_path: str, X: list) -> float:
    """X: lista wierszy cech (co najmniej SEQ_LEN wierszy)."""
    import torch
    import numpy as np
    import joblib

    bundle = joblib.load(model_path)
    n_features    = bundle["n_features"]
    feature_names = bundle["feature_names"]
    mean          = np.array(bundle["mean"], dtype=np.float32)
    std           = np.array(bundle["std"],  dtype=np.float32)
    seq_len       = bundle.get("seq_len", SEQ_LEN)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model  = _build_model(n_features).to(device)
    model.load_state_dict(bundle["state_dict"])
    model.eval()

    # Przygotuj sekwencję z ostatnich seq_len wierszy
    rows = X[-seq_len:] if len(X) >= seq_len else X
    if len(rows) < 2:
        return 0.5

    # Normalizuj i zbuduj tensor [1, seq_len, n_features]
    x_raw = []
    for row in rows:
        if isinstance(row, dict):
            x_raw.append([float(row.get(k, 0.0)) for k in feature_names])
        else:
            x_raw.append([float(v) for v in row])

    x_np = (np.array(x_raw, dtype=np.float32) - mean) / std
    x_t  = torch.tensor(x_np, dtype=torch.float32).unsqueeze(0).to(device)  # [1, T, F]

    with torch.no_grad():
        logits = model(x_t)
        prob   = float(torch.softmax(logits, dim=1)[0][1].item())
    return prob
