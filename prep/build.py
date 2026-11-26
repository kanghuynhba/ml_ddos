"""Stage 2 (fast, repeatable): build federated clients and fixed test sets from the staged parquet cache.

Reads a dataset config (e.g. datasets/cic2019_v2.json) and writes <out>/:
  client_<i>_{train,val,test}.parquet   features + y (1 = attack) + attack (type name or BENIGN)
  test_same_day.parquet                 held-out rows from the training day, every attack type
  test_cross_day.parquet                rows from the second capture day (includes attacks no client trains on)
  global_test.parquet                   both test sets together (+ column `day`) -- the shared test set
  scaler.joblib                         StandardScaler combined from per-client statistics (federated)
  manifest.json                         everything above: features, clients, sizes, unseen attacks, checks

The test sets are carved out *before* clients are built, so they stay identical when the client layout changes.
Any training row that is an exact copy of a test row is removed (leakage guard).

    python -m prep.build --config datasets/cic2019_v2.json [--stage data/stage] [--out data/v2]
"""
import argparse
import glob
import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


def load_pool(stage: str, day: str, kind: str) -> pd.DataFrame:
    parts = [pd.read_parquet(p) for p in sorted(glob.glob(f"{stage}/{day}/*_{kind}.parquet"))]
    if not parts:
        raise SystemExit(f"nothing staged under {stage}/{day}; run `python -m prep.stage` first")
    return pd.concat(parts, ignore_index=True).drop_duplicates()


def keys(df: pd.DataFrame, features: list[str]) -> pd.Series:
    return pd.util.hash_pandas_object(df[features], index=False)


def federated_scaler(train_parts: list[pd.DataFrame], features: list[str]) -> StandardScaler:
    """Each client shares only its row count, per-feature sum and sum of squares; the server combines them.

    Equivalent to fitting StandardScaler on all clients' training rows, without any raw row leaving a client.
    """
    n, s, ss = 0, np.zeros(len(features)), np.zeros(len(features))
    for df in train_parts:
        X = df[features].to_numpy(np.float64)
        n, s, ss = n + len(X), s + X.sum(0), ss + (X * X).sum(0)
    mean = s / n
    var = np.maximum(ss / n - mean * mean, 0.0)
    sc = StandardScaler()
    sc.mean_, sc.var_, sc.n_samples_seen_, sc.n_features_in_ = mean, var, n, len(features)
    sc.scale_ = np.where(var > 0, np.sqrt(var), 1.0)  # same convention as sklearn for constant columns
    return sc


def take_test(pool: pd.DataFrame, per_type: int, benign: pd.DataFrame, n_benign: int, seed: int) -> tuple[pd.DataFrame, dict]:
    """per_type attack rows of every type that has enough rows, plus n_benign benign rows."""
    parts, counts = [], {}
    for t, g in pool.groupby("attack"):
        if len(g) >= min(per_type, 100):
            parts.append(g.sample(n=min(per_type, len(g)), random_state=seed))
            counts[t] = len(parts[-1])
    parts.append(benign.sample(n=min(n_benign, len(benign)), random_state=seed))
    counts["BENIGN"] = len(parts[-1])
    return pd.concat(parts, ignore_index=True), counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--stage", help="overrides config 'stage'")
    ap.add_argument("--out", help="overrides config 'out'")
    args = ap.parse_args()
    cfg = json.load(open(args.config))
    stage, out, seed = args.stage or cfg["stage"], args.out or cfg["out"], cfg["seed"]
    features = json.load(open(f"{stage}/stage_manifest.json"))["features"]
    os.makedirs(out, exist_ok=True)
    t0 = time.time()

    # 1. pools (deduplicated across files)
    tr_attack, tr_benign = load_pool(stage, "train_day", "attack"), load_pool(stage, "train_day", "benign")
    te_attack, te_benign = load_pool(stage, "test_day", "attack"), load_pool(stage, "test_day", "benign")

    # 2. fixed test sets, taken before any client exists
    t = cfg["test"]
    same_day, same_counts = take_test(tr_attack, t["same_day_attacks_per_type"], tr_benign, t["same_day_benign"], seed)
    cross_day, cross_counts = take_test(te_attack, t["cross_day_attacks_per_type"], te_benign, t["cross_day_benign"], seed)
    same_day["day"], cross_day["day"] = "train_day", "test_day"
    test_keys = set(keys(same_day, features)) | set(keys(cross_day, features))

    # 3. leakage guard: drop every training-day row that equals a test row
    tr_attack = tr_attack[~keys(tr_attack, features).isin(test_keys)].sample(frac=1, random_state=seed)
    before = len(tr_benign)
    tr_benign = tr_benign[~keys(tr_benign, features).isin(test_keys)].sample(frac=1, random_state=seed)
    leakage_removed = before - len(tr_benign)

    # 4. clients: benign pool split by weight; attack rows = attack_ratio x benign, spread over the client's types
    pools = {a: g for a, g in tr_attack.groupby("attack")}
    cursor = {a: 0 for a in pools}
    total_w = sum(c["weight"] for c in cfg["clients"])
    b_start, clients_meta, train_parts = 0, [], []
    for i, c in enumerate(cfg["clients"]):
        n_b = len(tr_benign) * c["weight"] // total_w
        n_a = round(n_b * c.get("attack_ratio", 1.0))
        per = [n_a // len(c["attacks"]) + (1 if k < n_a % len(c["attacks"]) else 0) for k in range(len(c["attacks"]))]
        parts = [tr_benign.iloc[b_start:b_start + n_b]]
        b_start += n_b
        for a, n in zip(c["attacks"], per):
            if a not in pools:
                raise SystemExit(f"{c['name']}: attack type {a!r} not in staged data (have {sorted(pools)})")
            if cursor[a] + n > len(pools[a]):
                raise SystemExit(f"{c['name']}: needs {n} more {a} rows, only {len(pools[a]) - cursor[a]} left; "
                                 "lower attack_ratio/weights or re-stage with a larger --attack-cap")
            parts.append(pools[a].iloc[cursor[a]:cursor[a] + n])  # disjoint slices: sites never share rows
            cursor[a] += n
        df = pd.concat(parts, ignore_index=True).sample(frac=1, random_state=seed)
        df["y"] = (df["attack"] != "BENIGN").astype(np.float32)
        sp = cfg["split"]
        train, rest = train_test_split(df, train_size=sp["train"], stratify=df["attack"], random_state=seed)
        val, test = train_test_split(rest, test_size=sp["test"] / (sp["val"] + sp["test"]), stratify=rest["attack"], random_state=seed)
        cols = features + ["y", "attack"]
        for name, part in (("train", train), ("val", val), ("test", test)):
            part[cols].to_parquet(f"{out}/{c['name']}_{name}.parquet", index=False)
        train_parts.append(train)
        clients_meta.append({**{k: c[k] for k in ("name", "label", "attacks", "weight")}, "attack_ratio": c.get("attack_ratio", 1.0),
                             "rows": {"train": len(train), "val": len(val), "test": len(test)},
                             "train_by_type": {k: int(v) for k, v in train["attack"].value_counts().items()}})
        print(f"{c['name']} ({'+'.join(c['attacks'])}): train {len(train):,} / val {len(val):,} / test {len(test):,}", flush=True)

    # 5. shared test files
    for df in (same_day, cross_day):
        df["y"] = (df["attack"] != "BENIGN").astype(np.float32)
    same_day[features + ["y", "attack", "day"]].to_parquet(f"{out}/test_same_day.parquet", index=False)
    cross_day[features + ["y", "attack", "day"]].to_parquet(f"{out}/test_cross_day.parquet", index=False)
    pd.concat([same_day, cross_day], ignore_index=True)[features + ["y", "attack", "day"]].to_parquet(f"{out}/global_test.parquet", index=False)

    # 6. federated scaler + self-checks
    scaler = federated_scaler(train_parts, features)
    joblib.dump(scaler, f"{out}/scaler.joblib")
    central = StandardScaler().fit(pd.concat(train_parts)[features].to_numpy(np.float64))
    assert np.allclose(scaler.mean_, central.mean_, rtol=1e-9, atol=1e-6), "federated mean != central mean"
    assert np.allclose(scaler.scale_, central.scale_, rtol=1e-6, atol=1e-6), "federated scale != central scale"
    for p in train_parts:
        assert not keys(p, features).isin(test_keys).any(), "a training row also appears in a test set"
        assert set(p["attack"]) - {"BENIGN"} and (p["attack"] == "BENIGN").any(), "client lacks one of the classes"

    trained = {a for c in cfg["clients"] for a in c["attacks"]}
    manifest = {
        "version": cfg["version"], "description": cfg.get("description", ""), "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": args.config, "seed": seed, "features": features, "scaler": "federated (count, sum, sum of squares per client)",
        "clients": clients_meta,
        "tests": {"same_day": same_counts, "cross_day": cross_counts},
        "unseen_attacks": sorted((set(same_counts) | set(cross_counts)) - trained - {"BENIGN"}),
        "benign_pool": {"train_day_after_tests": len(tr_benign), "used_by_clients": b_start},
        "leakage_removed_benign": leakage_removed,
        "seconds": round(time.time() - t0),
    }
    with open(f"{out}/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"same-day test {sum(same_counts.values()):,} rows, cross-day test {sum(cross_counts.values()):,} rows; "
          f"unseen attacks: {manifest['unseen_attacks']}; checks passed; {manifest['seconds']} s -> {out}")


if __name__ == "__main__":
    main()
