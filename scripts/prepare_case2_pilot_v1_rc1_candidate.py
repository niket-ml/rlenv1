#!/usr/bin/env python3
"""Build the zero-cost, explicitly unfrozen Case 2 RC1 evidence pack."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.case2_pilot_v1_rc1_audit import build_candidate_evidence


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(build_candidate_evidence(root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
