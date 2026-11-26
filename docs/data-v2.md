# Data v2: preparing clients

Two stages, so the slow part runs once and client layouts can change cheaply.

| Stage | Command (on khang-linux, from the repo) | Time | Output |
|---|---|---|---|
| 1. Stage raw CSVs | `docker compose --profile prep run --rm prep python -m prep.stage --raw /raw --out /data/stage` | long (reads ~29 GB once) | `data/stage/{train_day,test_day}/<file>_{benign,attack}.parquet`, `stage_manifest.json` |
| 2. Build clients | `docker compose --profile prep run --rm prep python -m prep.build --config datasets/cic2019_v2.json --stage /data/stage --out /data/v2` | seconds | `data/v2/client_<i>_{train,val,test}.parquet`, test sets, `scaler.joblib`, `manifest.json` |

After stage 2, restart the API (`docker compose up -d --build api`). It reads `DATA_DIR=/data/v2`.
Old runs keep their results; the v1 files in `data/` are untouched.

## What stage 1 does

- Reads every CSV in `training/` (capture day 2019-01-12) and `testing/` (2019-03-11) in 200k-row chunks.
- Drops identifier columns (IPs, source port, flow id, timestamp), rows with inf/NaN, and exact duplicates.
- Keeps **all BENIGN rows** (they are scarce: ~57k per day) and a **uniform random sample of attack rows**
  (`--attack-cap`, default 200k per file, sampled over the whole file, not just its start).
- Takes each row's attack type from its own `Label` (`DrDoS_DNS` → `DNS`, `UDP-lag` → `UDPLag`), because some files
  mix attacks. Label counts per file are in `stage_manifest.json`.

## What stage 2 does

1. **Fixed test sets first**, before any client exists, so they don't change when clients change:
   - `test_same_day`: 1,000 rows of every training-day attack type + 8,000 benign.
   - `test_cross_day`: 1,500 rows of every attack type on the second day (incl. **Portmap**, which no client
     trains on) + 10,500 benign from that day.
   - `global_test` = both, with columns `attack` and `day`. This is the shared test set in the dashboard.
2. **Leakage guard:** any training-day row identical to a test row is removed from the client pools.
3. **Clients** from the config: benign pool split by `weight`; attack rows = `attack_ratio` × benign, spread over
   the client's `attacks`. Clients that share an attack type get disjoint rows. Each client is split 80/10/10,
   stratified by attack type.
4. **Federated scaler:** each client contributes only its row count, per-feature sum and sum of squares; the
   combined mean/std is checked to equal a central fit.
5. `manifest.json` records features, clients, sizes, test composition and `unseen_attacks`.

## Adding or changing clients

Edit `datasets/cic2019_v2.json` (or copy it to a new file with a new `version` and `out`) and re-run stage 2 only.

```json
{"name": "client_6", "label": "Trường đại học", "attacks": ["LDAP", "NTP"], "weight": 2, "attack_ratio": 1.0}
```

- `name` must be `client_<i>` with consecutive `i`.
- `attacks`: any type listed under `labels` in `data/stage/stage_manifest.json` for the training day.
- `weight`: share of the benign pool (benign is the limiting resource, ~57k rows in total).
- `attack_ratio`: attack rows per benign row. Above 1 gives more data but unbalances the client.
- If a client needs more attack rows than were staged, stage 2 stops with the numbers; re-stage with a larger
  `--attack-cap`.

## Adding another dataset later

Any new source must produce **the same 80 feature columns** as CICFlowMeter, plus an `attack` label, because every
client's model has the same input layer. Two routes:

1. **Same feature extractor:** run the new pcaps through CICFlowMeter, put the CSVs in a new raw folder, stage
   them with `prep.stage`, and reference the new attack types in a config.
2. **Suricata schema (project goal):** define the feature set computed from Suricata EVE JSON, then write a stage
   step that turns EVE logs into that schema for every node. All clients must then use that schema.

A dataset with different columns (e.g. the per-packet tshark export from the Oulu paper) cannot join the same
federation without such a mapping.

## Resource notes

- Flower runs one process per client (~1 GB RAM each). With 6 clients, run one FL training at a time on the 12 GB
  machine (`EXP_PARALLEL=1 python experiments/models.py`).
