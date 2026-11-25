# API contract (backend ⇄ frontend)

Base URL: `VITE_API_URL`. JSON everywhere. CORS is open (lab network only).
**Status legend:** ✅ exists now, 🔜 planned (backend session builds it; frontend may code against it).

## ✅ `GET /health` → `{"ok": true}`

## ✅ `POST /runs`
Body: `{"kind": "fl" | "local", "rounds": 25, "epochs": 2, "lr": 0.001, "batch_size": 64}`
(`epochs` = local epochs per round for `fl`, total epochs for `local`.) Returns `{"id": "<run_id>"}`.
Optional ✅: `"mu": 0.0` (fl: FedProx weight, 0 = FedAvg), `"weighting": "uniform" | "samples"` (fl: aggregation weight per client, default `uniform`; runs created before 2026-11-26 have no field and used `samples`), `"seed": 42` (fl and local). All are echoed back in `config`.

## ✅ `GET /runs` and `GET /runs/{id}`
```json
{
  "id": "20261125-161926-f528",
  "status": "running | done | failed",
  "config": {"kind": "fl", "rounds": 2, "epochs": 1, "lr": 0.001, "batch_size": 64},
  "started": 1764087566.1,
  "history": {"round": [0,1,2], "global_loss": [..], "global_f1": [..]},   // fl only; round 0 = untrained model
  "local_metrics": {"client_0": {"local_test_f1": 0.97, "global_test_f1": 0.52, "global_test_loss": 0.9}}  // local only
}
```
`GET /runs/{id}/log` → `{"log": "<last 8000 chars>"}`.

## ✅ `GET /runs/{id}` additions (per-client data)
Added to the run object, fl runs, one entry per completed round (index aligns with `history.round`, round 0 omitted):
```json
"clients": [
  {"id": 0, "name": "client_0", "attack": "SYN", "model": "MLP", "train_samples": 3000,
   "rounds": [
     {"round": 1, "train_loss": 0.31, "val_f1": 0.88, "bytes_down": 32361, "bytes_up": 32361}
   ]}
],
"phase": {"round": 3, "state": "training | aggregating | idle"}
```
`phase` is for driving the animation live (`training` while clients fit and download weights, `aggregating` while the server averages, `idle` after the round is evaluated). `final` = `{"columns": [...], "f1": [...]}` appears when the fl run finishes (FedAvg F1 on each client test set + global test). The frontend may also animate purely from new rounds appearing.

## ✅ Comparison block (when both a local run and an fl run exist)
`GET /compare?fl=<run_id>&local=<run_id>`:
```json
{"columns": ["client_0_test","client_1_test","client_2_test","global_test"],
 "rows": [{"model": "local client_0", "f1": [0.97,0.41,0.38,0.52]},
          {"model": "fedavg", "f1": [0.97,0.96,0.98,0.95]}]}
```

## ✅ `GET /clients`
List of configured clients (id, name, attack, sample count, model) so the topology renders N clients.

Rule: if the frontend needs something not listed here, ask for a contract change first. Do not parse `log.txt`.
