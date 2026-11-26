import argparse
import json
import os
import joblib
import torch
from sklearn.ensemble import RandomForestClassifier
from model_utils import DATA_DIR, NUM_CLIENTS, TEST_COLUMNS, build_model, detection_metrics, evaluate_detailed, load_parquet_loader, load_xy, per_attack_recall, predict, rounded, train_epochs

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="results")
ap.add_argument("--epochs", type=int, default=15)
ap.add_argument("--lr", type=float, default=1e-3)
ap.add_argument("--batch-size", type=int, default=64)
ap.add_argument("--seed", type=int, default=None)
ap.add_argument("--model", choices=["mlp", "cnn", "rf"], default="mlp")
ap.add_argument("--trees", type=int, default=100, help="rf only")
ARGS = ap.parse_args()
OUT = ARGS.out
os.makedirs(OUT, exist_ok=True)
if ARGS.seed is not None:
    torch.manual_seed(ARGS.seed)
GLOBAL_PATH = f"{DATA_DIR}/global_test.parquet"
global_test_loader, input_dim = load_parquet_loader(GLOBAL_PATH, batch_size=256)

test_loaders = [load_parquet_loader(f"{DATA_DIR}/client_{i}_test.parquet", batch_size=256)[0] for i in range(NUM_CLIENTS)]
local_results = {}


def run_rf(cid: int) -> dict:
    """Random Forest baseline: no epochs/lr/batch, just fit on the client's data."""
    X, y = load_xy(f"{DATA_DIR}/client_{cid}_train.parquet")
    rf = RandomForestClassifier(n_estimators=ARGS.trees, n_jobs=4, random_state=ARGS.seed).fit(X, y)
    joblib.dump(rf, f"{OUT}/local_client_{cid}_rf.joblib")
    paths = [f"{DATA_DIR}/client_{i}_test.parquet" for i in range(NUM_CLIENTS)] + [f"{DATA_DIR}/global_test.parquet"]
    ms = [rounded(detection_metrics(yt, rf.predict(Xt))) for Xt, yt in map(load_xy, paths)]
    return {"local_test_f1": ms[cid]["f1"], "global_test_f1": ms[-1]["f1"], "global_test_loss": None,
            "test_f1": [m["f1"] for m in ms], "test_metrics": ms,
            "per_attack": per_attack_recall(rf.predict(load_xy(paths[-1])[0]), paths[-1])}


for cid in range(NUM_CLIENTS):
    if ARGS.model == "rf":
        local_results[f"client_{cid}"] = r = run_rf(cid)
        print(f"Client {cid} RF Local-Only -> Local Test F1: {r['local_test_f1']:.4f} | Global Test F1: {r['global_test_f1']:.4f}")
        continue
    train_loader, _ = load_parquet_loader(
        f"{DATA_DIR}/client_{cid}_train.parquet", batch_size=ARGS.batch_size, shuffle=True
    )

    model = build_model(ARGS.model, input_dim)
    train_epochs(model, train_loader, epochs=ARGS.epochs, lr=ARGS.lr)

    global_loss, gm = evaluate_detailed(model, global_test_loader)
    ms = [rounded(evaluate_detailed(model, ld)[1]) for ld in test_loaders] + [rounded(gm)]  # order = TEST_COLUMNS
    local_f1, global_f1 = ms[cid]["f1"], ms[-1]["f1"]
    torch.save(model.state_dict(), f"{OUT}/local_client_{cid}.pt")
    local_results[f"client_{cid}"] = {
        "local_test_f1": local_f1,
        "global_test_f1": global_f1,
        "global_test_loss": round(global_loss, 4),
        "test_f1": [m["f1"] for m in ms],
        "test_metrics": ms,
        "per_attack": per_attack_recall(predict(model, GLOBAL_PATH), GLOBAL_PATH),
    }
    print(
        f"Client {cid} Local-Only -> Local Test F1: {local_f1:.4f} | "
        f"Global Test F1: {global_f1:.4f} (Loss: {global_loss:.4f})"
    )

with open(f"{OUT}/local_metrics.json", "w") as f:
    json.dump(local_results, f, indent=2)
