import argparse
import json
import os
import torch
from model_utils import DATA_DIR, NUM_CLIENTS, TEST_COLUMNS, DDoSMLP, evaluate_model, load_parquet_loader, train_epochs

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="results")
ap.add_argument("--epochs", type=int, default=15)
ap.add_argument("--lr", type=float, default=1e-3)
ap.add_argument("--batch-size", type=int, default=64)
ap.add_argument("--seed", type=int, default=None)
ARGS = ap.parse_args()
OUT = ARGS.out
os.makedirs(OUT, exist_ok=True)
if ARGS.seed is not None:
    torch.manual_seed(ARGS.seed)
global_test_loader, input_dim = load_parquet_loader(f"{DATA_DIR}/global_test.parquet", batch_size=256)

test_loaders = [load_parquet_loader(f"{DATA_DIR}/client_{i}_test.parquet", batch_size=256)[0] for i in range(NUM_CLIENTS)]
local_results = {}
for cid in range(NUM_CLIENTS):
    train_loader, _ = load_parquet_loader(
        f"{DATA_DIR}/client_{cid}_train.parquet", batch_size=ARGS.batch_size, shuffle=True
    )
    local_test_loader, _ = load_parquet_loader(
        f"{DATA_DIR}/client_{cid}_test.parquet", batch_size=256
    )

    model = DDoSMLP(input_dim)
    train_epochs(model, train_loader, epochs=ARGS.epochs, lr=ARGS.lr)

    local_loss, local_f1 = evaluate_model(model, local_test_loader)
    global_loss, global_f1 = evaluate_model(model, global_test_loader)

    f1s = [evaluate_model(model, ld)[1] for ld in test_loaders] + [global_f1]
    torch.save(model.state_dict(), f"{OUT}/local_client_{cid}.pt")
    local_results[f"client_{cid}"] = {
        "local_test_f1": round(local_f1, 4),
        "global_test_f1": round(global_f1, 4),
        "global_test_loss": round(global_loss, 4),
        "test_f1": [round(v, 4) for v in f1s],  # order = TEST_COLUMNS
    }
    print(
        f"Client {cid} Local-Only -> Local Test F1: {local_f1:.4f} | "
        f"Global Test F1: {global_f1:.4f} (Loss: {global_loss:.4f})"
    )

with open(f"{OUT}/local_metrics.json", "w") as f:
    json.dump(local_results, f, indent=2)
