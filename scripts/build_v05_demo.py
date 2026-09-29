#!/usr/bin/env python3
"""Build an agent-visible v0.5 development start state without revealing answers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.hard_suite_v05 import V05Builder, iter_v05_scenarios

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-id", default="dev5_preprocessing_leakage")
    parser.add_argument("--output-root", type=Path, default=Path("build/v05_demo"))
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    development_ids = {str(row["scenario_id"]) for row in iter_v05_scenarios(PROJECT_ROOT)}
    if args.scenario_id not in development_ids:
        raise SystemExit("Only development scenarios may be built by the public demo command")
    output_root = (PROJECT_ROOT / args.output_root).resolve()
    if PROJECT_ROOT not in output_root.parents:
        raise SystemExit("--output-root must remain inside the project")
    package = V05Builder(PROJECT_ROOT).build(
        args.scenario_id,
        output_root=output_root,
        replace=args.replace,
    )
    print(
        json.dumps(
            {
                "workspace": package.workspace_root.relative_to(PROJECT_ROOT).as_posix(),
                "scenario_id": package.scenario_id,
                "partition": package.partition,
                "validation_outcomes_visible": False,
                "private_answers_visible": False,
                "entrypoint": (package.workspace_root / "TASK.md")
                .relative_to(PROJECT_ROOT)
                .as_posix(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
