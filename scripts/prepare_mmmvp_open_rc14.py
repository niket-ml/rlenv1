#!/usr/bin/env python3
"""Create zero-cost RC1.4 disclosure and archived-replay artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc14_audit import (
    replay_archived_submissions,
    write_contract_disclosure_audit,
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    disclosure = write_contract_disclosure_audit(root)
    replay = replay_archived_submissions(root)
    print(
        json.dumps(
            {
                "disclosure": disclosure["status"],
                "archived_replay": replay["status"],
                "api_requests": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
