#!/usr/bin/env python3
"""Run and persist the zero-cost open-endedness gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.mmmvp_open_audit import run_open_endedness_audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/mmmvp_open_rc1/open_endedness_audit.json"),
    )
    parser.add_argument(
        "--temporary-root",
        type=Path,
        default=Path("build/mmmvp_open_rc1_local_audit"),
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    temporary = (root / args.temporary_root).resolve()
    if temporary.exists():
        raise SystemExit(f"Refusing to overwrite existing audit directory: {temporary}")
    result = run_open_endedness_audit(root, temporary)
    output = (root / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "api_requests": result["api_requests"],
                "output": output.relative_to(root).as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
