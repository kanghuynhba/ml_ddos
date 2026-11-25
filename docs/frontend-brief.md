# Frontend brief

## What this is
A web UI for a lab-report **demo** of federated learning (FL) for DDoS detection on CIC-DDoS2019.
Goal: someone watching should *see* the idea and *see how well the model works for every client*.

- 3 clients with different attack data (non-IID): Client 0 = SYN flood (1x data), Client 1 = DNS DrDoS (4x), Client 2 = UDP DrDoS (16x).
- A central server runs FedAvg: it sends the global model to clients, each client trains on its own data, sends back only weights, the server averages them (by default every client gets an equal vote; sample-count weighting is an option, see `experiments/syn_gap_results.md`).
- Raw traffic never leaves a client. That is the privacy point of the demo.
- The comparison that matters: **local-only models** (each trained on one client's data) vs the **federated central model**, on each client's test set and on the global test set (which includes attacks a single client never saw).

## Where things run
- Backend: Docker container on the Linux machine (data lives there). Frontend runs on the Mac and calls it at `VITE_API_URL` (see `frontend/.env`, currently `http://khang-linux:8000`).
- Contract between the two: `docs/api-contract.md`. Build against that. Do not edit backend files (`api/`, `*.py` in the repo root).

## Main screen
Open `docs/mockup/fl-flow-mockup.html` in a browser (fake numbers, press Start). It shows:
1. **Topology panel**: server on top, client cards below. On each round: weights fly down (blue), clients light up while training (orange), updates fly back up (orange), server flashes while averaging, round counter and global F1 update.
2. **Central model card**: big global F1 number plus F1-per-round line chart.
3. **Per-round traffic table**: KB sent and received per client.
4. **Local vs Federated table**: rows = local-only models and the FedAvg model, columns = each client's test set and the global test set.
5. Tabs for later: Per client (curve, confusion matrix), Convergence, Comm cost, Runs (compare runs).

The animation should be driven by the real round events from the API, not a timer. While a run is in progress, poll the run and animate each new round as its data arrives.

## Run controls
Start-run form: kind (fl or local), rounds, local epochs, learning rate, batch size. Later: strategy (FedAvg/FedProx), and per-client settings.

## Planned later (design for it)
- More clients: the UI must render N clients from the API, not a hardcoded 3.
- Each client can have its own model type. The API carries a `model` field per client. FedAvg needs the same architecture on all clients, so for now every client reports `MLP`; the backend plan for different models is a shared body with a personal head.
- Fine-tuning on clients and server: run configs are stored per run so runs can be compared.
