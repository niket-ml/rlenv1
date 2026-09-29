from __future__ import annotations

import asyncio
import copy
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

import uc_bench.mmmvp_open_controls as controls
from uc_bench.durable_runner import DurableRequestLedger
from uc_bench.mmmvp_open_rc14_audit import (
    audit_contract_disclosure,
    issue_is_disclosed,
    replay_archived_submissions,
)
from uc_bench.mmmvp_open_rc14_compatibility import (
    ContractCompatibilityBudget,
    run_one_contract_canary,
)
from uc_bench.mmmvp_open_rc14_contract import (
    ENUMS,
    FINAL_SUBMISSION_FIELDS,
    FOLLOWUP_PLAN_FIELDS,
    IDENTIFIER_PATTERN,
    RC14_AGENT_VISIBLE_CONTRACT,
    RELATIONSHIP_CONSTRAINTS,
    VALIDATION_PLAN_FIELDS,
)
from uc_bench.mmmvp_open_rc14_environment import RC14OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc14_harness import (
    ConvergenceBudget,
    TechnicalCanaryCore,
    _result_classification,
    _technical_observation,
    forensic_adjudicate_round01,
    run_one_production_path_canary,
    technical_replay_check,
)
from uc_bench.mmmvp_open_rc14_runner import (
    RC14DurableAuditedOpenRouterClient,
    RC14DurableTrajectoryStore,
)
from uc_bench.mmmvp_open_rc14_sentinel import rc14_global_stop_faults
from uc_bench.mmmvp_open_schema import (
    SCHEMA_VERSION,
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.mmmvp_open_verifier import SCORE_SOURCE_TABLE, verify_open_submission
from uc_bench.mmmvp_provider import MMMVPProviderAdapter
from uc_bench.v06_provider import ProviderIdentityError


def _decision() -> dict[str, Any]:
    return {
        "development_stage": "INTERNAL_VALIDATION",
        "disposition": "PAUSE",
        "use_scope": "NO_USE",
        "allowed_use": ["Internal evaluation may continue."],
        "prohibited_use": ["Do not deploy."],
        "unresolved_gates": ["One question remains."],
        "required_next_evidence": ["Resolve that question."],
    }


def _validation() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "decision_definition": "Choose the bounded next action.",
        "evidence_standard": "Use saved, source-linked calculations.",
        "hypotheses": [
            {
                "hypothesis_id": "H1",
                "statement": "The evidence supports bounded continuation.",
                "belief": 0.5,
                "decision_effect_if_true": "SUPPORTS",
            },
            {
                "hypothesis_id": "H2",
                "statement": "A material limitation weakens continuation.",
                "belief": 0.5,
                "decision_effect_if_true": "WEAKENS",
            },
            {
                "hypothesis_id": "H3",
                "statement": "A material defect invalidates continuation.",
                "belief": 0.1,
                "decision_effect_if_true": "INVALIDATES",
            },
        ],
        "planned_analyses": [
            {
                "analysis_id": "A1",
                "question": "What does the evidence support?",
                "method": "A defensible source-linked analysis.",
                "analysis_unit": "The scientifically justified unit.",
                "input_paths": ["intended_use.json"],
                "planned_output_paths": ["work/result.json"],
                "decision_relevance": "It informs the bounded decision.",
            }
        ],
        "decision_criteria": [
            {
                "criterion_id": "D1",
                "calculation_id": "C1",
                "metric": "ROC_AUC",
                "comparator": "AT_LEAST",
                "threshold": 0.5,
            }
        ],
        "evidence_refs": ["intended_use.json"],
    }


def _followup() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "decision_question_id": "Q1",
        "decision_question": "Which evidence has decision value?",
        "chosen_resource": "none",
        "evidence_target": "NO_NEW_EVIDENCE",
        "live_explanations": [
            {
                "explanation_id": "E1",
                "statement": "One explanation is viable.",
                "distinguishing_evidence": "A measurable result.",
            },
            {
                "explanation_id": "E2",
                "statement": "A competing explanation is viable.",
                "distinguishing_evidence": "A different measurable result.",
            },
        ],
        "alternatives_considered": [
            {"resource_id": "none", "limitations": "No new evidence."},
            {"resource_id": "X63", "limitations": "Advice only."},
        ],
        "result_contingencies": [
            {
                "contingency_id": "K1",
                "observable_result": "The first explanation is supported.",
                "hypothesis_updates": [{"hypothesis_id": "H1", "direction": "INCREASE"}],
                "next_decision": _decision(),
                "next_action": "Follow the evidence.",
            },
            {
                "contingency_id": "K2",
                "observable_result": "The second explanation is supported.",
                "hypothesis_updates": [{"hypothesis_id": "H2", "direction": "DECREASE"}],
                "next_decision": _decision(),
                "next_action": "Revise the bounded action.",
            },
        ],
        "beliefs_before": {"H1": 0.5, "H2": 0.5, "H3": 0.1},
        "current_decision": _decision(),
        "evidence_refs": ["intended_use.json"],
    }


def _final() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_manifest": [
            {
                "artifact_id": "T1",
                "path": "work/table.csv",
                "role": "ANALYSIS_TABLE",
                "source_paths": ["data/source.csv"],
                "analysis_structure": "ENTITY_AGGREGATED",
                "aggregation": "MEAN",
                "column_map": {
                    "entity_id": "person",
                    "source_record_ids": "records",
                    "prediction": "prediction",
                    "outcome": "outcome",
                    "split": "split",
                    "context": "site",
                },
            },
            {
                "artifact_id": "O1",
                "path": "work/results.json",
                "role": "CALCULATION_OUTPUT",
                "source_paths": ["work/table.csv"],
            },
        ],
        "calculations": [
            {
                "calculation_id": "C1",
                "role": "PRIMARY",
                "source_analysis_table_id": "T1",
                "unit_of_analysis": "BIOLOGICAL_ENTITY",
                "cohort": {
                    "split_values": ["VALIDATION"],
                    "entity_ids": [],
                    "included_row_count": 10,
                },
                "outcome_column": "outcome",
                "prediction_column": "prediction",
                "context_columns": ["site"],
                "metric": "ROC_AUC",
                "estimator": "EMPIRICAL",
                "parameters": {},
                "reported_value": 0.7,
                "evidence_source": "SUPPLIED_AND_REVEALED",
                "output_artifact_id": "O1",
                "uncertainty": {
                    "method": "CLUSTER_BOOTSTRAP_PERCENTILE",
                    "level": 0.95,
                    "lower": 0.6,
                    "upper": 0.8,
                    "replicates": 100,
                    "seed": 1,
                },
            }
        ],
        "findings": [
            {
                "finding_id": "F1",
                "statement": "A bounded finding.",
                "status": "SUPPORTED",
                "decision_effect": "SUPPORTS",
                "evidence_refs": ["work/results.json"],
                "calculation_ids": ["C1"],
            }
        ],
        "evidence_assessments": [
            {
                "evidence_id": "V1",
                "source_paths": ["work/table.csv"],
                "eligible_for_decision": True,
                "rationale": "The source chain is valid.",
            }
        ],
        "belief_updates": [
            {
                "hypothesis_id": "H1",
                "before": 0.5,
                "after": 0.6,
                "evidence_refs": ["work/results.json"],
                "matched_contingency_id": "K1",
            }
        ],
        "decision": _decision(),
        "claims": [
            {
                "claim_id": "L1",
                "statement": "A bounded claim.",
                "status": "SUPPORTED",
                "scope": "PROGNOSTIC_RANKING",
                "evidence_refs": ["work/results.json"],
                "calculation_ids": ["C1"],
            }
        ],
        "remaining_uncertainties": ["External validity remains unknown."],
        "evidence_refs": ["work/results.json"],
    }


def _delete_path(payload: Any, path: str) -> Any:
    if path == "$":
        return []
    value = copy.deepcopy(payload)
    current = value
    parts = path.replace("[*]", "[0]").split(".")
    for part in parts[:-1]:
        if "[" in part:
            name, index = part[:-1].split("[")
            current = current[name][int(index)]
        else:
            current = current[part]
    final = parts[-1]
    if "[" in final:
        name, index = final[:-1].split("[")
        del current[name][int(index)]
    else:
        current.pop(final, None)
    return value


def _issue_paths(result: Any) -> set[str]:
    return {issue.path for issue in result.issues}


def test_every_required_and_conditional_field_is_disclosed_and_enforced() -> None:
    cases = (
        (_validation(), VALIDATION_PLAN_FIELDS, validate_validation_plan),
        (_followup(), FOLLOWUP_PLAN_FIELDS, validate_followup_plan),
        (_final(), FINAL_SUBMISSION_FIELDS, validate_final_submission),
    )
    for payload, fields, validator in cases:
        assert validator(payload).valid
        for row in fields:
            if not row["required"] and row.get("required_when") is None:
                continue
            altered = _delete_path(payload, row["path"])
            result = validator(altered)
            assert not result.valid, row["path"]
            assert all(issue_is_disclosed(issue.to_dict()) for issue in result.issues)


def test_all_allowed_enum_values_are_schema_valid() -> None:
    validation_paths = {
        "decision_effect": ("hypotheses", 2, "decision_effect_if_true"),
        "calculation_metric": ("decision_criteria", 0, "metric"),
        "criterion_comparator": ("decision_criteria", 0, "comparator"),
    }
    for family, path in validation_paths.items():
        for allowed in ENUMS[family]:
            payload = _validation()
            payload[path[0]][path[1]][path[2]] = allowed
            assert validate_validation_plan(payload).valid, (family, allowed)

    for allowed in ENUMS["resource_id"]:
        payload = _followup()
        payload["chosen_resource"] = allowed
        assert validate_followup_plan(payload).valid
    for allowed in ENUMS["evidence_target"]:
        payload = _followup()
        payload["evidence_target"] = allowed
        assert validate_followup_plan(payload).valid
    for allowed in ENUMS["belief_direction"]:
        payload = _followup()
        payload["result_contingencies"][0]["hypothesis_updates"][0]["direction"] = allowed
        assert validate_followup_plan(payload).valid
    for family, field in (
        ("development_stage", "development_stage"),
        ("disposition", "disposition"),
        ("use_scope", "use_scope"),
    ):
        for allowed in ENUMS[family]:
            payload = _followup()
            payload["current_decision"][field] = allowed
            assert validate_followup_plan(payload).valid

    final_paths = {
        "artifact_role": ("artifact_manifest", 0, "role"),
        "analysis_structure": ("artifact_manifest", 0, "analysis_structure"),
        "aggregation": ("artifact_manifest", 0, "aggregation"),
        "calculation_role": ("calculations", 0, "role"),
        "unit_of_analysis": ("calculations", 0, "unit_of_analysis"),
        "calculation_metric": ("calculations", 0, "metric"),
        "calculation_estimator": ("calculations", 0, "estimator"),
        "calculation_evidence_source": ("calculations", 0, "evidence_source"),
        "uncertainty_method": ("calculations", 0, "uncertainty", "method"),
        "finding_status": ("findings", 0, "status"),
        "decision_effect": ("findings", 0, "decision_effect"),
        "claim_status": ("claims", 0, "status"),
        "claim_scope": ("claims", 0, "scope"),
    }
    for family, path in final_paths.items():
        for allowed in ENUMS[family]:
            payload = _final()
            target: Any = payload
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = allowed
            assert validate_final_submission(payload).valid, (family, allowed)


def test_invalid_enums_return_clear_recoverable_feedback() -> None:
    payload = _final()
    payload["calculations"][0]["unit_of_analysis"] = "PATIENTISH"
    result = validate_final_submission(payload)
    assert not result.valid
    issue = next(item for item in result.issues if item.path.endswith("unit_of_analysis"))
    assert issue.code == "invalid_enum"
    assert issue.message
    assert issue_is_disclosed(issue.to_dict())


def test_contract_has_no_private_scientific_hint_and_prose_cannot_score() -> None:
    result = audit_contract_disclosure()
    assert result["status"] == "passed"
    assert result["forbidden_scientific_disclosures"] == []
    assert RC14_AGENT_VISIBLE_CONTRACT["policy"]["identifier_pattern"] == IDENTIFIER_PATTERN
    assert all(not row["prose_can_affect_science"] for row in SCORE_SOURCE_TABLE)
    assert len(RELATIONSHIP_CONSTRAINTS) >= 14


def test_rc14_workspace_contains_revised_contract_before_hashing(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    environment = RC14OpenMMMVPEnvironment(root, "case_01", workspace)
    observed = json.loads((workspace / "submission_contract.json").read_text())
    assert observed == RC14_AGENT_VISIBLE_CONTRACT
    assert observed["enums"]["unit_of_analysis"] == [
        "BIOLOGICAL_ENTITY",
        "SOURCE_RECORD_CLUSTERED",
    ]
    assert "submission_contract.json" in environment._start_hashes  # noqa: SLF001


def test_first_attempt_semantic_payloads_need_no_hidden_rule_discovery() -> None:
    for payload, validator in (
        (_validation(), validate_validation_plan),
        (_followup(), validate_followup_plan),
        (_final(), validate_final_submission),
    ):
        result = validator(payload)
        assert result.valid
        assert result.issues == ()


def test_alternative_workflows_pass_and_generic_work_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(controls, "OpenMMMVPEnvironment", RC14OpenMMMVPEnvironment)
    reference, reference_workspace = controls.build_open_reference(
        root, "case_02", tmp_path / "reference", alternative=False
    )
    alternative, alternative_workspace = controls.build_open_reference(
        root, "case_02", tmp_path / "alternative", alternative=True
    )
    assert verify_open_submission(
        root, reference_workspace, reference, condition_id="case_02"
    ).complete_mission_success
    assert verify_open_submission(
        root, alternative_workspace, alternative, condition_id="case_02"
    ).complete_mission_success
    for submission in (reference, alternative):
        assert not any(
            row.get("event", "").endswith("_rejected")
            for row in submission["event_log"]
        )

    unsupported_workspace = tmp_path / "unsupported"
    controls._copy_workspace(reference_workspace, unsupported_workspace)  # noqa: SLF001
    unsupported = controls._relocate_submission(  # noqa: SLF001
        reference, unsupported_workspace
    )
    unsupported_final = copy.deepcopy(unsupported["final_submission"])
    unsupported_final["decision"] = {
        **unsupported_final["decision"],
        "development_stage": "EXTERNAL_VALIDATION",
        "disposition": "CONTINUE",
        "use_scope": "RESEARCH_PROBABILITY",
    }
    controls._replace_final_submission(  # noqa: SLF001
        unsupported, unsupported_workspace, unsupported_final
    )
    assert not verify_open_submission(
        root, unsupported_workspace, unsupported, condition_id="case_02"
    ).complete_mission_success

    generic, generic_workspace = controls.build_open_reference(
        root,
        "case_01",
        tmp_path / "generic",
        alternative=False,
        planned_output_paths=["work/generic_checklist.txt"],
    )
    generic_grade = verify_open_submission(
        root, generic_workspace, generic, condition_id="case_01"
    )
    assert not generic_grade.complete_mission_success
    assert "prospective_plan_implemented" in generic_grade.mission_failures


def test_natural_prose_paraphrases_do_not_change_schema() -> None:
    first = _final()
    second = copy.deepcopy(first)
    second["decision"]["allowed_use"] = ["Continue a limited research assessment."]
    second["decision"]["prohibited_use"] = ["No patient-facing action is justified."]
    second["decision"]["unresolved_gates"] = ["Generalisation has not been established."]
    second["decision"]["required_next_evidence"] = ["Obtain evidence addressing that limit."]
    assert validate_final_submission(first).valid
    assert validate_final_submission(second).valid


def test_archived_replay_is_diagnostic_only_and_all_old_rules_are_now_disclosed() -> None:
    root = Path(__file__).resolve().parents[1]
    result = replay_archived_submissions(root)
    assert result["status"] == "passed"
    assert result["diagnostic_replay_only"]
    assert not result["archived_scores_recomputed"]
    assert not result["archived_scores_reinterpreted"]
    assert result["all_replayed_issues_now_disclosed"]
    assert {row["model_id"] for row in result["models"]} == {
        "mistralai/mistral-large-2512",
        "anthropic/claude-sonnet-4",
        "google/gemini-3.1-pro-preview",
    }


def test_fake_route_ingests_revised_contract_and_submits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = MMMVPProviderAdapter(
        model_id="lab/fake",
        expected_canonical_slug="lab/fake-pinned",
        provider_order=("Lab Provider",),
        allow_fallbacks=False,
        requested_reasoning_effort="medium",
        reasoning_mode="effort",
        tool_choice="auto",
        preserve_reasoning_state=True,
        maximum_prompt_price_usd_per_million=0.1,
        maximum_completion_price_usd_per_million=0.1,
        supported_parameters=("max_tokens", "reasoning", "tool_choice", "tools"),
        endpoint_contract_digest="digest",
        context_length=50_000,
        maximum_completion_tokens=5_000,
    )

    class FakeClient:
        def __init__(self, ledger: Any) -> None:
            self.ledger = ledger

        async def get_native_response(
            self, messages: Any, model: str, sampling: Any, tools: Any
        ) -> dict[str, Any]:
            assert "BIOLOGICAL_ENTITY" in messages[-1]["content"]
            payload = {
                "contract_revision": "rc1.4",
                "schema_version": SCHEMA_VERSION,
                "unit_of_analysis_values": [
                    "BIOLOGICAL_ENTITY",
                    "SOURCE_RECORD_CLUSTERED",
                ],
                "calculation_cohort_fields": [
                    "entity_ids",
                    "included_row_count",
                    "split_values",
                ],
                "analysis_table_conditional_fields": [
                    "aggregation",
                    "analysis_structure",
                    "column_map",
                ],
                "supported_claim_nonempty_fields": [
                    "calculation_ids",
                    "evidence_refs",
                ],
            }
            response = {
                "model": "lab/fake-pinned",
                "provider": "Lab Provider",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call-contract",
                                    "type": "function",
                                    "function": {
                                        "name": "submit_contract_check",
                                        "arguments": json.dumps(
                                            {"payload_json": json.dumps(payload)}
                                        ),
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.001},
            }
            self.ledger.record_response(response, latency_seconds=0.01)
            return response

        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        "uc_bench.mmmvp_open_rc14_compatibility.load_open_route_contract_adapters",
        lambda root: {"lab/fake": adapter},
    )
    monkeypatch.setattr(
        "uc_bench.mmmvp_open_rc14_compatibility.build_v071_scientific_client",
        lambda **kwargs: FakeClient(kwargs["ledger"]),
    )
    result = asyncio.run(
        run_one_contract_canary(
            Path(__file__).resolve().parents[1],
            key="sk-or-v1-test-secret",
            model_id="lab/fake",
            output_root=tmp_path,
            budget=ContractCompatibilityBudget(),
        )
    )
    assert result["classification"] == "compatible"
    assert result["revised_contract_ingested"]
    assert result["structured_submission"]
    assert result["request_count"] == 1
    assert "sk-or-v1-test-secret" not in json.dumps(result)


def test_runner_changes_only_environment_and_release_wiring() -> None:
    from uc_bench import mmmvp_open_rc14_runner as runner

    source = inspect.getsource(runner.run_rc14_open_mmmvp_episode)
    assert "RC14OpenMMMVPEnvironment(" in source
    assert "read_rc14_release_freeze" in source
    assert "verify_open_submission(" in source
    assert "build/uc_bench_mmmvp_open_rc14_runs" in source


def _production_fixture_adapter(model_id: str, provider: str) -> MMMVPProviderAdapter:
    return MMMVPProviderAdapter(
        model_id=model_id,
        expected_canonical_slug=f"{model_id}-canonical",
        provider_order=(provider,),
        allow_fallbacks=False,
        requested_reasoning_effort="medium",
        reasoning_mode="effort",
        tool_choice="auto",
        preserve_reasoning_state=True,
        maximum_prompt_price_usd_per_million=20.0,
        maximum_completion_price_usd_per_million=80.0,
        supported_parameters=("max_tokens", "reasoning", "tool_choice", "tools"),
        endpoint_contract_digest="fixture-contract",
        context_length=50_000,
        maximum_completion_tokens=5_000,
    )


def _production_fixture_path(
    tmp_path: Path, adapter: MMMVPProviderAdapter
) -> tuple[
    RC14DurableAuditedOpenRouterClient,
    DurableRequestLedger,
    RC14DurableTrajectoryStore,
    TechnicalCanaryCore,
]:
    workspace = tmp_path / "workspace"
    core = TechnicalCanaryCore(workspace)
    ledger = DurableRequestLedger(
        tmp_path / "request_ledger.json",
        adapter,
        secret="sk-or-v1-fixture-secret",
        remaining_cap_usd=10.0,
    )
    store = RC14DurableTrajectoryStore(
        tmp_path / "host_trajectory",
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret="sk-or-v1-fixture-secret",
        run_metadata={"fixture": True},
    )
    client = RC14DurableAuditedOpenRouterClient(object(), adapter, ledger, store)
    return client, ledger, store, core


@pytest.mark.parametrize(
    "fixture",
    json.loads(
        (
            Path(__file__).parent
            / "fixtures/mmmvp_open_rc14_round01_response_shapes.json"
        ).read_text()
    )["models"],
    ids=lambda row: row["model_id"],
)
def test_round01_response_shapes_use_production_persistence_before_judgement(
    fixture: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _production_fixture_adapter(fixture["model_id"], fixture["provider"])
    client, ledger, store, core = _production_fixture_path(tmp_path, adapter)

    class CapturedProviderError(RuntimeError):
        pass

    if "error" in fixture:
        error = CapturedProviderError(fixture["error"]["message"])
        error.status_code = fixture["error"]["status_code"]  # type: ignore[attr-defined]

        async def captured(*args: Any, **kwargs: Any) -> Any:
            raise error

    else:

        async def captured(*args: Any, **kwargs: Any) -> Any:
            return fixture["response"]

    monkeypatch.setattr(
        "uc_bench.mmmvp_open_rc14_runner.post_chat_completion_with_routed_experts_sidecar",
        captured,
    )
    prompt = [{"role": "user", "content": "Run the technical round trip."}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "record_technical_round_trip",
                "parameters": {
                    "type": "object",
                    "properties": {"payload": {"type": "string"}},
                    "required": ["payload"],
                },
            },
        }
    ]
    if "error" in fixture:
        with pytest.raises(CapturedProviderError):
            asyncio.run(
                client.get_native_response(
                    prompt,
                    adapter.model_id,
                    adapter.sampling_args(maximum_completion_tokens=5000),
                    tools,
                )
            )
        latest = store.latest()
        assert latest["event_type"] == "provider_error"
        assert ledger.records[0]["error"]["classification"] == "provider_adapter_failure"
        return

    asyncio.run(
        client.get_native_response(
            prompt, adapter.model_id, adapter.sampling_args(maximum_completion_tokens=5000), tools
        )
    )
    events = [
        json.loads(path.read_text())["event_type"]
        for path in sorted(store.journal_root.glob("*.json"))
    ]
    assert events == ["raw_model_response_received", "model_response"]
    assert store.latest()["provider_exchanges"][0]["raw_response"] == fixture["response"]
    assert not ledger.records[0]["identity_violations"]
    replay = technical_replay_check(
        store,
        workspace=core.workspace,
        core=core,
        secret="sk-or-v1-fixture-secret",
    )
    observation = _technical_observation(
        generated={"outputs": [{"stop_condition": None}]},
        ledger=ledger,
        store=store,
        replay=replay,
    )
    classification = _result_classification(observation, replay)
    if fixture["expected_adjudication"] == "technical_inconclusive_token_exhaustion":
        assert classification == "technical_inconclusive_token_exhaustion"
    else:
        assert store.latest()["pending_tool_calls"][0]["name"] == (
            "record_technical_round_trip"
        )


def test_raw_and_malformed_arguments_are_persisted_before_identity_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _production_fixture_adapter("lab/model", "Lab")
    client, ledger, store, _ = _production_fixture_path(tmp_path, adapter)
    response = {
        "model": "wrong/model",
        "provider": "Lab",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "bad-json",
                            "type": "function",
                            "function": {
                                "name": "record_technical_round_trip",
                                "arguments": "{",
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.001},
    }

    async def captured(*args: Any, **kwargs: Any) -> Any:
        return response

    monkeypatch.setattr(
        "uc_bench.mmmvp_open_rc14_runner.post_chat_completion_with_routed_experts_sidecar",
        captured,
    )
    with pytest.raises(ProviderIdentityError):
        asyncio.run(
            client.get_native_response(
                [{"role": "user", "content": "technical"}],
                adapter.model_id,
                adapter.sampling_args(maximum_completion_tokens=5000),
                [],
            )
        )
    journal = [
        json.loads(path.read_text())
        for path in sorted(store.journal_root.glob("*.json"))
    ]
    assert [row["event_type"] for row in journal] == [
        "raw_model_response_received",
        "model_response",
    ]
    assert journal[0]["event"]["raw_response"] == response
    assert journal[1]["pending_tool_calls"][0]["arguments"] is None
    assert ledger.records[0]["identity_violations"] == ["returned_model_mismatch"]


def test_round01_forensic_adjudication_preserves_original_and_reruns_only_two() -> None:
    root = Path(__file__).resolve().parents[1]
    before = (
        root / "artifacts/mmmvp_open_rc14/compatibility_results.json"
    ).read_bytes()
    result = forensic_adjudicate_round01(root, write=False)
    assert result["technically_compatible_model_count"] == 8
    assert result["rerun_models"] == [
        "z-ai/glm-5.2",
        "qwen/qwen3.5-397b-a17b",
    ]
    assert result["original_result_sha256_before"] == result[
        "original_result_sha256_after"
    ]
    assert (
        root / "artifacts/mmmvp_open_rc14/compatibility_results.json"
    ).read_bytes() == before
    status = {row["model_id"]: row for row in result["models"]}
    assert status["anthropic/claude-sonnet-4"]["technical_status"] == (
        "technically_compatible"
    )
    assert status["moonshotai/kimi-k3"]["technical_status"] == (
        "technically_compatible"
    )
    assert status["anthropic/claude-opus-4.1"]["technical_status"] == (
        "technically_compatible"
    )
    assert status["deepseek/deepseek-v3.2"]["technical_status"] == (
        "technically_compatible"
    )


def test_full_fake_round_trip_uses_production_client_dispatch_and_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openai.types.chat.chat_completion import ChatCompletion

    adapter = _production_fixture_adapter("lab/model", "Lab")
    responses = [
        ChatCompletion.model_validate(
            {
                "id": "first",
                "created": 0,
                "object": "chat.completion",
                "model": "lab/model",
                "provider": "Lab",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "round-trip-call",
                                    "type": "function",
                                    "function": {
                                        "name": "record_technical_round_trip",
                                        "arguments": json.dumps({"payload": "anything"}),
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                    "cost": 0.001,
                },
            }
        ),
        ChatCompletion.model_validate(
            {
                "id": "second",
                "created": 1,
                "object": "chat.completion",
                "model": "lab/model",
                "provider": "Lab",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "done"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 5,
                    "total_tokens": 25,
                    "cost": 0.001,
                },
            }
        ),
    ]

    async def captured(*args: Any, **kwargs: Any) -> Any:
        return responses.pop(0)

    monkeypatch.setattr(
        "uc_bench.mmmvp_open_rc14_harness.load_open_route_contract_adapters",
        lambda root: {"lab/model": adapter},
    )
    monkeypatch.setattr(
        "uc_bench.mmmvp_open_rc14_runner.post_chat_completion_with_routed_experts_sidecar",
        captured,
    )
    result = run_one_production_path_canary(
        Path(__file__).resolve().parents[1],
        key="sk-or-v1-fixture-secret",
        model_id="lab/model",
        output_root=tmp_path / "attempts",
        budget=ConvergenceBudget(prior_spend_usd=0.0, hard_cap_usd=10.0),
        attempt_index=0,
    )
    assert result["classification"] == "technically_compatible"
    assert result["observation"]["parseable_response_count"] == 2
    assert result["observation"]["raw_response_receive_count"] == 2
    assert result["observation"]["tool_call_count"] == 1
    assert result["observation"]["tool_result_count"] == 1
    assert result["observation"]["continuation_response_recorded"]
    assert result["trajectory_replay"]["passed"]
    assert result["trajectory_replay"]["reopened"]
    assert not responses


def test_provider_and_model_failures_are_not_global_stops() -> None:
    healthy = {
        "classification": "provider_adapter_failure",
        "grader_consistency": {"passed": False},
        "integrity": {
            "start_state_untampered": True,
            "protected_evidence_untampered": True,
            "protected_evidence_mutation_attempted": False,
            "workspace_boundary_enforced": True,
        },
        "trajectory_persistence": {"passed": True},
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
    }
    assert rc14_global_stop_faults(healthy) == []
    model_failure = copy.deepcopy(healthy)
    model_failure["classification"] = "agent_task_failure"
    model_failure["grader_consistency"] = {"passed": True}
    assert rc14_global_stop_faults(model_failure) == []


def test_shared_corruption_is_a_global_stop() -> None:
    corrupted = {
        "classification": "unknown_harness_failure",
        "grader_consistency": {"passed": False},
        "integrity": {
            "start_state_untampered": False,
            "protected_evidence_untampered": False,
            "protected_evidence_mutation_attempted": True,
            "workspace_boundary_enforced": False,
        },
        "trajectory_persistence": {"passed": False},
        "agent_received_provider_credentials": True,
        "agent_network_enabled": False,
    }
    assert set(rc14_global_stop_faults(corrupted)) == {
        "verifier_contradiction",
        "scientific_start_state_changed",
        "protected_evidence_changed",
        "protected_evidence_tampering",
        "workspace_boundary_failure",
        "trajectory_lifecycle_inconsistency",
        "credential_or_network_leakage",
        "shared_harness_failure",
    }
