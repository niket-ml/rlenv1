#!/usr/bin/env python3
"""Create and immediately verify v0.8 development snapshot 02."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.hashing import sha256_file
from uc_bench.v08_repair_snapshot import (
    SNAPSHOT_02_PATH,
    create_v08_repair_snapshot,
    read_v08_repair_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    created = create_v08_repair_snapshot(ROOT)
    verified = read_v08_repair_snapshot(ROOT)
    if created["hash_set_digest"] != verified["hash_set_digest"]:
        raise AssertionError("Created v0.8 repair snapshot did not verify")
    print(
        json.dumps(
            {
                "path": SNAPSHOT_02_PATH.as_posix(),
                "manifest_sha256": sha256_file(ROOT / SNAPSHOT_02_PATH),
                "hash_set_digest": verified["hash_set_digest"],
                "file_count": verified["file_count"],
                "release_freeze": verified["release_freeze"],
                "api_requests_during_repair": verified["api_requests_during_repair"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
