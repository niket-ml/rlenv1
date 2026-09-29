#!/usr/bin/env python3
"""Run the complete zero-cost RC1.5 pre-freeze launch gate."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc14_freeze import read_rc14_release_freeze
from uc_bench.mmmvp_open_rc15_adapter import (
    load_rc15_all_routes,
    load_rc15_launch_routes,
)
from uc_bench.mmmvp_open_rc15_audit import (
    INHERITANCE_PATH,
    RC14_FREEZE_SHA256,
    SCHEMA_INVENTORY_PATH,
)
from uc_bench.mmmvp_open_rc15_cost import calculate_rc15_cost_plan
from uc_bench.mmmvp_open_rc15_guard import (
    FrozenByteSnapshot,
    run_preserving_frozen_files,
)
from uc_bench.mmmvp_open_rc15_rehearsal import PREFREEZE_REHEARSAL_PATH
from uc_bench.mmmvp_open_runner import OpenRunConfig, production_request

TARGET = Path("artifacts/mmmvp_open_rc15/pre_exposure_gate.json")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / TARGET
    if target.exists():
        raise SystemExit("RC1.5 pre-exposure gate already exists")
    scientific = read_open_mmmvp_freeze(root)
    rc14_before = read_rc14_release_freeze(root)
    rc14_snapshot = FrozenByteSnapshot.capture(
        root, rc14_before["infrastructure_hashes"]
    )
    rc14_freeze_before = sha256_file(
        root / "artifacts/mmmvp_open_rc14/release_freeze.json"
    )
    identity_before = compatibility_identity(root)
    inheritance = json.loads((root / INHERITANCE_PATH).read_text())
    inventory = json.loads((root / SCHEMA_INVENTORY_PATH).read_text())
    rehearsal = json.loads((root / PREFREEZE_REHEARSAL_PATH).read_text())
    cost = calculate_rc15_cost_plan(root)
    all_routes = load_rc15_all_routes(root)
    compatible = load_rc15_launch_routes(root)
    commands = [
        run_preserving_frozen_files(
            root,
            ["./.venv/bin/python", "-m", "pytest", "-q", "tests/test_mmmvp_open_rc15.py"],
            rc14_snapshot,
        ),
        run_preserving_frozen_files(
            root,
            ["./.venv/bin/ruff", "check", "src", "tests", "scripts"],
            rc14_snapshot,
        ),
        run_preserving_frozen_files(
            root,
            [
                "./.venv/bin/python",
                "-m",
                "pytest",
                "-q",
                "--ignore=tests/test_mmmvp_open_rc14.py",
            ],
            rc14_snapshot,
        ),
        run_preserving_frozen_files(
            root,
            ["./.venv/bin/python", "-m", "pytest", "-q", "tests/test_mmmvp_open_rc14.py"],
            rc14_snapshot,
        ),
        run_preserving_frozen_files(
            root,
            ["./.venv/bin/python", "-m", "uc_bench", "doctor"],
            rc14_snapshot,
        ),
        run_preserving_frozen_files(
            root,
            ["./.venv/bin/python", "scripts/project_status.py", "--check"],
            rc14_snapshot,
        ),
        run_preserving_frozen_files(
            root,
            ["./.venv/bin/python", "scripts/run_docker_preflight.py"],
            rc14_snapshot,
        ),
        run_preserving_frozen_files(
            root,
            ["./.venv/bin/python", "scripts/run_mmmvp_open_rc12_docker_preflight.py"],
            rc14_snapshot,
        ),
    ]
    rc14_after = read_rc14_release_freeze(root)
    identity_after = compatibility_identity(root)
    rc14_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc14_release.json").read_text()
    )
    rc15_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc15_release.json").read_text()
    )
    invariants = {
        "rc14_freeze_byte_identical": rc14_freeze_before
        == RC14_FREEZE_SHA256
        == sha256_file(root / "artifacts/mmmvp_open_rc14/release_freeze.json"),
        "rc14_release_valid_and_unchanged": rc14_before == rc14_after,
        "scientific_freeze_unchanged": scientific["hash_set_digest"]
        == "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c",
        "request_and_tool_hashes_unchanged": identity_before == identity_after,
        "scientific_episode_config_unchanged": rc14_config["scientific_episode"]
        == rc15_config["scientific_episode"],
        "compatibility_inherited_without_calls": inheritance["status"] == "passed"
        and inheritance["new_compatibility_requests"] == 0,
        "canonical_schema_inventory_passed": inventory["status"] == "passed",
        "all_ten_routes_parse_canonically": len(all_routes) == 10,
        "only_nine_compatible_routes_costed": len(compatible) == 9
        and set(cost["excluded_routes"]) == {"z-ai/glm-5.2"},
        "nested_price_sources_recorded": all(
            row["price_source_fields"]
            == [
                "maximum_route_price_usd_per_million.prompt",
                "maximum_route_price_usd_per_million.completion",
            ]
            for row in cost["observations"]
        ),
        "two_cost_calculations_agree": cost["independent_calculations_agree"],
        "cost_distribution_within_cap": cost["sentinel_no_cache_p90_usd"]
        <= cost["scientific_hard_cap_usd"],
        "full_production_rehearsal_passed": rehearsal["status"] == "passed"
        and rehearsal["valid_fake_submission"] is True,
        "rehearsal_request_matches_frozen_science": rehearsal[
            "production_request_sha256"
        ]
        == canonical_sha256(
            production_request(
                OpenRunConfig("gate", next(iter(compatible)), "case_02")
            )
        ),
        "rehearsal_interruption_restart_passed": all(
            rehearsal["interruption_restart"].get(field)
            for field in ("reopened", "verification_passed", "messages_exact", "state_exact")
        ),
        "no_scientific_or_external_requests": rehearsal["api_requests"] == 0
        and cost["api_requests"] == 0,
        "frozen_predecessor_restored_after_every_command": all(
            row["frozen_predecessor_restored_and_verified"] for row in commands
        ),
        "full_repository_tests_covered": any(
            "--ignore=tests/test_mmmvp_open_rc14.py" in row["command"]
            for row in commands
        )
        and any(
            row["command"][-1] == "tests/test_mmmvp_open_rc14.py"
            for row in commands
        ),
    }
    passed = all(row["passed"] for row in commands) and all(invariants.values())
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-5-pre-exposure-gate-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "api_requests": 0,
        "scientific_requests": 0,
        "compatibility_requests": 0,
        "commands": commands,
        "invariants": invariants,
        "offline_cost_summary": {
            "median_usd": cost["sentinel_no_cache_median_usd"],
            "p90_usd": cost["sentinel_no_cache_p90_usd"],
            "p95_usd": cost["sentinel_no_cache_p95_usd"],
            "hard_cap_usd": cost["scientific_hard_cap_usd"],
        },
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "rc14_infrastructure_digest": rc14_after["infrastructure_digest"],
        "rc14_freeze_sha256": rc14_freeze_before,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(target)
    print(
        json.dumps(
            {
                "status": value["status"],
                "api_requests": 0,
                "p90_usd": cost["sentinel_no_cache_p90_usd"],
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
