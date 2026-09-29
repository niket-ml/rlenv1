"""Zero-cost pre-freeze evidence pack for the Case 2 RC1 candidate."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc6_release import read_rc6_freeze
from uc_bench.case2_pilot_v1_rc1_contract import (
    CONTEXT_MINIMUMS,
    PUBLIC_CONTRACT,
)
from uc_bench.case2_pilot_v1_rc1_controls import (
    build_reference,
    build_strong_context_variant,
    grade,
)
from uc_bench.case2_pilot_v1_rc1_environment import (
    DEVELOPMENT_ACTION_CONTRACT,
    FIELD_GUIDE,
    IDENTITY_PROVENANCE,
    MISSION,
    PUBLIC_SUPPORT_MODULES,
    Case2PilotRC1Environment,
)
from uc_bench.case2_pilot_v1_rc1_semantics import evaluate_case2_submission

RELEASE_ID = "uc-bench-case2-pilot-v1-rc1"
CASE1_RC6_DIGEST = "a1795f1be20b02bb02d86516a664a3d62aed7d6ca716bdd45cb277b4c1ea6d19"
ARTIFACT_DIRECTORY = "artifacts/uc_bench_case2_pilot_v1_rc1_candidate"

CANDIDATE_SOURCE_PATHS = (
    "src/uc_bench/case2_pilot_v1_rc1_contract.py",
    "src/uc_bench/case2_pilot_v1_rc1_environment.py",
    "src/uc_bench/case2_pilot_v1_rc1_semantics.py",
    "src/uc_bench/case2_pilot_v1_rc1_verifier.py",
    "src/uc_bench/case2_pilot_v1_rc1_controls.py",
    "src/uc_bench/case2_pilot_v1_rc1_audit.py",
    "src/uc_bench/case2_pilot_v1_infrastructure.py",
    "tests/test_case2_pilot_v1_rc1.py",
    "tests/test_case2_pilot_v1_readiness.py",
)

SOURCE_FIXTURE_ROOTS = (
    "tasks/hard_suite_v07/development/case_02",
    "grader_private/hard_suite_v07/case_02",
    "grader_private/mmmvp_open_rc1/case_02",
)

HISTORICAL_RUN_ROOT = "build/uc_bench_mmmvp_open_rc14_runs"

HISTORICAL_FIXTURE_HASHES = {
    (
        "open-mmmvp-rc16-sentinel-00-anthropic-claude-sonnet-4-case-02-attempt-/submission.json"
    ): "b4055dc095d3f515d26e567c925138afd10093356844895997345bd379a21e46",
    (
        "open-mmmvp-rc16-sentinel-00-anthropic-claude-sonnet-4-case-02-attempt-/run_summary.json"
    ): "36d5dd3d259b1827c312d28cb4d5ca133bd56a33c8ed75b8422a95b870aba9ca",
    (
        "open-mmmvp-rc16-sentinel-01-openai-gpt-5-case-02-attempt-0/submission.json"
    ): "3863dffa03bb96798f6f0c09ed4248703bf8762aa69e5b9ee3f7b74d66cc6828",
    (
        "open-mmmvp-rc16-sentinel-01-openai-gpt-5-case-02-attempt-0/run_summary.json"
    ): "006610277b468cb1bcf06493621f2bbe90e9ef5d8343de7ecc5a339ee244d81f",
    (
        "open-mmmvp-rc16-sentinel-02-anthropic-claude-opus-4.1-case-02-attempt-/submission.json"
    ): "648308a8ae3719a4c722327f2ec344b027c202306e81a2b038631388a41c388e",
    (
        "open-mmmvp-rc16-sentinel-02-anthropic-claude-opus-4.1-case-02-attempt-/run_summary.json"
    ): "80d4be211c1cfdd8e404e2df5c1f24c3717aeca2bfe564a0455bf963e60b382f",
    (
        "open-mmmvp-rc16-sentinel-03-google-gemini-3.1-pro-preview-case-02-atte/submission.json"
    ): "9a61d609ac5a33635b989c4da9b69603f983ea3e7c64ffb2645669e2ad2c98a5",
    (
        "open-mmmvp-rc16-sentinel-03-google-gemini-3.1-pro-preview-case-02-atte/run_summary.json"
    ): "9bedbea832b1821da988f15cdb733b9c10392c0620a2b6fb3c0d9883480104fe",
    (
        "open-mmmvp-rc16-sentinel-04-mistralai-mistral-large-2512-case-02-attem/submission.json"
    ): "652da0b1b1252e9d0c60089f06147f09a1f4cda0c8a4f2d42d31464cad193499",
    (
        "open-mmmvp-rc16-sentinel-04-mistralai-mistral-large-2512-case-02-attem/run_summary.json"
    ): "e1e6af0aecfaed3debdb2d9d131dc84c670d7f4b51ebbded50c22b6c93fc13ce",
    (
        "open-mmmvp-rc16-sentinel-05-qwen-qwen3.5-397b-a17b-case-02-attempt-0/request_ledger.json"
    ): "96966fc30928e1f9a94af0a56345f9e1ead7d28167284969720a4469a0c31ebc",
    (
        "open-mmmvp-rc16-sentinel-06-deepseek-deepseek-v3.2-case-02-attempt-0/request_ledger.json"
    ): "a1c3c0c421dcdfc0f43fd31a0b4b35222b80b699955c9a9ac2fae3eb84834bd4",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hashes(root: Path, relative: str) -> dict[str, str]:
    directory = root / relative
    return {
        path.relative_to(root).as_posix(): _sha(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _status(grade_value: dict[str, Any]) -> dict[str, Any]:
    return {
        "partial_scientific_quality": grade_value["partial_scientific_quality"],
        "complete_mission_success": grade_value["complete_mission_success"],
        "mission_failures": list(grade_value["mission_failures"]),
        "first_decision_critical_failure": grade_value["first_decision_critical_failure"],
        "failure_class": grade_value["failure_class"],
    }


def _public_hidden_parity(
    root: Path, workspace: Path, submission: dict[str, Any]
) -> dict[str, Any]:
    for name in ("validation_plan", "followup_plan", "final_submission"):
        _write_json(workspace / "work" / f"{name}.json", submission[name])
    completed = subprocess.run(
        [sys.executable, str(workspace / "validate_science.py")],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    public = json.loads(completed.stdout)
    hidden = evaluate_case2_submission(workspace, submission).to_dict()
    properties = {row["requirement_id"]: row["passed"] for row in public["requirements"]}
    hidden_properties = {row["requirement_id"]: row["passed"] for row in hidden["requirements"]}
    support_equal = all(
        (workspace / "public_support/uc_bench" / filename).read_bytes()
        == (root / "src/uc_bench" / filename).read_bytes()
        for filename in PUBLIC_SUPPORT_MODULES
    )
    scientific_equal = bool(
        public["partial_scientific_quality"] == hidden["partial_scientific_quality"]
        and public["complete_mission_success"] == hidden["complete_mission_success"]
        and public["mission_failures"] == list(hidden["mission_failures"])
        and properties == hidden_properties
        and public["diagnostics"]["resource"] == hidden["diagnostics"]["resource"]
    )
    return {
        "passed": bool(completed.returncode == 0 and scientific_equal and support_equal),
        "public_exit_code": completed.returncode,
        "public_grade": _status(public),
        "hidden_grade": _status(hidden),
        "property_outcomes_equal": properties == hidden_properties,
        "scientific_grade_equal": scientific_equal,
        "full_grade_equal": public == hidden,
        "host_only_process_diagnostics_expected_to_differ": True,
        "public_support_sources_byte_identical": support_equal,
        "semantic_engine": "case2_pilot_v1_rc1_semantics.py",
    }


def build_controls(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="uc-case2-rc1-controls-") as temporary:
        temporary_root = Path(temporary)
        for aggregation in ("MEAN", "NONE"):
            submission, workspace = build_reference(
                root, temporary_root / f"workflow-{aggregation.lower()}", aggregation=aggregation
            )
            rows.append(
                {
                    "control": f"valid_workflow_{aggregation.lower()}",
                    "class": "accepted_professional_alternative",
                    **_status(grade(submission, workspace)),
                }
            )
        for resource in ("none", "X17", "X24", "X31", "X46", "X58", "X63"):
            submission, workspace = build_reference(
                root, temporary_root / f"resource-{resource}", resource=resource
            )
            current = grade(submission, workspace)
            rows.append(
                {
                    "control": f"declared_resource_path_{resource}",
                    "class": "resource_return_recomputation",
                    "resource": current["diagnostics"]["resource"],
                    **_status(current),
                }
            )
        for disposition, scope in (
            ("PAUSE", "HOLD_CURRENT_CLAIM"),
            ("INSUFFICIENT_EVIDENCE", "HOLD_CURRENT_CLAIM"),
            ("CONTINUE", "TARGETED_CONTEXT_INVESTIGATION"),
            ("STOP", "END_DEVELOPMENT_PATH"),
        ):
            submission, workspace = build_reference(
                root,
                temporary_root / f"action-{disposition.lower()}",
                decision_override=(disposition, scope),
            )
            rows.append(
                {
                    "control": f"evidence_supported_{disposition.lower()}",
                    "class": "accepted_decision_branch",
                    **_status(grade(submission, workspace)),
                }
            )

        strong, strong_workspace = build_strong_context_variant(
            root, temporary_root / "strong-context"
        )
        strong_grade = evaluate_case2_submission(
            strong_workspace, strong, require_host_process=False
        ).to_dict()
        rows.append(
            {
                "control": "altered_input_strong_context_general_advance",
                "class": "altered_input_anti_policy",
                **_status(strong_grade),
            }
        )
        universal_pause = copy.deepcopy(strong)
        paused_decision = copy.deepcopy(universal_pause["final_submission"]["decision"])
        paused_decision.update(
            {
                "development_stage": "INTERNAL_VALIDATION",
                "disposition": "PAUSE",
                "use_scope": "NO_USE",
                "action_scope": "HOLD_CURRENT_CLAIM",
                "multisite_probability_use_permitted": False,
            }
        )
        contingency_id = universal_pause["final_submission"]["belief_updates"][0][
            "matched_contingency_id"
        ]
        next(
            row
            for row in universal_pause["followup_plan"]["result_contingencies"]
            if row["contingency_id"] == contingency_id
        )["next_decision"] = copy.deepcopy(paused_decision)
        universal_pause["final_submission"]["decision"] = copy.deepcopy(paused_decision)
        pause_grade = evaluate_case2_submission(
            strong_workspace, universal_pause, require_host_process=False
        ).to_dict()
        rows.append(
            {
                "control": "universal_pause_fails_when_context_passes",
                "class": "generic_policy_attack",
                **_status(pause_grade),
            }
        )
        universal_stop = copy.deepcopy(strong)
        stopped_decision = copy.deepcopy(universal_stop["final_submission"]["decision"])
        stopped_decision.update(
            {
                "development_stage": "STOPPED",
                "disposition": "STOP",
                "use_scope": "NO_USE",
                "action_scope": "END_DEVELOPMENT_PATH",
                "multisite_probability_use_permitted": False,
            }
        )
        next(
            row
            for row in universal_stop["followup_plan"]["result_contingencies"]
            if row["contingency_id"] == contingency_id
        )["next_decision"] = copy.deepcopy(stopped_decision)
        universal_stop["final_submission"]["decision"] = copy.deepcopy(stopped_decision)
        universal_stop["final_submission"]["findings"][0]["decision_effect"] = "INVALIDATES"
        stop_grade = evaluate_case2_submission(
            strong_workspace, universal_stop, require_host_process=False
        ).to_dict()
        rows.append(
            {
                "control": "universal_stop_fails_when_context_passes",
                "class": "generic_policy_attack",
                **_status(stop_grade),
            }
        )

        parity_submission, parity_workspace = build_reference(
            root, temporary_root / "semantic-parity", resource="X17"
        )
        parity = _public_hidden_parity(root, parity_workspace, parity_submission)

    expected_fail = {
        "declared_resource_path_X31",
        "declared_resource_path_X63",
        "universal_pause_fails_when_context_passes",
        "universal_stop_fails_when_context_passes",
    }
    passed = (
        all(
            row["complete_mission_success"] == (row["control"] not in expected_fail) for row in rows
        )
        and parity["passed"]
    )
    return {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-controls-1",
        "api_requests": 0,
        "paid_spend_usd": 0.0,
        "passed": passed,
        "controls": rows,
    }, parity


def historical_fixture_replay(root: Path) -> dict[str, Any]:
    run_root = root / HISTORICAL_RUN_ROOT
    observed_hashes = {
        relative: _sha(run_root / relative) for relative in HISTORICAL_FIXTURE_HASHES
    }
    if observed_hashes != HISTORICAL_FIXTURE_HASHES:
        raise RuntimeError("immutable RC1.6 historical fixture changed")
    rows: list[dict[str, Any]] = []
    for path in sorted(run_root.glob("open-mmmvp-rc16-sentinel-*/submission.json")):
        if not any(
            slug in path.as_posix()
            for slug in ("sonnet", "openai-gpt-5-", "opus", "gemini", "mistral")
        ):
            continue
        submission = json.loads(path.read_text(encoding="utf-8"))
        replay = evaluate_case2_submission(path.parent / "workspace", submission).to_dict()
        summary_path = path.parent / "run_summary.json"
        archived_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        archived_grade = archived_summary.get("diagnostic_grade") or {}
        archived_requirements = archived_grade.get("requirements") or []
        final = submission.get("final_submission") or {}
        followup = submission.get("followup_plan") or {}
        rows.append(
            {
                "run_id": path.parent.name,
                "model_id": archived_summary.get("model_id"),
                "submission_sha256": _sha(path),
                "archived_run_summary_sha256": _sha(summary_path),
                "archived_classification": archived_summary.get("classification"),
                "candidate_parser_replay": _status(replay),
                "immutable_scientific_fixture": {
                    "resource_choice": followup.get("chosen_resource"),
                    "final_disposition": (final.get("decision") or {}).get("disposition"),
                    "artifact_count": len(final.get("artifact_manifest") or []),
                    "calculation_count": len(final.get("calculations") or []),
                    "belief_update_count": len(final.get("belief_updates") or []),
                    "claim_status_and_scope": [
                        [row.get("status"), row.get("scope")]
                        for row in final.get("claims") or []
                        if isinstance(row, dict)
                    ],
                    "archived_property_outcomes": {
                        row.get("requirement_id"): row.get("passed")
                        for row in archived_requirements
                        if isinstance(row, dict)
                    },
                    "archived_first_failure": (
                        archived_grade.get("first_decision_critical_failure") or {}
                    ).get("requirement_id"),
                    "archived_failure_sequence": list(archived_grade.get("mission_failures") or []),
                },
                "fixture_checks": {
                    "parser_total": replay.get("failure_class")
                    in {"contract_failure", "scientific_failure", "none"},
                    "artifact_chain_observed": "saved_artifact_chain"
                    in {
                        row.get("requirement_id")
                        for row in archived_requirements
                        if isinstance(row, dict)
                    },
                    "identity_alternative_observed": "relevant_entity_reconstruction"
                    in {
                        row.get("requirement_id")
                        for row in archived_requirements
                        if isinstance(row, dict)
                    },
                    "resource_choice_observed": isinstance(followup.get("chosen_resource"), str),
                    "belief_and_claim_shapes_observed": isinstance(
                        final.get("belief_updates"), list
                    )
                    and isinstance(final.get("claims"), list),
                    "causal_failure_recorded": bool(
                        isinstance(archived_grade.get("first_decision_critical_failure"), dict)
                        and (archived_grade.get("first_decision_critical_failure") or {}).get(
                            "requirement_id"
                        )
                        == next(iter(archived_grade.get("mission_failures") or []), None)
                    ),
                },
                "interpretation": (
                    "The immutable payload and its archived causal diagnostics are regression "
                    "fixtures. Candidate parsing is total, but its contract result is not a "
                    "rescore because the model did not see the candidate contract."
                ),
            }
        )
    return {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-historical-replay-1",
        "api_requests": 0,
        "historical_records_mutated": False,
        "immutable_fixture_hashes": observed_hashes,
        "ranking_eligible": False,
        "rows": rows,
    }


def build_candidate_evidence(root: Path) -> dict[str, Any]:
    artifact_root = root / ARTIFACT_DIRECTORY
    artifact_root.mkdir(parents=True, exist_ok=True)
    rc6 = read_rc6_freeze(root)
    if rc6["closure"]["aggregate_digest"] != CASE1_RC6_DIGEST:
        raise RuntimeError("Accepted Case 1 RC6 digest changed")

    controls, parity = build_controls(root)
    history = historical_fixture_replay(root)
    with tempfile.TemporaryDirectory(prefix="uc-case2-rc1-packet-") as temporary:
        public_workspace = Path(temporary) / "workspace"
        Case2PilotRC1Environment(root, public_workspace)
        public_hashes = {
            path.relative_to(public_workspace).as_posix(): _sha(path)
            for path in sorted(public_workspace.rglob("*"))
            if path.is_file()
        }

    source_fixture_hashes: dict[str, str] = {}
    for relative in SOURCE_FIXTURE_ROOTS:
        source_fixture_hashes.update(_tree_hashes(root, relative))
    candidate_hashes = {relative: _sha(root / relative) for relative in CANDIDATE_SOURCE_PATHS}
    authored_surface = "\n".join(
        (root / relative).read_text(encoding="utf-8") for relative in CANDIDATE_SOURCE_PATHS[:5]
    )
    no_leak = {
        "passed": all(
            token not in authored_surface
            for token in (
                "0.82736",
                "0.72098",
                "0.56867",
                "0.50446",
                "F0017",
                "F0018",
                '"canonical_person_count": 95',
                '"provisional_unit_count": 96',
                "artifacts/mmmvp_open_rc14",
            )
        ),
        "authored_candidate_contains_private_answer_constants": False,
        "public_start_state_contains_sealed_outcomes": any(
            path.startswith("revealed/") for path in public_hashes
        ),
        "public_start_state_contains_oracle_or_grader": any(
            "truth" in path or "grader" in path for path in public_hashes
        ),
        "compromised_rc14_artifact_chain_is_runtime_authority": False,
        "note": (
            "Public input rows legitimately contain source identifiers to investigate. "
            "The authored contract contains no planted identity result, metric, outcome, "
            "private disposition, or RC1.4 artifact dependency."
        ),
    }
    no_leak["passed"] = bool(
        no_leak["passed"]
        and not no_leak["public_start_state_contains_sealed_outcomes"]
        and not no_leak["public_start_state_contains_oracle_or_grader"]
    )

    contract_diff = {
        "approved_changes_only": True,
        "identity_before": (
            "Historical implementations treated fingerprint_cluster as the operational "
            "person key or otherwise obscured its provisional status."
        ),
        "identity_after": IDENTITY_PROVENANCE,
        "context_before": (
            "The public intended-use gates omitted a context floor while the private "
            "grader independently preferred PAUSE/INSUFFICIENT_EVIDENCE."
        ),
        "context_after": {
            "minimums": CONTEXT_MINIMUMS,
            "decision_standard": PUBLIC_CONTRACT["context_decision_standard"],
        },
        "unchanged": [
            "public case data and locked predictor",
            "sealed outcomes",
            "preprocessing evidence",
            "follow-up catalogue and returned resources",
            "five irreversible actions and one-purchase budget",
            "ten scientific-property weights",
        ],
    }
    decision_table = {
        "GENERAL_MULTISITE_ADVANCEMENT": {
            "allowed_when": "every committed primary and context criterion passes",
            "decision": "CONTINUE",
            "current_multisite_probability_use": True,
        },
        "TARGETED_CONTEXT_INVESTIGATION": {
            "allowed_when": "context failed or is not evaluable and a context question remains",
            "decision": "CONTINUE",
            "current_multisite_probability_use": False,
            "required_target": sorted(PUBLIC_CONTRACT["enums"]["evidence_target"]),
        },
        "HOLD_CURRENT_CLAIM": {
            "allowed_when": "a consequential gate remains unresolved",
            "decisions": ["PAUSE", "INSUFFICIENT_EVIDENCE"],
            "current_multisite_probability_use": False,
        },
        "END_DEVELOPMENT_PATH": {
            "allowed_when": "verified evidence invalidates the development path",
            "decision": "STOP",
            "current_multisite_probability_use": False,
        },
    }
    freeze_proposal = {
        "freeze_now": False,
        "release_id_if_approved": RELEASE_ID,
        "required_closure": {
            "candidate_source_hashes": candidate_hashes,
            "scientific_source_fixture_hashes": source_fixture_hashes,
            "agent_visible_start_state_hashes": public_hashes,
            "public_hidden_semantic_parity": parity["passed"],
            "zero_cost_controls": controls["passed"],
            "independent_reviews": ["blind_packet_review", "rl_environment_scientific_review"],
            "runner_and_route_policy": "must be added and tested before a later freeze",
            "funding_gate": "must be refreshed immediately before any authorized model call",
        },
        "must_not_include": [
            "API keys or authorization headers",
            "private outcomes or oracle in the agent-visible packet",
            "historical RC1.4 artifact digest as release authority",
            "a preferred resource, disposition or scientific narrative",
        ],
    }
    cost_plan = {
        "pricing_status": "historical planning estimate; refresh routes and headroom pre-launch",
        "proposed_panel": [
            ["google/gemini-3.1-pro-preview", "Google AI Studio"],
            ["openai/gpt-5.1", "OpenAI"],
            ["openai/gpt-5", "OpenAI"],
            ["anthropic/claude-sonnet-4", "Amazon Bedrock"],
            ["anthropic/claude-opus-4.1", "Amazon Bedrock"],
        ],
        "smallest_sentinel": {
            "models": [
                "google/gemini-3.1-pro-preview",
                "openai/gpt-5.1",
                "anthropic/claude-sonnet-4",
            ],
            "median_estimate_usd": 7.04,
            "hard_cap_usd": 12.0,
        },
        "full_five_model_pilot": {
            "median_estimate_usd": 40.42,
            "no_cache_25_percent_contingency_usd": 50.53,
            "hard_cap_usd": 52.0,
        },
    }
    provenance = {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-provenance-root-1",
        "release_id": RELEASE_ID,
        "new_provenance_root": True,
        "frozen": False,
        "api_requests": 0,
        "paid_spend_usd": 0.0,
        "case1_rc6_release_digest": CASE1_RC6_DIGEST,
        "case1_rc6_modified": False,
        "source_fixture_hashes": source_fixture_hashes,
        "candidate_source_hashes": candidate_hashes,
        "agent_visible_start_state_hashes": public_hashes,
        "historical_fixtures_are_read_only": True,
        "rc14_archive_is_release_authority": False,
    }

    _write_json(artifact_root / "control_results.json", controls)
    _write_json(artifact_root / "semantic_parity.json", parity)
    _write_json(artifact_root / "historical_fixture_replay.json", history)
    _write_json(artifact_root / "contract_diff.json", contract_diff)
    _write_json(artifact_root / "decision_table.json", decision_table)
    _write_json(artifact_root / "no_leak_audit.json", no_leak)
    _write_json(artifact_root / "cost_plan.json", cost_plan)
    _write_json(artifact_root / "freeze_manifest_proposal.json", freeze_proposal)
    _write_json(artifact_root / "provenance.json", provenance)
    candidate_manifest = {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-candidate-1",
        "release_id": RELEASE_ID,
        "status": (
            "PREFREEZE_REVIEW_READY"
            if controls["passed"] and parity["passed"] and no_leak["passed"]
            else "NO_GO"
        ),
        "frozen": False,
        "api_requests": 0,
        "paid_spend_usd": 0.0,
        "approved_construct_repairs": ["neutral_provisional_identity", "public_context_rule"],
        "scientific_sources_changed": False,
        "controls_passed": controls["passed"],
        "semantic_parity_passed": parity["passed"],
        "no_leak_passed": no_leak["passed"],
        "review_state": "independent review artifacts are recorded separately",
        "mission": MISSION,
        "field_guide_sha256": hashlib.sha256(FIELD_GUIDE.encode()).hexdigest(),
        "action_contract": DEVELOPMENT_ACTION_CONTRACT,
    }
    _write_json(artifact_root / "candidate_manifest.json", candidate_manifest)
    return candidate_manifest


__all__ = ["ARTIFACT_DIRECTORY", "RELEASE_ID", "build_candidate_evidence"]
