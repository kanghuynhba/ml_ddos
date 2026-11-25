"""SYN-gap experiment: start FL configs x seeds through the API, then summarise /compare F1 per test column.

Usage: python experiments/syn_gap.py [API_URL]   (default http://khang-linux:8000)
Writes experiments/syn_gap_results.json and prints a mean ± std table.
"""
import json
import statistics
from pathlib import Path

from common import call, run_all
SEEDS = [0, 1, 2]
BASE = {"kind": "fl", "rounds": 25, "epochs": 2, "lr": 0.001, "batch_size": 64}
CONFIGS = {
    "FedAvg (samples, E=2)": {"weighting": "samples"},
    "FedAvg (uniform, E=2)": {"weighting": "uniform"},
    "FedProx mu=0.1 (samples)": {"mu": 0.1, "weighting": "samples"},
    "FedAvg (samples, E=1)": {"epochs": 1, "weighting": "samples"},
}


local_ids = run_all([(s, {"kind": "local", "epochs": 15, "lr": 0.001, "batch_size": 64, "seed": s}) for s in SEEDS])
fl_ids = run_all([((name, s), {**BASE, **cfg, "seed": s}) for name, cfg in CONFIGS.items() for s in SEEDS])

results = {"local": {}, "fl": {}}
for s in SEEDS:
    cmp = call(f"/compare?fl={fl_ids[(next(iter(CONFIGS)), s)]}&local={local_ids[s]}")
    cols = cmp["columns"]
    for row in cmp["rows"][:-1]:
        results["local"].setdefault(row["model"], []).append(row["f1"])
for (name, s), rid in fl_ids.items():
    results["fl"].setdefault(name, []).append(call(f"/runs/{rid}")["final"]["f1"])
results["columns"], results["run_ids"] = cols, {"local": local_ids, "fl": {f"{k[0]} | seed {k[1]}": v for k, v in fl_ids.items()}}
Path(__file__).with_name("syn_gap_results.json").write_text(json.dumps(results, indent=2))


def fmt(rows):
    cells = []
    for i in range(len(cols)):
        vals = [r[i] for r in rows]
        cells.append(f"{statistics.mean(vals):.3f} ± {statistics.stdev(vals):.3f}")
    return " | ".join(cells)


print("\n| Model | " + " | ".join(cols) + " |")
for name, rows in {**results["local"], **results["fl"]}.items():
    print(f"| {name} | {fmt(rows)} |")
