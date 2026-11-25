"""SYN-gap experiment: start FL configs x seeds through the API, then summarise /compare F1 per test column.

Usage: python experiments/syn_gap.py [API_URL]   (default http://khang-linux:8000)
Writes experiments/syn_gap_results.json and prints a mean ± std table.
"""
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

API = sys.argv[1] if len(sys.argv) > 1 else "http://khang-linux:8000"
SEEDS = [0, 1, 2]
BASE = {"kind": "fl", "rounds": 25, "epochs": 2, "lr": 0.001, "batch_size": 64}
CONFIGS = {
    "FedAvg (samples, E=2)": {},
    "FedAvg (uniform, E=2)": {"weighting": "uniform"},
    "FedProx mu=0.1 (samples)": {"mu": 0.1},
    "FedAvg (samples, E=1)": {"epochs": 1},
}
PARALLEL = 3


def call(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def run_all(jobs):
    """jobs: list of (key, body). Runs PARALLEL at a time; returns {key: run_id}."""
    ids, queue, active = {}, list(jobs), {}
    while queue or active:
        while queue and len(active) < PARALLEL:
            key, body = queue.pop(0)
            active[key] = ids[key] = call("/runs", body)["id"]
            print("started", key, ids[key], flush=True)
        time.sleep(10)
        for key, rid in list(active.items()):
            status = call(f"/runs/{rid}")["status"]
            if status != "running":
                print(status, key, flush=True)
                del active[key]
    return ids


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
