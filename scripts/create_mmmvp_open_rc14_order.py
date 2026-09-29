#!/usr/bin/env python3
"""Create the one-time RC1.4 sentinel order before freezing."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc14_order import create_rc14_sentinel_order


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    value = create_rc14_sentinel_order(root)
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
