from __future__ import annotations

import inspect
from pathlib import Path

from uc_bench.case1_pilot_v1_rc3_tools import case1_tool_definitions
from uc_bench.case2_pilot_v1_rc1_interface import production_request
from uc_bench.case2_pilot_v1_rc1_provider import load_case2_adapters, load_case2_config
from uc_bench.case2_pilot_v1_rc1_release import read_freeze as read_rc1_freeze
from uc_bench.case2_pilot_v1_rc2_execution import route_snapshot
from uc_bench.case2_pilot_v1_rc2_release import (
    RC1_RELEASE_DIGEST,
    SCOPE_DIFF_PATH,
    candidate_manifest,
    compatibility_adjudication,
    rc1_to_rc2_diff,
)
from uc_bench.case2_pilot_v1_rc2_runner import Case2RunConfig
from uc_bench.hashing import canonical_sha256

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_rc1_integrity_and_successor_scope_proof() -> None:
    rc1 = read_rc1_freeze(ROOT)
    assert rc1["closure"]["aggregate_digest"] == RC1_RELEASE_DIGEST
    result = rc1_to_rc2_diff(ROOT)
    assert result["passed"]
    assert all(result["checks"].values())
    assert result["allowed_functional_changes"] == [
        "endpoint_catalog_identity_normalization"
    ]


def test_request_tools_adapters_and_configuration_are_exactly_inherited() -> None:
    rc1 = read_rc1_freeze(ROOT)
    request = production_request(Case2RunConfig("digest", "openai/gpt-5.1"))
    adapters = {key: value.to_dict() for key, value in load_case2_adapters(ROOT).items()}
    config = load_case2_config(ROOT)
    assert canonical_sha256(request) == rc1["request_sha256"]
    assert canonical_sha256(case1_tool_definitions()) == rc1["tool_schema_sha256"]
    assert adapters == rc1["provider_adapters"]
    assert config["models"] == rc1["model_configuration"]
    assert config["execution_limits"] == rc1["execution_limits"]


def test_compatibility_is_inherited_without_inference_calls() -> None:
    result = compatibility_adjudication(ROOT)
    assert result["passed"]
    assert result["source_digest"] == RC1_RELEASE_DIGEST
    assert result["affected_routes_requiring_live_canary"] == []
    assert result["new_api_requests"] == 0
    assert result["new_spend_usd"] == 0.0


def test_candidate_binds_scope_proof_and_separates_endpoint_parser() -> None:
    if not (ROOT / SCOPE_DIFF_PATH).is_file():
        return
    candidate = candidate_manifest(ROOT)
    assert candidate["rc1_to_rc2_diff"]["passed"]
    groups = candidate["closure"]["groups"]
    assert set(groups["endpoint_identity_normalization"]) == {
        "src/uc_bench/case2_pilot_v1_rc2_endpoint.py"
    }
    assert candidate["compatibility_inheritance"]["new_api_requests"] == 0


def test_production_route_gate_uses_only_the_new_explicit_parser() -> None:
    source = inspect.getsource(route_snapshot)
    assert "route_evidence(" in source
    assert "model_name" not in source
    assert "case2_pilot_v1_rc2_endpoint" in inspect.getsource(
        __import__("uc_bench.case2_pilot_v1_rc2_execution", fromlist=["*"])
    )
