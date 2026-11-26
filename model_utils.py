import os

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from config import load_clients, load_manifest
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader, TensorDataset

DATA_DIR = os.environ.get("DATA_DIR", "data")
# torch defaults to one thread per core in every process; parallel runs and Flower's client workers
# then oversubscribe the CPU. 4 threads is plenty for this small MLP.
torch.set_num_threads(int(os.environ.get("TORCH_NUM_THREADS", "4")))
CLIENT_CFG = load_clients()  # clients.json
NUM_CLIENTS = len(CLIENT_CFG)
ATTACKS = [c["attack"] for c in CLIENT_CFG]
TEST_COLUMNS = [f"client_{i}_test" for i in range(NUM_CLIENTS)] + ["global_test"]
SCALER = joblib.load(f"{DATA_DIR}/scaler.joblib")
_MANIFEST = load_manifest()
FEATURES = _MANIFEST["features"] if _MANIFEST else None  # v1 data: every column except y is a feature


def load_xy(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Scaled features and labels as numpy arrays (also used by the sklearn models)."""
    df = pd.read_parquet(path)
    y = df["y"].values.astype(np.float32)
    raw = df[FEATURES] if FEATURES else df.drop(columns=["y"])
    X = SCALER.transform(raw.values.astype(np.float32)).astype(np.float32)
    return X, y


def load_parquet_loader(
    path: str, batch_size: int = 64, shuffle: bool = False
) -> tuple[DataLoader, int]:
    X, y = load_xy(path)
    dataset = TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle), X.shape[1]


class DDoSMLP(nn.Module):
    def __init__(self, input_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


class DDoSCNN(nn.Module):
    """1D-CNN over the flow-feature vector (features as one channel). ~10k weights, close to the MLP's ~7k."""

    def __init__(self, input_dim: int):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(1, 16, kernel_size=3, padding=1), nn.ReLU(),
            nn.Conv1d(16, 32, kernel_size=3, padding=1), nn.ReLU(),
            nn.AdaptiveMaxPool1d(8),
        )
        self.head = nn.Sequential(nn.Flatten(), nn.Linear(32 * 8, 32), nn.ReLU(), nn.Linear(32, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.conv(x.unsqueeze(1))).squeeze(-1)


TORCH_MODELS = {"mlp": DDoSMLP, "cnn": DDoSCNN}
MODEL_LABELS = {"mlp": "MLP", "cnn": "1D-CNN", "rf": "Random Forest"}


def build_model(name: str, input_dim: int) -> nn.Module:
    return TORCH_MODELS[name](input_dim)


def train_epochs(
    model: nn.Module, loader: DataLoader, epochs: int = 3, lr: float = 1e-3, prox_mu: float = 0.0
) -> float:
    """prox_mu > 0 adds the FedProx term mu/2 * ||w - w_start||^2, keeping the client near the global model."""
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    start = [p.detach().clone() for p in model.parameters()] if prox_mu > 0 else None
    model.train()
    last_loss = 0.0
    for _ in range(epochs):
        total_loss, count = 0.0, 0
        for X_batch, y_batch in loader:
            optimizer.zero_grad()
            logits = model(X_batch)
            loss = criterion(logits, y_batch)
            if start is not None:
                prox = sum(((p - s) ** 2).sum() for p, s in zip(model.parameters(), start))
                (loss + prox_mu / 2 * prox).backward()
            else:
                loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(y_batch)
            count += len(y_batch)
        last_loss = total_loss / max(count, 1)
    return last_loss


def detection_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Confusion counts (attack = positive) and the rates an IDS cares about. fpr = false-alarm rate on benign traffic."""
    y_true, y_pred = np.asarray(y_true).astype(int), np.asarray(y_pred).astype(int)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "fpr": fp / (fp + tn) if fp + tn else 0.0,
    }


def rounded(m: dict, nd: int = 4) -> dict:
    return {k: round(v, nd) if isinstance(v, float) else v for k, v in m.items()}


@torch.no_grad()
def evaluate_detailed(model: nn.Module, loader: DataLoader) -> tuple[float, dict]:
    """Mean BCE loss and detection_metrics() at the 0.5 threshold."""
    criterion = nn.BCEWithLogitsLoss()
    model.eval()
    total_loss, count = 0.0, 0
    all_preds, all_targets = [], []
    for X_batch, y_batch in loader:
        logits = model(X_batch)
        loss = criterion(logits, y_batch)
        total_loss += loss.item() * len(y_batch)
        count += len(y_batch)
        preds = (torch.sigmoid(logits) >= 0.5).float()
        all_preds.append(preds.numpy())
        all_targets.append(y_batch.numpy())
    return total_loss / max(count, 1), detection_metrics(np.concatenate(all_targets), np.concatenate(all_preds))


def evaluate_model(model: nn.Module, loader: DataLoader) -> tuple[float, float]:
    loss, m = evaluate_detailed(model, loader)
    return loss, m["f1"]


def per_attack_recall(y_pred: np.ndarray, path: str) -> dict | None:
    """Detection rate per attack type (and false-alarm rate on BENIGN) for a test file with an `attack` column.

    y_pred must be in the file's row order. Returns None for v1 files without the column.
    """
    df = pd.read_parquet(path, columns=None)
    if "attack" not in df:
        return None
    out = {}
    for (attack, day), idx in df.groupby(["attack", df.get("day", pd.Series("", index=df.index))]).groups.items():
        p = np.asarray(y_pred)[idx]
        key = f"{attack}@{day}" if day else attack
        out[key] = {"n": int(len(idx)), "rate": round(float(p.mean()), 4)}  # attack: detection rate; BENIGN: false-alarm rate
    return out


@torch.no_grad()
def predict(model: nn.Module, path: str) -> np.ndarray:
    """0/1 predictions for every row of a parquet file, in file order."""
    model.eval()
    X, _ = load_xy(path)
    return (torch.sigmoid(model(torch.from_numpy(X))) >= 0.5).numpy().astype(int)
