#!/usr/bin/env python3
"""Create the immutable RC1.4 release freeze."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc14_freeze import create_rc14_release_freeze


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    value = create_rc14_release_freeze(root)
    print(
        json.dumps(
            {
                "status": value["status"],
                "infrastructure_digest": value["infrastructure_digest"],
                "scientific_freeze_digest": value["scientific_freeze_digest"],
                "contract_sha256": value["agent_visible_contract_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
