#!/usr/bin/env python3
"""Build deterministic private X17/X31 assets for the open MMMVP release candidate."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_interventions import build_rc_private_assets


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    result = build_rc_private_assets(root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
