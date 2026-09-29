#!/usr/bin/env python3
"""Create the immutable RC1.5 infrastructure freeze."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc15_freeze import create_rc15_release_freeze


def main() -> int:
    value = create_rc15_release_freeze(Path(__file__).resolve().parents[1])
    print(
        json.dumps(
            {
                "status": value["status"],
                "infrastructure_digest": value["infrastructure_digest"],
                "scientific_freeze_digest": value["scientific_freeze_digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
