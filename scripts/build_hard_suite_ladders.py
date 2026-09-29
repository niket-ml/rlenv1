#!/usr/bin/env python3
"""Build controlled breaking-point ladders without paid model calls."""

from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.hard_suite import (
    HardSuiteBuilder,
    HardSuiteEnvironment,
    grade_hard_suite,
    iter_hard_suite_ladder_variants,
    reference_commitment,
    solve_hard_suite,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory(prefix="uc-hard-ladders-") as directory:
        output_root = Path(directory)
        for variant in iter_hard_suite_ladder_variants(PROJECT_ROOT):
            package = HardSuiteBuilder(PROJECT_ROOT).build(
                variant["variant_id"],
                output_root=output_root,
                partition="ladder",
            )
            environment = HardSuiteEnvironment(package)
            commitment = reference_commitment(package.workspace_root, variant)
            commitment_path = package.workspace_root / "submission" / "commitment.json"
            commitment_path.write_text(json.dumps(commitment, indent=2) + "\n", encoding="utf-8")
            environment.commit_plan()
            environment.reveal_evidence()
            submission = solve_hard_suite(package.workspace_root, variant)
            grade = grade_hard_suite(
                package.workspace_root,
                variant,
                commitment,
                submission,
                commitment_immutable=True,
            )
            rows.append(
                {
                    "ladder_id": variant["ladder_id"],
                    "family_id": variant["family_id"],
                    "variant_id": variant["variant_id"],
                    "parameter": variant["ladder_parameter"],
                    "level": variant["ladder_level"],
                    "expected_decision": submission["decision"],
                    "expected_primary_failure": submission["primary_failure"],
                    "reference_score": grade.score,
                    "package_digest": package.package_digest,
                    "sealed_digest": package.sealed_digest,
                }
            )
    by_ladder: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_ladder[str(row["ladder_id"])].append(row)
    transition_checks = {
        ladder_id: len(
            {
                (str(row["expected_decision"]), str(row["expected_primary_failure"]))
                for row in selected
            }
        )
        >= 2
        for ladder_id, selected in by_ladder.items()
    }
    output = {
        "schema_version": "0.2",
        "generated_at": datetime.now(UTC).isoformat(),
        "paid_model_calls": 0,
        "ladder_count": len(by_ladder),
        "level_count": len(rows),
        "reference_minimum_score": min(row["reference_score"] for row in rows),
        "transition_checks": transition_checks,
        "all_ladders_have_breaking_transition": all(transition_checks.values()),
        "rows": rows,
    }
    path = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_ladders.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "rows"}, indent=2))
    return 0 if output["all_ladders_have_breaking_transition"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
