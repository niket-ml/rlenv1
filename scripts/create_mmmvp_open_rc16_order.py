#!/usr/bin/env python3
import json
import secrets
from pathlib import Path

from uc_bench.mmmvp_open_rc15_adapter import load_rc15_launch_routes
from uc_bench.mmmvp_open_rc16_freeze import read_rc16_release_freeze
from uc_bench.mmmvp_open_rc16_order import ORDER_PATH, order_record
from uc_bench.model_runner import _write_json

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    release = read_rc16_release_freeze(root)
    value = order_record(
        list(load_rc15_launch_routes(root)),
        release_infrastructure_digest=release["infrastructure_digest"],
        entropy=secrets.token_bytes(32),
    )
    value["schema_version"] = "uc-bench-open-mmmvp-rc1-6-order-1"
    _write_json(root / ORDER_PATH, value, secret="")
    print(json.dumps(value, indent=2, sort_keys=True))
