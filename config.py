"""Single source of truth for the clients. Edit clients.json, then re-run preprocessing_data.py.

Client i is always named client_i (data/client_i_*.parquet). `weight` is its relative data size.
"""
import json
import os
from pathlib import Path


def load_clients() -> list[dict]:
    path = os.environ.get("CLIENTS_CONFIG", str(Path(__file__).with_name("clients.json")))
    return json.loads(Path(path).read_text())
