#!/usr/bin/env python3
"""Inspect the zero-cost RC1-to-RC2 successor scope before release gating."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.case2_pilot_v1_rc2_release import rc1_to_rc2_diff


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(rc1_to_rc2_diff(root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
