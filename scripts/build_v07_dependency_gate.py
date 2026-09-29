#!/usr/bin/env python3
"""Run and record the ten pre-freeze dependency invariants."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/diagnostics/hard_suite_v07_dependency_gate.json"
TEST_FILE = ROOT / "tests/test_v07_dependency_contract.py"

INVARIANTS = [
    "contaminated analysis cannot pass via a correct final label",
    "post-reveal plan violation retains partial work but cannot validate",
    "one purchase cannot reveal a different resource",
    "precommit correction recovers while post-reveal plan repair is forbidden",
    "one final decision cannot pass both Case 3 returns",
    "wrong patient/site structure cannot pass quantitative execution",
    "claim strength is bounded by the weakest decision-critical evidence",
    "no resource and low-cost confirmation are both accepted in Case 1",
    "a guessed final without evidence receives partial credit only",
    "missing submission changes reliability rather than scientific work quality",
]


def main() -> int:
    environment = dict(os.environ)
    source = str(ROOT / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (source, environment.get("PYTHONPATH")) if value
    )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", str(TEST_FILE), "-q"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    module = ast.parse(TEST_FILE.read_text(encoding="utf-8"))
    collected = [
        node.name
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    passed = completed.returncode == 0 and len(collected) == len(INVARIANTS)
    result = {
        "schema_version": "0.7-dependency-gate-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "invariant_count": len(INVARIANTS),
        "collected_test_names": collected,
        "invariants": [
            {"index": index, "description": description, "passed": passed}
            for index, description in enumerate(INVARIANTS, start=1)
        ],
        "command": [sys.executable, "-m", "pytest", "tests/test_v07_dependency_contract.py", "-q"],
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
