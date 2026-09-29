#!/usr/bin/env python3
"""Run the zero-network, full production-path RC1.5 rehearsal."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc15_rehearsal import run_prefreeze_rehearsal


def main() -> int:
    result = run_prefreeze_rehearsal(Path(__file__).resolve().parents[1])
    print(
        json.dumps(
            {
                "status": result["status"],
                "fake_provider_requests": result["fake_provider_requests"],
                "valid_fake_submission": result["valid_fake_submission"],
                "api_requests": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
