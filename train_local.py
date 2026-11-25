import json
import os
import torch
from model_utils import DDoSMLP, evaluate_model, load_parquet_loader, train_epochs

os.makedirs("results", exist_ok=True)
global_test_loader, input_dim = load_parquet_loader("data/global_test.parquet", batch_size=256)

local_results = {}
for cid in range(3):
    train_loader, _ = load_parquet_loader(
        f"data/client_{cid}_train.parquet", batch_size=64, shuffle=True
    )
    local_test_loader, _ = load_parquet_loader(
        f"data/client_{cid}_test.parquet", batch_size=256
    )

    model = DDoSMLP(input_dim)
    train_epochs(model, train_loader, epochs=15, lr=1e-3)

    local_loss, local_f1 = evaluate_model(model, local_test_loader)
    global_loss, global_f1 = evaluate_model(model, global_test_loader)

    torch.save(model.state_dict(), f"results/local_client_{cid}.pt")
    local_results[f"client_{cid}"] = {
        "local_test_f1": round(local_f1, 4),
        "global_test_f1": round(global_f1, 4),
        "global_test_loss": round(global_loss, 4),
    }
    print(
        f"Client {cid} Local-Only -> Local Test F1: {local_f1:.4f} | "
        f"Global Test F1: {global_f1:.4f} (Loss: {global_loss:.4f})"
    )

with open("results/local_metrics.json", "w") as f:
    json.dump(local_results, f, indent=2)
