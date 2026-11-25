from collections import OrderedDict
import argparse
import json
import os
from flwr.client import ClientApp, NumPyClient
from flwr.common import Context, ndarrays_to_parameters
from flwr.server import ServerApp, ServerAppComponents, ServerConfig
from flwr.server.strategy import FedAvg
from flwr.simulation import run_simulation
import matplotlib.pyplot as plt
import torch
import pyarrow.parquet as pq
from model_utils import ATTACKS, DATA_DIR, NUM_CLIENTS, TEST_COLUMNS, DDoSMLP, evaluate_model, load_parquet_loader, train_epochs

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="results")
ap.add_argument("--rounds", type=int, default=25)
ap.add_argument("--local-epochs", type=int, default=2)
ap.add_argument("--lr", type=float, default=1e-3)
ap.add_argument("--batch-size", type=int, default=64)
ap.add_argument("--mu", type=float, default=0.0, help="FedProx proximal weight; 0 = plain FedAvg")
ap.add_argument("--weighting", choices=["samples", "uniform"], default="samples", help="aggregation weight per client")
ap.add_argument("--seed", type=int, default=None)
ARGS = ap.parse_args() if __name__ == "__main__" else ap.parse_args([])
OUT = ARGS.out
os.makedirs(OUT, exist_ok=True)
if ARGS.seed is not None:
    torch.manual_seed(ARGS.seed)

GLOBAL_TEST_LOADER, INPUT_DIM = load_parquet_loader(f"{DATA_DIR}/global_test.parquet", batch_size=256)
HISTORY = {"round": [], "global_loss": [], "global_f1": []}
NUM_ROUNDS = ARGS.rounds
CLIENTS = {
    i: {
        "id": i, "name": f"client_{i}", "attack": ATTACKS[i], "model": "MLP",
        "train_samples": pq.ParquetFile(f"{DATA_DIR}/client_{i}_train.parquet").metadata.num_rows,
        "rounds": [],
    }
    for i in range(NUM_CLIENTS)
}


def dump(name: str, obj) -> None:
    """Atomic write so the API never reads a half-written file."""
    tmp = f"{OUT}/{name}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, f"{OUT}/{name}")


def get_weights(model: torch.nn.Module):
    return [val.cpu().numpy() for _, val in model.state_dict().items()]


def set_weights(model: torch.nn.Module, parameters):
    params_dict = zip(model.state_dict().keys(), parameters)
    state_dict = OrderedDict({k: torch.tensor(v) for k, v in params_dict})
    model.load_state_dict(state_dict, strict=True)


class DDoSClient(NumPyClient):
    def __init__(self, cid: int):
        self.cid = cid
        self.model = DDoSMLP(INPUT_DIM)
        self.train_loader = None  # built in fit(), once the server has sent batch_size
        self.val_loader, _ = load_parquet_loader(
            f"{DATA_DIR}/client_{cid}_val.parquet", batch_size=256
        )

    def fit(self, parameters, config):
        # hyperparameters come from the server each round (see fit_config), not from this process's argv
        if self.train_loader is None or self.train_loader.batch_size != int(config["batch_size"]):
            self.train_loader, _ = load_parquet_loader(
                f"{DATA_DIR}/client_{self.cid}_train.parquet", batch_size=int(config["batch_size"]), shuffle=True
            )
        if config["seed"] >= 0:
            torch.manual_seed(int(config["seed"]) * 1000 + self.cid * 100 + int(config["round"]))
        set_weights(self.model, parameters)
        loss = train_epochs(self.model, self.train_loader, epochs=int(config["local_epochs"]),
                            lr=float(config["lr"]), prox_mu=float(config["mu"]))
        new = get_weights(self.model)
        metrics = {
            "cid": self.cid, "train_loss": float(loss),
            "bytes_down": int(sum(p.nbytes for p in parameters)), "bytes_up": int(sum(p.nbytes for p in new)),
        }
        return new, len(self.train_loader.dataset), metrics

    def evaluate(self, parameters, config):
        set_weights(self.model, parameters)
        loss, f1 = evaluate_model(self.model, self.val_loader)
        return float(loss), len(self.val_loader.dataset), {"f1": float(f1), "cid": self.cid}


def client_fn(context: Context):
    cid = int(context.node_config["partition-id"])
    return DDoSClient(cid).to_client()


def server_evaluate(server_round: int, parameters, config):
    model = DDoSMLP(INPUT_DIM)
    set_weights(model, parameters)
    loss, f1 = evaluate_model(model, GLOBAL_TEST_LOADER)
    HISTORY["round"].append(server_round)
    HISTORY["global_loss"].append(loss)
    HISTORY["global_f1"].append(f1)
    dump("history.json", HISTORY)
    if server_round == NUM_ROUNDS:
        torch.save(model.state_dict(), f"{OUT}/fedavg_global_model.pt")
        f1s = [evaluate_model(model, load_parquet_loader(f"{DATA_DIR}/client_{i}_test.parquet", 256)[0])[1] for i in range(NUM_CLIENTS)]
        dump("final.json", {"columns": TEST_COLUMNS, "f1": [round(v, 4) for v in f1s + [f1]]})
    return loss, {"global_f1": f1}


class RecordingFedAvg(FedAvg):
    """FedAvg that records per-client metrics and the current phase for the UI."""

    def configure_fit(self, server_round, parameters, client_manager):
        dump("phase.json", {"round": server_round, "state": "training"})
        return super().configure_fit(server_round, parameters, client_manager)

    def aggregate_fit(self, server_round, results, failures):
        for _, res in results:
            m = res.metrics
            CLIENTS[int(m["cid"])]["rounds"].append({
                "round": server_round, "train_loss": m["train_loss"],
                "bytes_down": int(m["bytes_down"]), "bytes_up": int(m["bytes_up"]),
                "num_examples": res.num_examples,
            })
            if ARGS.weighting == "uniform":
                res.num_examples = 1  # every client gets an equal vote in the average
        dump("phase.json", {"round": server_round, "state": "aggregating"})
        return super().aggregate_fit(server_round, results, failures)

    def aggregate_evaluate(self, server_round, results, failures):
        for _, res in results:
            for r in CLIENTS[int(res.metrics["cid"])]["rounds"]:
                if r["round"] == server_round:
                    r["val_f1"] = res.metrics["f1"]
        dump("clients.json", list(CLIENTS.values()))
        dump("phase.json", {"round": server_round, "state": "idle"})
        return super().aggregate_evaluate(server_round, results, failures)


def fit_config(server_round: int) -> dict:
    return {"round": server_round, "local_epochs": ARGS.local_epochs, "lr": ARGS.lr, "batch_size": ARGS.batch_size,
            "mu": ARGS.mu, "seed": -1 if ARGS.seed is None else ARGS.seed}


def server_fn(context: Context):
    init_model = DDoSMLP(INPUT_DIM)
    strategy = RecordingFedAvg(
        fraction_fit=1.0,
        fraction_evaluate=1.0,
        min_fit_clients=NUM_CLIENTS,
        min_evaluate_clients=NUM_CLIENTS,
        min_available_clients=NUM_CLIENTS,
        initial_parameters=ndarrays_to_parameters(get_weights(init_model)),
        evaluate_fn=server_evaluate,
        on_fit_config_fn=fit_config,
    )
    return ServerAppComponents(strategy=strategy, config=ServerConfig(num_rounds=NUM_ROUNDS))


if __name__ == "__main__":
    run_simulation(
        server_app=ServerApp(server_fn=server_fn),
        client_app=ClientApp(client_fn=client_fn),
        num_supernodes=NUM_CLIENTS,
    )

    with open(f"{OUT}/fl_history.json", "w") as f:
        json.dump(HISTORY, f, indent=2)

    if not os.path.exists("results/local_metrics.json"):
        raise SystemExit(0)
    with open("results/local_metrics.json") as f:
        local_metrics = json.load(f)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

    ax1.plot(HISTORY["round"], HISTORY["global_loss"], marker="o", color="tab:red", label="FedAvg Global Loss")
    ax1.set_title("Global Test Loss per FL Round")
    ax1.set_xlabel("Federated Round")
    ax1.set_ylabel("BCE Loss")
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    ax2.plot(HISTORY["round"], HISTORY["global_f1"], marker="o", color="tab:blue", linewidth=2, label="FedAvg Global F1")
    colors = ["tab:orange", "tab:green", "tab:purple"]
    for i, (cname, vals) in enumerate(local_metrics.items()):
        ax2.axhline(
            vals["global_test_f1"],
            linestyle="--",
            color=colors[i % len(colors)],
            label=f"{cname} Local-Only F1 ({vals['global_test_f1']:.2f})",
        )
    ax2.set_title("Global Test F1: FedAvg vs. Local-Only")
    ax2.set_xlabel("Federated Round")
    ax2.set_ylabel("F1 Score")
    ax2.set_ylim(0, 1.05)
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    plt.tight_layout()
    plt.savefig(f"{OUT}/fl_vs_local_comparison.png", dpi=200)
    print("Done! Saved results to " + OUT + "")
