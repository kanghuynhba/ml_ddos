# Client models: MLP vs 1D-CNN vs Random Forest (2026-11-26)

**Question.** Does a different client model change the picture? (1) Is a stronger classic model such as Random Forest
already good enough locally, making federation unnecessary? (2) Does a 1D-CNN federate better than the MLP?

**Setup.** Same data and clients as `syn_gap_results.md` (SYN : DNS : UDP = 3,200 : 12,800 : 51,200 train samples).
Seeds 0, 1, 2; values are mean ± std of F1.
- Local-only: MLP and 1D-CNN 15 epochs (lr 0.001, batch 64); Random Forest 100 trees.
- Federated: 25 rounds × 2 local epochs, uniform client weighting (the default since the SYN-gap experiment).
  Random Forest is not federated: it has no weights to average.
- 1D-CNN: 2 conv layers (16, 32 filters, kernel 3) over the 80 flow features as one channel, max-pool to 8, then
  32 → 1. About 10k weights vs the MLP's ~7k.

Reproduce: `python experiments/models.py http://<backend>:8000`; raw per-seed numbers in `models_results.json`.

| Model | Test SYN | Test DNS | Test UDP | Shared test |
|---|---|---|---|---|
| Local client 0 (SYN) · MLP | 1.000 ± 0.000 | 0.532 ± 0.433 | 0.911 ± 0.006 | 0.916 ± 0.027 |
| Local client 1 (DNS) · MLP | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.998 ± 0.000 | 0.843 ± 0.000 |
| Local client 2 (UDP) · MLP | 0.454 ± 0.110 | 0.997 ± 0.001 | 0.999 ± 0.000 | 0.927 ± 0.006 |
| Local client 0 (SYN) · 1D-CNN | 1.000 ± 0.000 | 0.000 ± 0.000 | 0.001 ± 0.000 | 0.421 ± 0.000 |
| Local client 1 (DNS) · 1D-CNN | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.997 ± 0.001 | 0.843 ± 0.000 |
| Local client 2 (UDP) · 1D-CNN | 0.536 ± 0.036 | 0.999 ± 0.000 | 0.999 ± 0.001 | 0.942 ± 0.015 |
| Local client 0 (SYN) · Random Forest | 1.000 ± 0.000 | 0.000 ± 0.000 | 0.001 ± 0.000 | 0.116 ± 0.083 |
| Local client 1 (DNS) · Random Forest | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.997 ± 0.000 | 0.844 ± 0.000 |
| Local client 2 (UDP) · Random Forest | 0.206 ± 0.029 | 0.988 ± 0.000 | 1.000 ± 0.000 | 0.851 ± 0.001 |
| **Federated · MLP** | 0.944 ± 0.024 | 1.000 ± 0.000 | 1.000 ± 0.000 | 0.981 ± 0.005 |
| **Federated · 1D-CNN** | **0.988 ± 0.011** | **1.000 ± 0.000** | 0.999 ± 0.000 | **0.988 ± 0.013** |

## Findings

1. **Random Forest does not make federation unnecessary; it generalizes worst.** Every local RF is perfect on its own
   attack and poor on unseen ones (client 0's RF: 0.00 on DNS and UDP, 0.12 on the shared test). Trees memorise
   the thresholds of the attack they saw. The best local RF reaches 0.851 on the shared test, below the best local
   MLP (0.927) and far below either federated model.
2. **The best local-only model of any type** is client 2's 1D-CNN at 0.942 on the shared test. Both federated
   models beat it: MLP 0.981 (+0.039), CNN 0.988 (+0.046), each several times the seed spread.
3. **Federated 1D-CNN is the strongest on SYN** (0.988 vs 0.944 for the MLP; the gap exceeds both spreads).
   On the shared test the CNN's lead over the MLP (+0.007) is within noise (spreads 0.013 and 0.005), so the
   honest claim is "at least as good overall, better on the smallest client".
4. **DNS and UDP reflection floods look alike to every model**: a model trained only on DNS scores ≈ 1.0 on UDP and
   vice versa. The hard case, and where federation earns its keep, is SYN.

## Decision

- **Federated forest is not worth building now.** Its premise was that RF might be much stronger than the MLP; the
  results show the opposite for unseen attacks, and merging trees would also leak each client's split thresholds.
- Keep **MLP as the default** (smaller, already well understood) and report **1D-CNN as the best-performing option**.

## Caveats

- Local client 0's CNN and RF give identical numbers across seeds (± 0.000), i.e. they collapse to "attack only if
  it looks like SYN". That is a real property of training on one attack type, not a seed bug: the MLP rows match
  the SYN-gap experiment exactly for the same seeds, so seeding is reproducible.
- No hyperparameter tuning for any model; RF uses scikit-learn defaults apart from 100 trees.
