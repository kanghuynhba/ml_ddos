# SYN-gap experiment (2026-11-26)

**Question.** Plain FedAvg detects SYN floods poorly (F1 ≈ 0.6 on client 0's test set). Client 0 has 16× less data
than client 2, so with sample-weighted averaging it barely influences the global model. Which change fixes that
without hurting the other clients?

**Setup.** CIC-DDoS2019, 3 clients (SYN : DNS : UDP = 3,200 : 12,800 : 51,200 train samples), MLP 64-32-1,
25 rounds, lr 0.001, batch 64. Each configuration run with seeds 0, 1, 2; values are mean ± std of F1.
Local-only baselines: 15 epochs on one client's data, same seeds. Raw per-seed numbers: `syn_gap_results.json`.
Reproduce: `python experiments/syn_gap.py http://<backend>:8000`.

| Model | Test SYN (client 0) | Test DNS (client 1) | Test UDP (client 2) | Shared test |
|---|---|---|---|---|
| Local-only client 0 (SYN) | 1.000 ± 0.000 | 0.532 ± 0.433 | 0.911 ± 0.006 | 0.916 ± 0.027 |
| Local-only client 1 (DNS) | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.998 ± 0.000 | 0.843 ± 0.000 |
| Local-only client 2 (UDP) | 0.454 ± 0.110 | 0.997 ± 0.001 | 0.999 ± 0.000 | 0.927 ± 0.006 |
| FedAvg, sample-weighted, E=2 (baseline) | 0.614 ± 0.020 | 0.999 ± 0.001 | 1.000 ± 0.000 | 0.930 ± 0.005 |
| **FedAvg, uniform weights, E=2** | **0.945 ± 0.042** | **1.000 ± 0.000** | **1.000 ± 0.000** | **0.980 ± 0.006** |
| FedProx μ=0.1, sample-weighted | 0.817 ± 0.134 | 0.999 ± 0.000 | 0.997 ± 0.000 | 0.954 ± 0.008 |
| FedAvg, sample-weighted, E=1 | 0.556 ± 0.104 | 1.000 ± 0.000 | 1.000 ± 0.000 | 0.930 ± 0.010 |

## Findings

1. **Local-only models fail on attacks they never saw.** The DNS client's model detects 0 % of SYN floods; the UDP
   client's model ≈ 45 %. This is the core motivation for federated learning.
2. **The SYN gap comes from the aggregation weights, not from client drift.** Giving every client an equal vote
   (uniform weighting) lifts SYN F1 from 0.61 to 0.95 and the shared-test F1 from 0.930 to 0.980, with DNS/UDP
   unchanged at ≈ 1.0. All three uniform seeds beat all three baseline seeds on both columns, so this is well
   outside run-to-run noise.
3. **FedProx helps partly but is unstable** (SYN 0.82 ± 0.13: 0.96, 0.81, 0.69 across seeds).
   **Fewer local epochs does not help** (0.56 ± 0.10). Both target client drift, which is not the main problem here.
4. **The federated model now clearly beats every local-only model** on the shared test set: 0.980 vs the best
   local 0.927 (+0.053, ≈ 9× the seed spread). With sample weighting the margin was only +0.003, within noise.

## Caveats

- Uniform weighting gives a small client as much influence as a large one. That is fair to small sites, but a
  compromised small node could also poison the model more easily. Worth pairing with a robust aggregator
  (trimmed mean / median) in the poisoning experiment.
- 3 seeds is a minimum; local-only client 0 on the DNS test (0.53 ± 0.43) shows how unstable a single run can be.
- One dataset, one model size, 3 clients. Not yet repeated on Suricata-derived features.
