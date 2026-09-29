from __future__ import annotations

import json
from pathlib import Path

from uc_bench.hashing import sha256_file
from uc_bench.v08_repair_snapshot import FIRST_SNAPSHOT_PATH

ROOT = Path(__file__).resolve().parents[1]


def test_first_execution_snapshot_and_raw_case2_result_are_immutable() -> None:
    assert sha256_file(ROOT / FIRST_SNAPSHOT_PATH) == (
        "6e114b0c26dd4be39501c07173c1ea5fb55b907a97d409bf0e643a5837481d93"
    )
    raw = (
        ROOT / "build/hard_suite_v08_runs/v08-gpt-5.6-sol-case_02-20260909T061848Z/run_summary.json"
    )
    assert sha256_file(raw) == ("e9f711b61d99609982499695fd49cdc769d0c6ccc94ad94677d81ec0b2470111")
    value = json.loads(raw.read_text(encoding="utf-8"))
    assert value["partial_scientific_quality"] == 95
    assert value["complete_mission_success"] is False
