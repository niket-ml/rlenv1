#!/usr/bin/env python3
"""Build, freeze, or verify the final Case 2 MMMVP package without network access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.case2_mmmvp_v1_release import (
    VALIDATION_PATH,
    build_candidate,
    freeze_release,
    read_release_freeze,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--build", action="store_true")
    modes.add_argument("--freeze", action="store_true")
    modes.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.build:
        result = build_candidate(root)
    elif args.freeze:
        receipt = json.loads((root / VALIDATION_PATH).read_text(encoding="utf-8"))
        result = freeze_release(root, receipt)
    else:
        result = read_release_freeze(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
