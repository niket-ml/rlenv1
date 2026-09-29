from __future__ import annotations

import ast
import copy
import inspect
import json
import sys
from pathlib import Path

import pytest

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import sha256_file
from uc_bench.mmmvp_open_rc13_cost import calculate_rc13_cost_plan
from uc_bench.mmmvp_open_rc15_adapter import (
    CanonicalLaunchRoute,
    load_rc15_all_routes,
    load_rc15_launch_routes,
)
from uc_bench.mmmvp_open_rc15_audit import (
    RC14_FREEZE_SHA256,
    compatibility_inheritance,
    schema_parsing_inventory,
)
from uc_bench.mmmvp_open_rc15_cost import calculate_rc15_cost_plan
from uc_bench.mmmvp_open_rc15_guard import (
    FrozenByteSnapshot,
    run_preserving_frozen_files,
)
from uc_bench.mmmvp_open_rc15_order import order_record
from uc_bench.mmmvp_open_rc15_sentinel import rc15_global_stop_faults

ROOT = Path(__file__).resolve().parents[1]


def _serialized_adapter() -> dict[str, object]:
    return next(iter(load_rc15_all_routes(ROOT).values())).adapter.to_dict()


def test_rc14_is_preserved_byte_for_byte() -> None:
    assert sha256_file(
        ROOT / "artifacts/mmmvp_open_rc14/release_freeze.json"
    ) == RC14_FREEZE_SHA256


def test_all_routes_parse_once_and_only_technical_passes_launch() -> None:
    all_routes = load_rc15_all_routes(ROOT)
    compatible = load_rc15_launch_routes(ROOT)
    assert len(all_routes) == 10
    assert len(compatible) == 9
    assert set(all_routes) - set(compatible) == {"z-ai/glm-5.2"}
    for route in all_routes.values():
        assert route.price_source_fields == (
            "maximum_route_price_usd_per_million.prompt",
            "maximum_route_price_usd_per_million.completion",
        )
        assert route.prompt_price_usd_per_million >= 0
        assert route.completion_price_usd_per_million >= 0


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (("delete", "prompt", None), "price field is missing"),
        (("set", "prompt", "1.0"), "finite non-negative number"),
        (("set", "prompt", float("nan")), "finite non-negative number"),
        (("set", "completion", -1.0), "finite non-negative number"),
        (("container", "", []), "must be an object"),
    ],
)
def test_canonical_prices_fail_closed(
    mutation: tuple[str, str, object], match: str
) -> None:
    value = copy.deepcopy(_serialized_adapter())
    action, field, replacement = mutation
    if action == "delete":
        del value["maximum_route_price_usd_per_million"][field]  # type: ignore[index]
    elif action == "set":
        value["maximum_route_price_usd_per_million"][field] = replacement  # type: ignore[index]
    else:
        value["maximum_route_price_usd_per_million"] = replacement
    with pytest.raises(ConfigurationError, match=match):
        CanonicalLaunchRoute.from_serialized_adapter(value)


def test_rc13_nested_price_regression_and_rc15_strict_reconstruction() -> None:
    archived = calculate_rc13_cost_plan(ROOT)
    repaired = calculate_rc15_cost_plan(ROOT)
    assert len(archived["observations"]) == len(repaired["observations"]) == 5
    assert all(
        row["reconstructed_no_cache_cost_usd"] > 0
        for row in repaired["observations"]
    )
    assert {
        row["model_id"]: row["reconstructed_no_cache_cost_usd"]
        for row in archived["observations"]
    } == {
        row["model_id"]: row["reconstructed_no_cache_cost_usd"]
        for row in repaired["observations"]
    }


def test_independent_nine_cell_cost_calculations_agree() -> None:
    value = calculate_rc15_cost_plan(ROOT)
    assert value["method"]["target_cell_count"] == 9
    assert value["independent_calculations_agree"] is True
    for quantile in ("0.5", "0.9", "0.95"):
        assert abs(
            value["independent_quantiles_usd"]["expanded"][quantile]
            - value["independent_quantiles_usd"]["multinomial"][quantile]
        ) <= 1e-10
    assert value["sentinel_no_cache_p90_usd"] <= 52.0
    assert value["excluded_routes"] == ["z-ai/glm-5.2"]


def test_successor_modules_cannot_bypass_canonical_adapter() -> None:
    protected_keys = {
        "maximum_prompt_price_usd_per_million",
        "maximum_completion_price_usd_per_million",
        "maximum_route_price_usd_per_million",
        "context_length",
        "maximum_completion_tokens",
        "provider_order",
        "reasoning_mode",
        "requested_reasoning_effort",
    }
    modules = [
        "mmmvp_open_rc15_cost.py",
        "mmmvp_open_rc15_order.py",
        "mmmvp_open_rc15_rehearsal.py",
        "mmmvp_open_rc15_sentinel.py",
        "mmmvp_open_rc15_analysis.py",
    ]
    violations: list[str] = []
    for name in modules:
        path = ROOT / "src/uc_bench" / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript):
                continue
            key = node.slice.value if isinstance(node.slice, ast.Constant) else None
            if key in protected_keys:
                violations.append(f"{name}:{node.lineno}:{key}")
    assert violations == []


def test_schema_inventory_and_compatibility_inheritance_are_zero_cost() -> None:
    inventory = schema_parsing_inventory(ROOT)
    inheritance = compatibility_inheritance(ROOT)
    assert inventory["status"] == "passed"
    assert inventory["successor_raw_flat_price_bypasses"] == []
    assert inheritance["status"] == "passed"
    assert inheritance["new_compatibility_requests"] == 0
    assert inheritance["provider_specific_exclusions"] == ["z-ai/glm-5.2"]


def test_order_is_randomized_over_exact_compatible_set() -> None:
    models = list(load_rc15_launch_routes(ROOT))
    first = order_record(
        models,
        release_infrastructure_digest="candidate",
        entropy=b"a" * 32,
    )
    second = order_record(
        models,
        release_infrastructure_digest="candidate",
        entropy=b"b" * 32,
    )
    assert set(first["execution_order"]) == set(models)
    assert first["execution_order"] != second["execution_order"]
    assert first["entropy_commitment_sha256"] != second[
        "entropy_commitment_sha256"
    ]


def test_global_and_cell_failure_boundaries_are_separate() -> None:
    provider = {
        "classification": "provider_adapter_failure",
        "usable_provider_response_count": 0,
        "provider_requests": [
            {"error": {"http_status": 503, "message": "temporarily unavailable"}}
        ],
        "integrity": {
            "start_state_untampered": True,
            "protected_evidence_untampered": True,
            "protected_evidence_mutation_attempted": False,
            "workspace_boundary_enforced": True,
        },
        "trajectory_persistence": {"passed": False},
        "grader_consistency": {"passed": True},
        "agent_received_provider_credentials": False,
    }
    assert rc15_global_stop_faults(provider) == []
    corrupted = copy.deepcopy(provider)
    corrupted["integrity"]["protected_evidence_untampered"] = False
    assert "protected_data_mutation" in rc15_global_stop_faults(corrupted)


def test_paid_sentinel_reuses_frozen_scientific_runner() -> None:
    from uc_bench import mmmvp_open_rc15_sentinel as sentinel

    source = inspect.getsource(sentinel.run_rc15_sentinel)
    assert "run_rc14_open_mmmvp_episode(" in source
    assert "case_id=\"case_02\"" in source
    assert "case_01" not in source
    assert "case_03" not in source
    assert "case_04" not in source


def test_config_changes_no_scientific_execution_setting() -> None:
    rc14 = json.loads(
        (ROOT / "configs/uc_bench_mmmvp_open_rc14_release.json").read_text()
    )
    rc15 = json.loads(
        (ROOT / "configs/uc_bench_mmmvp_open_rc15_release.json").read_text()
    )
    assert rc14["scientific_episode"] == rc15["scientific_episode"]
    assert rc15["sentinel"]["scientific_episode_count_maximum"] == 9
    assert rc15["sentinel"]["continue_to_remaining_matrix"] is False


def test_gate_command_restores_frozen_predecessor_before_judgement(
    tmp_path: Path,
) -> None:
    target = tmp_path / "frozen" / "evidence.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"immutable":true}\n')
    expected = {"frozen/evidence.json": sha256_file(target)}
    snapshot = FrozenByteSnapshot.capture(tmp_path, expected)
    result = run_preserving_frozen_files(
        tmp_path,
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "Path('frozen/evidence.json').write_text('{\\\"changed\\\":true}\\n')"
            ),
        ],
        snapshot,
    )
    assert result["passed"]
    assert result["frozen_predecessor_mutation_attempts_restored"] == [
        "frozen/evidence.json"
    ]
    assert sha256_file(target) == expected["frozen/evidence.json"]
