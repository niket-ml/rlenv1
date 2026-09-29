#!/usr/bin/env python3
import json
from pathlib import Path

from uc_bench.mmmvp_open_rc16_cost import write_rc16_cost_plan
from uc_bench.model_runner import load_openrouter_key

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    value = write_rc16_cost_plan(root, key=load_openrouter_key(root))
    print(json.dumps(value, indent=2, sort_keys=True))
