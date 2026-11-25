"""Model comparison: MLP vs 1D-CNN vs Random Forest, local-only and federated, 3 seeds each.

Usage: python experiments/models.py [API_URL]   (default http://khang-linux:8000)
Writes experiments/models_results.json and prints mean ± std F1 per test column.
FL runs use the default aggregation (uniform weights), 25 rounds, 2 local epochs.
"""
import json
from pathlib import Path

from common import call, mean_std, run_all

SEEDS = [0, 1, 2]
TRAIN = {"lr": 0.001, "batch_size": 64}
LOCAL = {"mlp": {"epochs": 15, **TRAIN}, "cnn": {"epochs": 15, **TRAIN}, "rf": {}}
FL = {"mlp": {"rounds": 25, "epochs": 2, **TRAIN}, "cnn": {"rounds": 25, "epochs": 2, **TRAIN}}
LABEL = {"mlp": "MLP", "cnn": "1D-CNN", "rf": "Random Forest"}

jobs = [(("local", m, s), {"kind": "local", "model": m, "seed": s, **cfg}) for m, cfg in LOCAL.items() for s in SEEDS]
jobs += [(("fl", m, s), {"kind": "fl", "model": m, "seed": s, **cfg}) for m, cfg in FL.items() for s in SEEDS]
ids = run_all(jobs)

rows, cols = {}, None  # row name -> list of per-seed F1 vectors
for (kind, m, s), rid in ids.items():
    r = call(f"/runs/{rid}")
    if kind == "local":
        for client, v in r["local_metrics"].items():
            rows.setdefault(f"Local {client} · {LABEL[m]}", []).append(v["test_f1"])
    else:
        cols = r["final"]["columns"]
        rows.setdefault(f"Federated · {LABEL[m]}", []).append(r["final"]["f1"])

Path(__file__).with_name("models_results.json").write_text(json.dumps(
    {"columns": cols, "rows": rows, "run_ids": {" | ".join(map(str, k)): v for k, v in ids.items()}}, indent=2))
print("\n| Model | " + " | ".join(cols) + " |\n|---|" + "---|" * len(cols))
for name, vals in rows.items():
    print(f"| {name} | {mean_std(vals)} |")
