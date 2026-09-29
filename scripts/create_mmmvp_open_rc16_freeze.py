#!/usr/bin/env python3
import json
from pathlib import Path

from uc_bench.mmmvp_open_rc16_freeze import create_rc16_release_freeze

if __name__ == "__main__":
    value = create_rc16_release_freeze(Path(__file__).resolve().parents[1])
    print(json.dumps(value, indent=2, sort_keys=True))
