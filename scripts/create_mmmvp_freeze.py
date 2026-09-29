from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_freeze import create_mmmvp_freeze


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    result = create_mmmvp_freeze(root)
    print(
        json.dumps(
            {
                "status": result["status"],
                "file_count": result["file_count"],
                "hash_set_digest": result["hash_set_digest"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
