"""Job runner API: starts training scripts as subprocesses, exposes status + results."""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import load_clients

RUNS = Path(os.environ.get("RUNS_DIR", "/app/runs"))
RUNS.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="FL DDoS backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])  # lab network only
procs: dict[str, subprocess.Popen] = {}


class RunRequest(BaseModel):
    kind: str = Field(pattern="^(fl|local)$")
    rounds: int = Field(25, ge=1, le=500)          # fl only
    epochs: int = Field(2, ge=1, le=50)             # fl: local epochs per round; local: total epochs
    lr: float = Field(1e-3, gt=0, le=1)
    batch_size: int = Field(64, ge=8, le=4096)
    mu: float = Field(0.0, ge=0, le=10)                       # fl only: FedProx weight, 0 = FedAvg
    weighting: str = Field("uniform", pattern="^(samples|uniform)$")  # fl only; uniform = equal vote per client (see experiments/)
    seed: int | None = Field(None, ge=0, le=2**31 - 1)
    model: str = Field("mlp", pattern="^(mlp|cnn|rf)$")      # rf: local-only (trees can't be weight-averaged)


def _status(run_id: str) -> str:
    p = procs.get(run_id)
    if p is None:  # API restarted: infer from outputs
        d = RUNS / run_id
        return "done" if (d / "fl_history.json").exists() or (d / "local_metrics.json").exists() else "failed"
    rc = p.poll()
    return "running" if rc is None else ("done" if rc == 0 else "failed")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/runs")
def start(req: RunRequest):
    if req.kind == "fl" and req.model == "rf":
        raise HTTPException(422, "Random Forest has no weights to average; use it for local-only runs")
    run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    out = RUNS / run_id
    out.mkdir()
    if req.kind == "fl":
        cmd = [sys.executable, "train_fl.py", "--out", str(out), "--rounds", str(req.rounds),
               "--local-epochs", str(req.epochs), "--lr", str(req.lr), "--batch-size", str(req.batch_size),
               "--mu", str(req.mu), "--weighting", req.weighting]
    else:
        cmd = [sys.executable, "train_local.py", "--out", str(out), "--epochs", str(req.epochs),
               "--lr", str(req.lr), "--batch-size", str(req.batch_size)]
    if req.seed is not None:
        cmd += ["--seed", str(req.seed)]
    cmd += ["--model", req.model]
    (out / "meta.json").write_text(json.dumps({"id": run_id, "config": req.model_dump(), "started": time.time()}))
    procs[run_id] = subprocess.Popen(cmd, stdout=open(out / "log.txt", "w"), stderr=subprocess.STDOUT)
    return {"id": run_id}


def _load(run_id: str) -> dict:
    d = RUNS / run_id
    if not (d / "meta.json").exists():
        raise HTTPException(404, "no such run")
    meta = json.loads((d / "meta.json").read_text())
    meta["status"] = _status(run_id)
    for name, key in (("history.json", "history"), ("local_metrics.json", "local_metrics"),
                      ("clients.json", "clients"), ("phase.json", "phase"), ("final.json", "final")):
        if (d / name).exists():
            try:
                meta[key] = json.loads((d / name).read_text())
            except json.JSONDecodeError:  # file mid-write; next poll gets it
                pass
    return meta


@app.get("/runs")
def list_runs():
    return [_load(p.name) for p in sorted(RUNS.iterdir(), reverse=True) if p.is_dir()]


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    return _load(run_id)


@app.get("/runs/{run_id}/log")
def get_log(run_id: str):
    f = RUNS / run_id / "log.txt"
    if not f.exists():
        raise HTTPException(404)
    return {"log": f.read_text()[-8000:]}


METRICS = ("f1", "precision", "recall", "fpr")


@app.get("/compare")
def compare(fl: str, local: str, metric: str = "f1"):
    """Local-only models vs the federated model on each client's test set and the global test set.

    Each row has "f1" (always) and "values" for the requested metric. Runs made before detailed metrics
    existed have no precision/recall/fpr: their values are null.
    """
    if metric not in METRICS:
        raise HTTPException(422, f"metric must be one of {METRICS}")
    f, l = _load(fl), _load(local)
    if "final" not in f or "local_metrics" not in l:
        raise HTTPException(409, "fl run or local run not finished yet")
    cols = f["final"]["columns"]

    def pick(f1s, detail):
        return f1s if metric == "f1" else [m[metric] for m in detail] if detail else [None] * len(cols)

    rows = [{"model": f"local {k}", "f1": v["test_f1"], "values": pick(v["test_f1"], v.get("test_metrics"))}
            for k, v in l["local_metrics"].items()]
    rows.append({"model": "fedavg", "f1": f["final"]["f1"], "values": pick(f["final"]["f1"], f["final"].get("metrics"))})
    return {"columns": cols, "metric": metric, "rows": rows}


@app.get("/clients")
def clients():
    import pyarrow.parquet as pq
    data = Path(os.environ.get("DATA_DIR", "/data"))
    return [{"id": i, "name": f"client_{i}", "attack": c["attack"], "model": "MLP",
             "train_samples": pq.ParquetFile(data / f"client_{i}_train.parquet").metadata.num_rows}
            for i, c in enumerate(load_clients())]
