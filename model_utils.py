import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader, TensorDataset

SCALER = joblib.load("data/scaler.joblib")


def load_parquet_loader(
    path: str, batch_size: int = 64, shuffle: bool = False
) -> tuple[DataLoader, int]:
    df = pd.read_parquet(path)
    y = df["y"].values.astype(np.float32)
    X = df.drop(columns=["y"]).values.astype(np.float32)
    X = SCALER.transform(X).astype(np.float32)
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


def train_epochs(
    model: nn.Module, loader: DataLoader, epochs: int = 3, lr: float = 1e-3
) -> float:
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    model.train()
    last_loss = 0.0
    for _ in range(epochs):
        total_loss, count = 0.0, 0
        for X_batch, y_batch in loader:
            optimizer.zero_grad()
            logits = model(X_batch)
            loss = criterion(logits, y_batch)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(y_batch)
            count += len(y_batch)
        last_loss = total_loss / max(count, 1)
    return last_loss


@torch.no_grad()
def evaluate_model(model: nn.Module, loader: DataLoader) -> tuple[float, float]:
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
    y_pred = np.concatenate(all_preds)
    y_true = np.concatenate(all_targets)
    return total_loss / max(count, 1), float(f1_score(y_true, y_pred, zero_division=0))
