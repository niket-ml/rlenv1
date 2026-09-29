#!/usr/bin/env python3
"""Create the one authorized v0.8 development execution snapshot 03."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.execution_snapshot_03 import create_execution_snapshot_03

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    value = create_execution_snapshot_03(ROOT)
    print(
        json.dumps(
            {
                "status": value["status"],
                "hash_set_digest": value["hash_set_digest"],
                "parent_files_matched": value["parent_snapshot_02"][
                    "matched_parent_file_count"
                ],
                "scientific_cases_changed": value["scientific_cases_changed"],
                "verifier_rules_changed": value["verifier_rules_changed"],
                "release_freeze": value["release_freeze"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
