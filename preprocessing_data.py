from concurrent.futures import ProcessPoolExecutor
import glob
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from config import load_clients

os.makedirs("data", exist_ok=True)

DROP_COLS = {
    "Unnamed: 0",
    "Flow ID",
    "Source IP",
    "Destination IP",
    "Source Port",
    "Timestamp",
    "SimillarHTTP",
}

MAX_WORKERS = 8  # Uses 8 of your 16 threads on Ryzen 7 5800H without spiking RAM


def clean_chunk(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip()
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna()
    return df


def scan_benign_from_file(filepath: str) -> pd.DataFrame:
    collected = []
    for chunk in pd.read_csv(
        filepath,
        chunksize=200_000,
        usecols=lambda c: c.strip() not in DROP_COLS,
        low_memory=False,
    ):
        chunk = clean_chunk(chunk)
        sub = chunk[chunk["Label"] == "BENIGN"]
        if not sub.empty:
            collected.append(sub)
    return pd.concat(collected, ignore_index=True) if collected else pd.DataFrame()


def sample_attack_from_csv(filepath: str, n_samples: int, seed: int = 42) -> pd.DataFrame:
    collected = []
    total = 0
    for chunk in pd.read_csv(
        filepath,
        chunksize=200_000,
        usecols=lambda c: c.strip() not in DROP_COLS,
        low_memory=False,
    ):
        chunk = clean_chunk(chunk)
        sub = chunk[chunk["Label"] != "BENIGN"]
        if not sub.empty:
            collected.append(sub)
            total += len(sub)
            if total >= n_samples * 2:
                break
    combined = pd.concat(collected, ignore_index=True)
    return combined.sample(n=min(n_samples, len(combined)), random_state=seed)


def main() -> None:
    train_files = sorted(glob.glob("training/*.csv"))
    test_files = sorted(glob.glob("testing/*.csv"))

    # 1. Parallel scan across 8 workers to gather ALL BENIGN rows fast
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        train_benign = pd.concat(
            list(pool.map(scan_benign_from_file, train_files)), ignore_index=True
        ).sample(frac=1.0, random_state=42)

        test_benign = pd.concat(
            list(pool.map(scan_benign_from_file, test_files)), ignore_index=True
        ).sample(frac=1.0, random_state=42)

    print(f"Found {len(train_benign)} BENIGN rows in training/, {len(test_benign)} in testing/")

    # Scale client sizes proportionally if fewer than 42,000 BENIGN rows exist
    usable_benign = min(42_000, len(train_benign))
    cfg = load_clients()
    unit = usable_benign // sum(c["weight"] for c in cfg)

    # 2. Build Non-IID, unbalanced clients from clients.json (default 1 : 4 : 16)
    client_specs, start = [], 0
    for i, c in enumerate(cfg):
        n = unit * c["weight"]
        client_specs.append((f"client_{i}", c["attack_file"], n, train_benign.iloc[start : start + n]))
        start += n

    global_test_parts = []
    all_train_features = []

    for cid, csv_path, n_atk, benign_slice in client_specs:
        atk_df = sample_attack_from_csv(csv_path, n_samples=n_atk, seed=42)
        df = pd.concat([atk_df, benign_slice], ignore_index=True).sample(
            frac=1.0, random_state=42
        )
        df["y"] = (df["Label"] != "BENIGN").astype(np.float32)
        df = df.drop(columns=["Label"])

        train_df, temp_df = train_test_split(
            df, test_size=0.2, stratify=df["y"], random_state=42
        )
        val_df, test_df = train_test_split(
            temp_df, test_size=0.5, stratify=temp_df["y"], random_state=42
        )

        train_df.to_parquet(f"data/{cid}_train.parquet", index=False)
        val_df.to_parquet(f"data/{cid}_val.parquet", index=False)
        test_df.to_parquet(f"data/{cid}_test.parquet", index=False)

        all_train_features.append(train_df.drop(columns=["y"]))
        global_test_parts.append(test_df)
        print(f"{cid}: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")

    # 3. Augment Global Test Set with cross-day attacks from testing/
    n_cross_each = min(2_000, len(test_benign) // 2)
    cross_day_syn = sample_attack_from_csv("testing/Syn.csv", n_cross_each, seed=99)
    cross_day_udp = sample_attack_from_csv("testing/UDP.csv", n_cross_each, seed=99)
    cross_day_df = pd.concat(
        [cross_day_syn, cross_day_udp, test_benign.iloc[: n_cross_each * 2]],
        ignore_index=True,
    )
    cross_day_df["y"] = (cross_day_df["Label"] != "BENIGN").astype(np.float32)
    cross_day_df = cross_day_df.drop(columns=["Label"])

    global_test_df = pd.concat(global_test_parts + [cross_day_df], ignore_index=True)
    global_test_df.to_parquet("data/global_test.parquet", index=False)
    print(
        f"Global test set saved -> {len(global_test_df)} rows, "
        f"{global_test_df.shape[1] - 1} features"
    )

    # 4. Fit shared StandardScaler on training features and save
    scaler = StandardScaler()
    scaler.fit(pd.concat(all_train_features, ignore_index=True).values)
    joblib.dump(scaler, "data/scaler.joblib")
    print("Saved data/scaler.joblib")


if __name__ == "__main__":
    main()
