#!/usr/bin/env python3
"""Create category-level immutable RC1 release digests."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_release_freeze import create_open_release_freeze


def main() -> None:
    result = create_open_release_freeze(Path("."))
    print(
        json.dumps(
            {
                "status": result["status"],
                "scientific_freeze_digest": result["scientific_freeze_digest"],
                "category_digest_set": result["category_digest_set"],
                "categories": {
                    name: row["digest"] for name, row in result["categories"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
