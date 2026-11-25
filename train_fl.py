from collections import OrderedDict
import json
from flwr.client import ClientApp, NumPyClient
from flwr.common import Context, ndarrays_to_parameters
from flwr.server import ServerApp, ServerAppComponents, ServerConfig
from flwr.server.strategy import FedAvg
from flwr.simulation import run_simulation
import matplotlib.pyplot as plt
import torch
from model_utils import DDoSMLP, evaluate_model, load_parquet_loader, train_epochs

GLOBAL_TEST_LOADER, INPUT_DIM = load_parquet_loader("data/global_test.parquet", batch_size=256)
HISTORY = {"round": [], "global_loss": [], "global_f1": []}
NUM_ROUNDS = 25


def get_weights(model: torch.nn.Module):
    return [val.cpu().numpy() for _, val in model.state_dict().items()]


def set_weights(model: torch.nn.Module, parameters):
    params_dict = zip(model.state_dict().keys(), parameters)
    state_dict = OrderedDict({k: torch.tensor(v) for k, v in params_dict})
    model.load_state_dict(state_dict, strict=True)


class DDoSClient(NumPyClient):
    def __init__(self, cid: int):
        self.model = DDoSMLP(INPUT_DIM)
        self.train_loader, _ = load_parquet_loader(
            f"data/client_{cid}_train.parquet", batch_size=64, shuffle=True
        )
        self.val_loader, _ = load_parquet_loader(
            f"data/client_{cid}_val.parquet", batch_size=256
        )

    def fit(self, parameters, config):
        set_weights(self.model, parameters)
        train_epochs(self.model, self.train_loader, epochs=2, lr=1e-3)
        return get_weights(self.model), len(self.train_loader.dataset), {}

    def evaluate(self, parameters, config):
        set_weights(self.model, parameters)
        loss, f1 = evaluate_model(self.model, self.val_loader)
        return float(loss), len(self.val_loader.dataset), {"f1": float(f1)}


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
    if server_round == NUM_ROUNDS:
        torch.save(model.state_dict(), "results/fedavg_global_model.pt")
    return loss, {"global_f1": f1}


def server_fn(context: Context):
    init_model = DDoSMLP(INPUT_DIM)
    strategy = FedAvg(
        fraction_fit=1.0,
        fraction_evaluate=1.0,
        min_fit_clients=3,
        min_evaluate_clients=3,
        min_available_clients=3,
        initial_parameters=ndarrays_to_parameters(get_weights(init_model)),
        evaluate_fn=server_evaluate,
    )
    return ServerAppComponents(strategy=strategy, config=ServerConfig(num_rounds=NUM_ROUNDS))


if __name__ == "__main__":
    run_simulation(
        server_app=ServerApp(server_fn=server_fn),
        client_app=ClientApp(client_fn=client_fn),
        num_supernodes=3,
    )

    with open("results/fl_history.json", "w") as f:
        json.dump(HISTORY, f, indent=2)

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
            color=colors[i],
            label=f"{cname} Local-Only F1 ({vals['global_test_f1']:.2f})",
        )
    ax2.set_title("Global Test F1: FedAvg vs. Local-Only")
    ax2.set_xlabel("Federated Round")
    ax2.set_ylabel("F1 Score")
    ax2.set_ylim(0, 1.05)
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    plt.tight_layout()
    plt.savefig("results/fl_vs_local_comparison.png", dpi=200)
    print("Done! Saved results/fl_vs_local_comparison.png and results/fedavg_global_model.pt")
