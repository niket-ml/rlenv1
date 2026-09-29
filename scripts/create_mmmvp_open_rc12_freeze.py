#!/usr/bin/env python3
"""Create the immutable RC1.2 infrastructure freeze."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc12_freeze import create_rc12_release_freeze


def main() -> int:
    freeze = create_rc12_release_freeze(Path(__file__).resolve().parents[1])
    print(
        json.dumps(
            {
                "status": freeze["status"],
                "scientific_freeze_digest": freeze["scientific_freeze_digest"],
                "infrastructure_digest": freeze["infrastructure_digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
