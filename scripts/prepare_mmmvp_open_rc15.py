#!/usr/bin/env python3
"""Write zero-cost RC1.5 compatibility and canonical-schema audits."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc15_audit import write_rc15_audits


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    inheritance, inventory = write_rc15_audits(root)
    print(
        json.dumps(
            {
                "compatibility": inheritance["status"],
                "schema_inventory": inventory["status"],
                "api_requests": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
