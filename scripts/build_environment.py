#!/usr/bin/env python3
"""Build both audited UC-Bench agent start states."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.packaging import CONDITIONS, StartStateBuilder

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    output_root = PROJECT_ROOT / "build" / "episodes"
    builder = StartStateBuilder(PROJECT_ROOT)
    packages = [
        builder.build(condition, output_root=output_root, replace=True)
        for condition in CONDITIONS
    ]
    print(
        json.dumps(
            [
                {
                    "condition": package.condition,
                    "workspace_root": str(package.workspace_root),
                    "manifest_path": str(package.manifest_path),
                    "file_count": package.file_count,
                    "package_digest": package.package_digest,
                }
                for package in packages
            ],
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
