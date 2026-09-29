#!/usr/bin/env python3
"""Create the fresh frozen RC1.5 Case-2 execution order."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc15_order import create_rc15_sentinel_order


def main() -> int:
    value = create_rc15_sentinel_order(Path(__file__).resolve().parents[1])
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
