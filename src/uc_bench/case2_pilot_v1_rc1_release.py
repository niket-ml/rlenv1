"""Immutable, category-separated release closure for Case 2 RC1."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc3_tools import case1_tool_definitions
from uc_bench.case2_pilot_v1_rc1_environment import (
    PUBLIC_SUPPORT_MODULES,
    Case2PilotRC1Environment,
)
from uc_bench.case2_pilot_v1_rc1_interface import production_request
from uc_bench.case2_pilot_v1_rc1_provider import (
    CONFIG_PATH,
    RELEASE_ID,
    load_case2_adapters,
    load_case2_config,
)
from uc_bench.case2_pilot_v1_rc1_runner import Case2RunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256

RELEASE_ROOT = Path("artifacts/uc_bench_case2_pilot_v1_rc1")
CANDIDATE_PATH = RELEASE_ROOT / "candidate_manifest.json"
PREFLIGHT_PATH = RELEASE_ROOT / "production_path_preflight.json"
GATE_PATH = RELEASE_ROOT / "zero_cost_gate.json"
RL_REVIEW_PATH = RELEASE_ROOT / "final_rl_review.json"
COMPATIBILITY_PATH = RELEASE_ROOT / "compatibility_adjudication.json"
FREEZE_PATH = RELEASE_ROOT / "release_freeze.json"

SCIENTIFIC_SOURCE_FILES = (
    Path("src/uc_bench/case2_pilot_v1_rc1_contract.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_semantics.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_verifier.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_controls.py"),
)
RUNNER_SOURCE_FILES = (
    Path("src/uc_bench/case2_pilot_v1_rc1_environment.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_runtime.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_trajectory.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_runner.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_execution.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_analysis.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_preflight.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_release.py"),
    Path("scripts/prepare_case2_pilot_v1_rc1.py"),
    Path("scripts/run_case2_pilot_v1_rc1.py"),
)
PROVIDER_SOURCE_FILES = (
    Path("src/uc_bench/case2_pilot_v1_rc1_provider.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_interface.py"),
    Path("src/uc_bench/case1_pilot_v1_rc3_tools.py"),
    Path("src/uc_bench/case1_pilot_v1_rc6_lifecycle.py"),
)
TEST_FILES = (
    Path("src/uc_bench/case2_pilot_v1_rc1_audit.py"),
    Path("tests/test_case2_pilot_v1_rc1.py"),
    Path("tests/test_case2_pilot_v1_readiness.py"),
    Path("tests/test_case2_pilot_v1_rc1_release.py"),
)
REVIEW_FILES = tuple(
    Path("artifacts/uc_bench_case2_pilot_v1_rc1_candidate") / name
    for name in (
        "blind_review.json",
        "candidate_manifest.json",
        "contract_diff.json",
        "control_results.json",
        "decision_table.json",
        "freeze_manifest_proposal.json",
        "historical_fixture_replay.json",
        "no_leak_audit.json",
        "provenance.json",
        "review_dispositions.json",
        "rl_scientific_review.json",
        "semantic_parity.json",
        "validation_results.json",
    )
)
SOURCE_ROOTS = (
    Path("tasks/hard_suite_v07/development/case_02"),
    Path("grader_private/hard_suite_v07/case_02"),
    Path("grader_private/mmmvp_open_rc1/case_02"),
)
CASE1_RC6_DIGEST = "a1795f1be20b02bb02d86516a664a3d62aed7d6ca716bdd45cb277b4c1ea6d19"
CASE1_RC6_REQUEST_DIGEST = (
    "0f39fc1de9edfddd4b574c07dbb90eded8b8e6838382eb8bbd3f891f70339a2e"
)
CASE1_RC6_TOOL_DIGEST = (
    "a29133462152f7c78452a5e13c76efc2991142b8703ce418cdf4a78d10f842d7"
)
CASE1_RC6_ADAPTER_DIGESTS = {
    "google/gemini-3.1-pro-preview": (
        "c457f002f1bfb460464fa4b787e659f1fd0359bbda59f5d40e72329118395cba"
    ),
    "openai/gpt-5.1": (
        "5dc68c2e6ea26bfce3e1fad8637f23b3b1c3d2adc4ab845f980f78f29f0dfd60"
    ),
    "anthropic/claude-sonnet-4": (
        "3841eea8f38d5f41ea7a755fb8fde11bbb91f8fa507dbac27618d7845a95d6c5"
    ),
}
_CREDENTIAL = re.compile(rb"sk-or-v1-[A-Za-z0-9_-]{20,}")
_SAFE_FIXTURE = re.compile(rb"sk-or-v1-(?:case2|rc[0-9]+)-fake-[A-Za-z0-9_-]+")
EXPECTED_GATE_CHECKS = frozenset(
    {
        "all_53_case2_controls_pass",
        "candidate_control_count_preserved",
        "candidate_controls",
        "clean_staged_closure",
        "compatibility_inherited_without_new_calls",
        "credential_scan",
        "docker_isolation",
        "exact_production_path_rehearsal",
        "full_repository_has_only_four_allowlisted_historical_failures",
        "lint_doctor_status_audit",
        "no_api_calls",
        "public_hidden_semantic_parity",
    }
)
EXPECTED_PREFLIGHT_CHECKS = frozenset(
    {
        "all_fake_clients_closed",
        "horizon_final_tool_is_unexecuted",
        "exhausted_provider_attempts_are_cell_local",
        "invalid_output_path_recoverable",
        "malformed_arguments_recoverable_and_persisted",
        "no_paid_calls",
        "outer_runner_adoption_recomputed",
        "outer_runner_adoption_rejects_index_tampering",
        "outer_runner_restart_modes",
        "protected_mutation_blocked",
        "recovered_response_parse_retry_adopts",
        "recovered_transient_retry_adopts",
        "provider_terminal_is_cell_local",
        "restart_after_purchase",
        "restart_after_reveal",
        "restart_before_reveal",
        "restart_replay_exact",
        "scientific_failure_is_scored",
        "valid_no_purchase",
        "valid_pause",
        "valid_targeted_continue",
        "valid_x17_recomputed",
    }
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(root: Path, paths: tuple[Path, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"Release file is missing: {relative}")
        result[relative.as_posix()] = _sha(path)
    return dict(sorted(result.items()))


def _trees(root: Path, roots: tuple[Path, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in roots:
        for path in sorted((root / relative).rglob("*")):
            if path.is_file():
                result[path.relative_to(root).as_posix()] = _sha(path)
    return dict(sorted(result.items()))


def _transitive_uc_bench_sources(root: Path) -> dict[str, str]:
    """Resolve the production import closure without copying unrelated history."""

    seeds = {
        *SCIENTIFIC_SOURCE_FILES,
        *RUNNER_SOURCE_FILES,
        *PROVIDER_SOURCE_FILES,
        Path("src/uc_bench/__init__.py"),
    }
    queue = [path for path in seeds if path.suffix == ".py" and "scripts" not in path.parts]
    seen: set[Path] = set()
    while queue:
        relative = queue.pop()
        if relative in seen or not (root / relative).is_file():
            continue
        seen.add(relative)
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            for name in names:
                if not name.startswith("uc_bench."):
                    continue
                module = name.removeprefix("uc_bench.").split(".")[0]
                candidate = Path("src/uc_bench") / f"{module}.py"
                if (root / candidate).is_file() and candidate not in seen:
                    queue.append(candidate)
    return _files(root, tuple(sorted(seen)))


def _visible_hashes(root: Path) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="uc-case2-visible-") as directory:
        workspace = Path(directory) / "workspace"
        Case2PilotRC1Environment(root, workspace)
        return {
            path.relative_to(workspace).as_posix(): _sha(path)
            for path in sorted(workspace.rglob("*"))
            if path.is_file() and "work" not in path.relative_to(workspace).parts
        }


def _semantic_copy_status(root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="uc-case2-semantic-copy-") as directory:
        workspace = Path(directory) / "workspace"
        Case2PilotRC1Environment(root, workspace)
        rows = {
            name: (
                _sha(workspace / "public_support/uc_bench" / name),
                _sha(root / "src/uc_bench" / name),
            )
            for name in PUBLIC_SUPPORT_MODULES
        }
    return {
        "passed": all(public == host for public, host in rows.values()),
        "digests": {
            name: {"public": public, "host": host} for name, (public, host) in rows.items()
        },
    }


def compatibility_adjudication(root: Path) -> dict[str, Any]:
    request = production_request(Case2RunConfig("digest", "openai/gpt-5.1"))
    adapters = {key: value.to_dict() for key, value in load_case2_adapters(root).items()}
    observed_adapter_digests = {
        key: canonical_sha256(value) for key, value in adapters.items()
    }
    checks = {
        "request_digest_byte_identical": canonical_sha256(request)
        == CASE1_RC6_REQUEST_DIGEST,
        "tool_digest_byte_identical": canonical_sha256(case1_tool_definitions())
        == CASE1_RC6_TOOL_DIGEST,
        "adapter_digests_byte_identical": observed_adapter_digests
        == CASE1_RC6_ADAPTER_DIGESTS,
    }
    return {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-compatibility-1",
        "passed": all(checks.values()),
        "checks": checks,
        "source_release": "uc-bench-case1-pilot-v1-rc6",
        "source_digest": CASE1_RC6_DIGEST,
        "accepted_request_digest": CASE1_RC6_REQUEST_DIGEST,
        "accepted_tool_digest": CASE1_RC6_TOOL_DIGEST,
        "accepted_adapter_digests": CASE1_RC6_ADAPTER_DIGESTS,
        "affected_routes_requiring_live_canary": [] if all(checks.values()) else list(adapters),
        "new_api_requests": 0,
        "new_spend_usd": 0.0,
    }


def category_hashes(root: Path) -> dict[str, dict[str, str]]:
    original = _trees(root, SOURCE_ROOTS)
    protected = {
        path: digest for path, digest in original.items() if path.startswith("grader_private/")
    }
    source_visible = {
        path: digest for path, digest in original.items() if path.startswith("tasks/")
    }
    semantic_support = _files(
        root,
        tuple(Path("src/uc_bench") / name for name in PUBLIC_SUPPORT_MODULES),
    )
    explicit = {
        *SCIENTIFIC_SOURCE_FILES,
        *RUNNER_SOURCE_FILES,
        *PROVIDER_SOURCE_FILES,
        *(Path("src/uc_bench") / name for name in PUBLIC_SUPPORT_MODULES),
    }
    transitive = {
        path: digest
        for path, digest in _transitive_uc_bench_sources(root).items()
        if Path(path) not in explicit
    }
    return {
        "agent_visible_materialized": _visible_hashes(root),
        "agent_visible_source": source_visible,
        "protected_and_sealed": protected,
        "scientific_semantics_and_verifier": _files(root, SCIENTIFIC_SOURCE_FILES),
        "runner_persistence_reporting": _files(root, RUNNER_SOURCE_FILES),
        "provider_request_tool_adapters": _files(root, PROVIDER_SOURCE_FILES),
        "public_support_and_host_semantic": semantic_support,
        "transitive_runtime_support": transitive,
        "tests_controls_reviews": {
            **_files(root, TEST_FILES),
            **_files(root, REVIEW_FILES),
        },
        "route_and_cost_policy": _files(root, (CONFIG_PATH,)),
    }


def candidate_manifest(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_case2_config(root)
    groups = category_hashes(root)
    group_digests = {name: canonical_sha256(rows) for name, rows in groups.items()}
    compatibility = compatibility_adjudication(root)
    semantic_copy = _semantic_copy_status(root)
    if not compatibility["passed"]:
        raise ConfigurationError("Provider-facing compatibility inheritance failed")
    if not semantic_copy["passed"]:
        raise ConfigurationError("Public semantic support differs from host sources")
    return {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-candidate-2",
        "release_id": RELEASE_ID,
        "status": "candidate_unfrozen",
        "model_configuration": config["models"],
        "provider_adapters": {
            key: value.to_dict() for key, value in load_case2_adapters(root).items()
        },
        "execution_order": config["execution_order"],
        "execution_limits": config["execution_limits"],
        "budgets_usd": config["budgets_usd"],
        "request_sha256": canonical_sha256(
            production_request(Case2RunConfig("digest", "openai/gpt-5.1"))
        ),
        "tool_schema_sha256": canonical_sha256(case1_tool_definitions()),
        "compatibility_inheritance": compatibility,
        "public_support_copy": semantic_copy,
        "closure": {
            "groups": groups,
            "group_digests": group_digests,
            "file_count": sum(len(rows) for rows in groups.values()),
            "aggregate_digest": canonical_sha256(group_digests),
            "runtime_monkeypatching": False,
            "historical_build_directory_dependency": False,
        },
    }


def credential_scan(root: Path, groups: dict[str, dict[str, str]]) -> bool:
    paths = {
        path
        for name, rows in groups.items()
        if name != "agent_visible_materialized"
        for path in rows
    }
    for relative in paths:
        content = (root / relative).read_bytes()
        for match in _CREDENTIAL.findall(content):
            if not _SAFE_FIXTURE.fullmatch(match):
                return False
    return True


def stage_closure(project_root: Path, target: Path) -> dict[str, Any]:
    root, destination = project_root.resolve(), target.resolve()
    if destination.exists():
        raise FileExistsError(f"Staging target already exists: {destination}")
    destination.mkdir(parents=True)
    manifest = candidate_manifest(root)
    expected = {
        path: digest
        for name, rows in manifest["closure"]["groups"].items()
        if name != "agent_visible_materialized"
        for path, digest in rows.items()
    }
    for relative in expected:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, output)
    observed = {path: _sha(destination / path) for path in expected}
    return {
        "passed": observed == expected,
        "file_count": len(observed),
        "aggregate_digest": canonical_sha256(observed),
    }


def write_candidate(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / CANDIDATE_PATH
    if path.exists():
        raise FileExistsError("Case 2 release candidate already exists")
    value = candidate_manifest(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if target.exists():
        raise FileExistsError("Case 2 RC1 is already frozen")
    candidate = json.loads((root / CANDIDATE_PATH).read_text(encoding="utf-8"))
    gate = json.loads((root / GATE_PATH).read_text(encoding="utf-8"))
    review = json.loads((root / RL_REVIEW_PATH).read_text(encoding="utf-8"))
    compatibility = json.loads((root / COMPATIBILITY_PATH).read_text(encoding="utf-8"))
    preflight = json.loads((root / PREFLIGHT_PATH).read_text(encoding="utf-8"))
    current = candidate_manifest(root)
    if current != candidate:
        raise ConfigurationError("Case 2 candidate changed before freeze")
    gate_checks = gate.get("checks")
    if (
        gate.get("schema_version") != "uc-bench-case2-pilot-v1-rc1-zero-cost-gate-1"
        or gate.get("passed") is not True
        or gate.get("candidate_digest") != current["closure"]["aggregate_digest"]
        or gate.get("api_requests") != 0
        or not isinstance(gate_checks, dict)
        or set(gate_checks) != EXPECTED_GATE_CHECKS
        or not all(value is True for value in gate_checks.values())
        or not isinstance(gate.get("commands"), list)
        or len(gate["commands"]) != 6
        or not all(row.get("passed") is True for row in gate["commands"])
    ):
        raise ConfigurationError("Case 2 zero-cost gate evidence is invalid")
    preflight_checks = preflight.get("checks")
    if (
        preflight.get("schema_version")
        != "uc-bench-case2-pilot-v1-rc1-production-preflight-1"
        or preflight.get("passed") is not True
        or preflight.get("api_requests") != 0
        or preflight.get("paid_spend_usd") != 0.0
        or not isinstance(preflight_checks, dict)
        or set(preflight_checks) != EXPECTED_PREFLIGHT_CHECKS
        or not all(value is True for value in preflight_checks.values())
    ):
        raise ConfigurationError("Case 2 production preflight evidence is invalid")
    if (
        review.get("schema_version")
        != "uc-bench-case2-pilot-v1-rc1-final-rl-review-1"
        or review.get("release_id") != RELEASE_ID
        or review.get("candidate_digest") != current["closure"]["aggregate_digest"]
        or review.get("disposition") != "APPROVE"
        or not isinstance(review.get("blocker_or_high_findings"), list)
        or review["blocker_or_high_findings"]
        or not isinstance(review.get("inspected_evidence_paths"), list)
        or not review["inspected_evidence_paths"]
        or review.get("api_requests") != 0
    ):
        raise ConfigurationError("Final RL review has blocker/high findings")
    if (
        compatibility != current["compatibility_inheritance"]
        or compatibility.get("schema_version")
        != "uc-bench-case2-pilot-v1-rc1-compatibility-1"
        or compatibility.get("passed") is not True
        or compatibility.get("new_api_requests") != 0
        or compatibility.get("new_spend_usd") != 0.0
        or compatibility.get("affected_routes_requiring_live_canary") != []
        or not all((compatibility.get("checks") or {}).values())
    ):
        raise ConfigurationError("Compatibility adjudication changed before freeze")
    attestations = {
        path.as_posix(): _sha(root / path)
        for path in (CANDIDATE_PATH, PREFLIGHT_PATH, GATE_PATH, RL_REVIEW_PATH, COMPATIBILITY_PATH)
    }
    if not credential_scan(root, current["closure"]["groups"]):
        raise ConfigurationError("Credential appeared in Case 2 release closure")
    value = {
        **current,
        "schema_version": "uc-bench-case2-pilot-v1-rc1-freeze-1",
        "status": "frozen_pre_science",
        "frozen_at": datetime.now(UTC).isoformat(),
        "attestation_hashes": attestations,
    }
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def _frozen_candidate_fields_match(
    frozen: dict[str, Any], candidate: dict[str, Any]
) -> bool:
    """Validate the two declared transitions and preserve every other field."""

    return (
        candidate.get("schema_version") == "uc-bench-case2-pilot-v1-rc1-candidate-2"
        and candidate.get("status") == "candidate_unfrozen"
        and frozen.get("schema_version") == "uc-bench-case2-pilot-v1-rc1-freeze-1"
        and frozen.get("status") == "frozen_pre_science"
        and all(
            field in {"schema_version", "status"} or frozen.get(field) == expected
            for field, expected in candidate.items()
        )
    )


def read_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / FREEZE_PATH
    if not path.is_file():
        raise ConfigurationError("Case 2 RC1 is not frozen")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("schema_version") != "uc-bench-case2-pilot-v1-rc1-freeze-1"
        or value.get("release_id") != RELEASE_ID
        or value.get("status") != "frozen_pre_science"
    ):
        raise ConfigurationError("Case 2 freeze identity is invalid")
    current = candidate_manifest(root)
    if not _frozen_candidate_fields_match(value, current):
        raise ConfigurationError("Frozen Case 2 candidate fields changed")
    expected_attestations = {
        item.as_posix(): _sha(root / item)
        for item in (CANDIDATE_PATH, PREFLIGHT_PATH, GATE_PATH, RL_REVIEW_PATH, COMPATIBILITY_PATH)
    }
    if value.get("attestation_hashes") != expected_attestations:
        raise ConfigurationError("Case 2 release attestations changed")
    return value


__all__ = [
    "CANDIDATE_PATH",
    "COMPATIBILITY_PATH",
    "FREEZE_PATH",
    "GATE_PATH",
    "PREFLIGHT_PATH",
    "RELEASE_ROOT",
    "RL_REVIEW_PATH",
    "candidate_manifest",
    "compatibility_adjudication",
    "freeze",
    "read_freeze",
    "stage_closure",
    "write_candidate",
]
