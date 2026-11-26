"""Stage 1 (slow, run once): read every raw CIC-DDoS2019 CSV in chunks and cache it as parquet.

For each file it keeps every BENIGN row and a uniform random sample of attack rows (up to --attack-cap), drops
identifier columns (IPs, ports, flow id, timestamp), removes rows with inf/NaN and exact duplicates, and records the
attack type of each row from its own Label (some files mix several attacks).

Output: <out>/<day>/<file>_{benign,attack}.parquet and <out>/stage_manifest.json.
Build federated clients from the cache with `python -m prep.build`.

    python -m prep.stage --raw /raw --out /data/stage
"""
import argparse
import glob
import json
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

DROP_COLS = {"Unnamed: 0", "Flow ID", "Source IP", "Destination IP", "Source Port", "Timestamp", "SimillarHTTP"}
DAYS = {"training": "train_day", "testing": "test_day"}  # CIC-DDoS2019: 2019-01-12 and 2019-03-11


def attack_type(label: str) -> str:
    """'DrDoS_DNS' -> 'DNS', 'UDP-lag' -> 'UDPLag'; BENIGN stays BENIGN."""
    return label.strip().replace("DrDoS_", "").replace("UDP-lag", "UDPLag")


def count_rows(path: str) -> int:
    return int(subprocess.run(["wc", "-l", path], capture_output=True, text=True, check=True).stdout.split()[0]) - 1


def stage_file(job: tuple) -> dict:
    path, out_dir, cap, seed = job
    total = count_rows(path)
    keep_p = min(1.0, cap * 1.3 / max(total, 1))  # oversample a little: NaN rows and duplicates get dropped
    rng = np.random.default_rng(seed)
    benign, attack, labels = [], [], {}
    for chunk in pd.read_csv(path, chunksize=200_000, low_memory=False,
                             usecols=lambda c: c.strip() not in DROP_COLS):
        chunk.columns = chunk.columns.str.strip()
        chunk = chunk.replace([np.inf, -np.inf], np.nan).dropna()
        chunk["attack"] = chunk.pop("Label").map(attack_type)
        for k, v in chunk["attack"].value_counts().items():
            labels[k] = labels.get(k, 0) + int(v)
        is_benign = chunk["attack"] == "BENIGN"
        benign.append(chunk[is_benign])
        rest = chunk[~is_benign]
        attack.append(rest[rng.random(len(rest)) < keep_p])

    stem = os.path.splitext(os.path.basename(path))[0]
    stats = {"file": path, "raw_rows": total, "labels": labels}
    for kind, parts in (("benign", benign), ("attack", attack)):
        df = pd.concat(parts, ignore_index=True)
        before = len(df)
        df = df.drop_duplicates()
        if kind == "attack" and len(df) > cap:
            df = df.sample(n=cap, random_state=seed)
        df.to_parquet(f"{out_dir}/{stem}_{kind}.parquet", index=False)
        stats[kind] = {"rows": len(df), "duplicates_dropped": before - len(df)}
    print(f"{stem}: benign {stats['benign']['rows']:,}, attack sample {stats['attack']['rows']:,} of {total:,}", flush=True)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=".", help="folder containing training/ and testing/")
    ap.add_argument("--out", default="data/stage")
    ap.add_argument("--attack-cap", type=int, default=200_000, help="max attack rows kept per file")
    ap.add_argument("--workers", type=int, default=4, help="parallel files; each needs ~1-2 GB RAM")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    t0, jobs = time.time(), []
    for raw_dir, day in DAYS.items():
        os.makedirs(f"{args.out}/{day}", exist_ok=True)
        jobs += [(p, f"{args.out}/{day}", args.attack_cap, args.seed) for p in sorted(glob.glob(f"{args.raw}/{raw_dir}/*.csv"))]
    if not jobs:
        raise SystemExit(f"no CSVs under {args.raw}/training or {args.raw}/testing")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        files = list(pool.map(stage_file, jobs))

    first = pd.read_parquet(glob.glob(f"{args.out}/train_day/*_benign.parquet")[0])
    features = [c for c in first.columns if c != "attack"]
    manifest = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "seed": args.seed, "attack_cap": args.attack_cap,
                "features": features, "files": files, "seconds": round(time.time() - t0)}
    with open(f"{args.out}/stage_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"staged {len(files)} files, {len(features)} features in {manifest['seconds']} s -> {args.out}")


if __name__ == "__main__":
    main()
