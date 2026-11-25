# Federated Learning for DDoS detection (CIC-DDoS2019)

3 Non-IID clients (SYN : DNS : UDP = 1 : 4 : 16), MLP, FedAvg with Flower.

## Setup
    pip install -r requirements.txt
Download CIC-DDoS2019 CSVs (https://www.unb.ca/cic/datasets/ddos-2019.html) into `training/` and `testing/`.

## Run
    python preprocessing_data.py   # builds data/*.parquet + scaler
    python train_local.py          # local-only baselines -> results/local_metrics.json
    python train_fl.py             # FedAvg -> results/fl_vs_local_comparison.png
