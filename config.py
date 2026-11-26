"""Where the client list comes from.

v2 data (prep/build.py) writes DATA_DIR/manifest.json; that is the source of truth for clients and features.
Older v1 data has no manifest and uses clients.json (built by preprocessing_data.py).
Client i is always named client_i (DATA_DIR/client_i_*.parquet).
"""
import json
import os
from pathlib import Path


def load_manifest() -> dict | None:
    p = Path(os.environ.get("DATA_DIR", "data")) / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else None


def load_clients() -> list[dict]:
    m = load_manifest()
    if m:  # v2: "attack" is the client's attack types joined, e.g. "Syn+UDPLag"
        return [{"attack": "+".join(c["attacks"]), "attacks": c["attacks"], "label": c.get("label"), "weight": c["weight"]}
                for c in m["clients"]]
    path = os.environ.get("CLIENTS_CONFIG", str(Path(__file__).with_name("clients.json")))
    return json.loads(Path(path).read_text())
