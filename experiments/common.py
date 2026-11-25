"""Helpers shared by the experiment scripts: talk to the backend API and run jobs a few at a time."""
import json
import statistics
import sys
import time
import urllib.request

API = sys.argv[1] if len(sys.argv) > 1 else "http://khang-linux:8000"
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


def mean_std(rows: list[list[float]]) -> str:
    """Column-wise 'mean ± std' cells joined for a markdown row."""
    return " | ".join(f"{statistics.mean(c):.3f} ± {statistics.stdev(c):.3f}" for c in zip(*rows))
