#!/usr/bin/env python3
"""Create the zero-spend immutable open MMMVP release-candidate freeze."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_freeze import create_open_mmmvp_freeze


def main() -> None:
    result = create_open_mmmvp_freeze(Path("."))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
