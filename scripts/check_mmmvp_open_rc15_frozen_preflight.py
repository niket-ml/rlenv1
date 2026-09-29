#!/usr/bin/env python3
"""Recompute RC1.5 launch inputs against the immutable freeze without network."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc15_rehearsal import frozen_preflight


def main() -> int:
    value = frozen_preflight(Path(__file__).resolve().parents[1])
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
