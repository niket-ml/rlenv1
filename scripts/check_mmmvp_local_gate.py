from __future__ import annotations

import json
import tempfile
from pathlib import Path

from uc_bench.execution_snapshot_03 import read_execution_snapshot_03
from uc_bench.mmmvp_controls import run_mmmvp_controls
from uc_bench.mmmvp_score_sources import validate_score_source_registry


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="uc-mmmvp-controls-") as directory:
        controls = run_mmmvp_controls(root, Path(directory))
    snapshot = read_execution_snapshot_03(root)
    faults = []
    if controls["status"] != "passed" or controls["control_count"] != 35:
        faults.append("thirty_five_control_gate_failed")
    faults.extend(validate_score_source_registry())
    if snapshot.get("release_freeze") is not False:
        faults.append("archived_v08_snapshot_changed")
    value = {
        "schema_version": "uc-bench-mmmvp-local-gate-1",
        "status": "passed" if not faults else "failed",
        "api_requests": 0,
        "api_spend_usd": 0.0,
        "faults": faults,
        "control_summary": controls,
        "archived_v08_snapshot_03_digest": snapshot["hash_set_digest"],
        "archived_v08_preserved": True,
        "scientific_case_or_truth_changes": False,
        "condition_count": 5,
        "score_source_registry_errors": validate_score_source_registry(),
    }
    path = root / "artifacts/mmmvp/local_gate.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(json.dumps({"status": value["status"], "faults": faults}, sort_keys=True))
    if faults:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
