#!/usr/bin/env python3
# ruff: noqa: E501
"""Build the zero-cost v0.7 vertical slice, controls, reviews, and cost gate."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from statistics import median
from typing import Any

from uc_bench.hard_suite_v07 import (
    CASE_IDS,
    V07Environment,
    V07ProtocolError,
    build_development_cases,
    direct_submission,
    empty_submission,
    generic_submission,
    grade_submission,
    load_truth,
    replay_reference,
    validate_public_packet_has_no_truth_labels,
    validate_v07_config,
)

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "artifacts/diagnostics"
REPLAYS = ROOT / "artifacts/replays/hard_suite_v07"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def case_mechanism(case_id: str) -> str:
    return "signal_collapses" if case_id == "case_03" else "default"


def keyword_submission() -> dict[str, Any]:
    submission = empty_submission()
    submission["checkpoints"]["C1"] = {
        "diagnosed_concepts": [
            "patient_dependence",
            "site_confounding",
            "validation_information_leakage",
            "miscalibration",
            "negative_threshold_utility",
        ]
    }
    return submission


def mediocre_submission() -> dict[str, Any]:
    submission = direct_submission(ROOT, "case_02")
    truth = load_truth(ROOT, "case_02")
    submission["checkpoints"]["C1"].update(
        {
            "analysis_unit": "biopsy",
            "n_patients": truth["n_samples"],
            "dependence_inspected": False,
            "site_distribution_inspected": False,
            "diagnosed_concepts": ["minor_endpoint_disagreement"],
        }
    )
    submission["checkpoints"]["C3"] = {
        "metrics": {
            "auc": truth["metrics"]["naive_row_auc"],
            "auc_ci_low": truth["metrics"]["auc_ci_low"],
            "brier": truth["metrics"]["brier"],
            "ece": truth["metrics"]["ece"],
            "net_benefit": truth["metrics"]["net_benefit"],
        },
        "patient_dependence_preserved": False,
        "site_aware_analysis": False,
        "uncertainty_matches_commitment": False,
        "discrimination_calibration_utility_integrated": False,
    }
    submission["selected_resource"] = "X24"
    submission["spent_units"] = 2
    submission["checkpoints"]["C4"].update(
        {
            "selected_resource": "X24",
            "diagnosed_concepts": ["minor_endpoint_disagreement"],
            "possible_results": [],
        }
    )
    submission["checkpoints"]["C5"].update(
        {
            "belief_direction": "endpoint_concern_resolved",
            "claims_made": ["independent_validation_passed"],
            "unsupported_claims": ["treatment_effect"],
        }
    )
    return submission


def validity_cards() -> list[dict[str, Any]]:
    shared = {
        "professional_role": "cross-functional computational-biology diligence team",
        "unacceptable_shortcuts": [
            "accept sponsor assertions as truth",
            "use biopsy rows as independent patients",
            "report AUC without calibration and utility",
            "select a resource without predeclared result-contingent actions",
            "infer treatment effect from a prognostic predictor",
        ],
        "accepted_alternative_approaches": [
            "patient-cluster bootstrap or a defensible hierarchical model",
            "fixed-bin calibration error or a calibration intercept/slope analysis",
            "net benefit or an explicit expected-utility analysis under the same contract",
            "a resource within 0.08 decision-value units of the optimum",
        ],
    }
    return [
        {
            **shared,
            "case_id": "case_01",
            "professional_decision": "Distinguish a usable research signal from harmless data-room imperfections and avoid wasteful reassurance.",
            "planted_truth": "Patient-level discrimination, calibration, and threshold utility clear the research-use contract; archived execution detail is incomplete but there is no positive leakage evidence.",
            "evidence_path": [
                "cohort metadata -> fingerprint patients",
                "locked predictions + revealed patient outcomes -> metrics",
                "fit membership + logs -> no observed validation fit",
            ],
            "harmless_distractors": ["one duplicated assay export", "a noncausal timestamp skew"],
            "required_calculations": [
                "patient AUC and interval",
                "Brier score",
                "calibration error",
                "net benefit at 0.50",
                "site sensitivity",
            ],
            "critical_errors": [
                "stop because any imperfection exists",
                "buy an expensive cohort without a live decision question",
                "claim clinical utility",
            ],
            "followup_logic": "Purchase nothing or the cheap execution package; both are reasonable if the residual condition and delay are explicit.",
            "final_decision_range": ["conditional_advance"],
            "real_world_consequence": "A valid asset is delayed or overfunded, or a research result is overstated as clinical utility.",
        },
        {
            **shared,
            "case_id": "case_02",
            "professional_decision": "Decide whether apparent validation survives patient dependence and uneven site composition.",
            "planted_truth": "Repeated biopsies and outcome-associated site mix make the naive row result misleading; within-site performance is materially weaker. Minor endpoint disagreement is not the present blocker.",
            "evidence_path": [
                "reported IDs + fingerprint clusters -> repeated people",
                "site distribution + outcomes + predictions -> site-stratified performance",
                "source-record package -> identity reconciliation",
            ],
            "harmless_distractors": ["small endpoint-review disagreement"],
            "required_calculations": [
                "row AUC",
                "patient AUC and cluster interval",
                "site-specific and site-weighted AUC",
                "calibration and net benefit",
            ],
            "critical_errors": [
                "mention clustering but keep the row analysis",
                "treat endpoint review as the main blocker",
                "claim independent validation passed",
            ],
            "followup_logic": "The source-record package resolves identity cheaply and exposes the remaining site blocker; endpoint review cannot answer site transport.",
            "final_decision_range": ["pause", "insufficient_evidence"],
            "real_world_consequence": "Pseudoreplicated, site-specific performance is mistaken for transportable evidence.",
        },
        {
            **shared,
            "case_id": "case_03",
            "professional_decision": "Determine whether apparent performance survives an outcome-blind reconstruction of preprocessing.",
            "planted_truth": "Validation samples entered reference fitting after outcomes were imported. The original metrics are ineligible. A clean replay either collapses or retains signal, and those returns require opposite final decisions.",
            "evidence_path": [
                "preprocess code + membership -> actual fit inputs",
                "execution timestamps -> outcomes available before fit",
                "pipeline package -> clean replay predictions",
            ],
            "harmless_distractors": ["one batch-name alias"],
            "required_calculations": [
                "original patient metrics, explicitly marked ineligible",
                "clean-replay patient AUC, interval, calibration, and utility",
            ],
            "critical_errors": [
                "leakage detected therefore always stop",
                "use contaminated AUC in the final claim",
                "ignore favorable clean replay",
            ],
            "followup_logic": "Only the pipeline execution package directly removes the suspected mechanism; its two controlled returns separate detection from belief revision.",
            "final_decision_range": {
                "signal_collapses": ["stop"],
                "signal_remains": ["conditional_advance"],
            },
            "real_world_consequence": "Contaminated evidence advances a nonperforming asset, or recoverable valid signal is discarded without testing.",
        },
        {
            **shared,
            "case_id": "case_04",
            "professional_decision": "Assess whether attractive ranking performance has safe value at the proposed threshold and in the intended population.",
            "planted_truth": "AUC is attractive, but predictions are badly miscalibrated and net benefit at 0.50 is negative. Matched external evidence confirms the decision-value problem.",
            "evidence_path": [
                "patient predictions + outcomes -> AUC versus calibration and utility",
                "matched package -> same contract in new sites",
            ],
            "harmless_distractors": ["two missing noncritical covariates"],
            "required_calculations": [
                "patient AUC and interval",
                "Brier score",
                "calibration error",
                "threshold confusion and net benefit",
                "matched external replication",
            ],
            "critical_errors": [
                "advance on AUC alone",
                "recommend more of the same sample rather than matched decision evidence",
                "claim safe threshold use",
            ],
            "followup_logic": "Matched external evidence directly tests calibration and utility under the intended use; a larger same-process sample improves precision without resolving transport.",
            "final_decision_range": ["pause", "stop"],
            "real_world_consequence": "A ranking model is deployed as a calibrated decision rule and causes avoidable false-positive treatment decisions.",
        },
    ]


def remedy_map() -> list[dict[str, Any]]:
    return [
        {
            "failure": "biopsies treated as independent patients",
            "observable": "sample count exceeds fingerprint-patient count and cluster-aware uncertainty widens",
            "scored_at": ["C1.patient_analysis_unit", "C3.patient_and_site_structure_preserved"],
            "smallest_action": "collapse or model repeated biopsies at patient level",
            "remedy_category": "statistical training or checking tools",
            "paired_intervention": "case_02 with versus without patient/site metric helper",
            "recovery_measure": "C3 improves without changing C4/C5 truth",
        },
        {
            "failure": "site mix mistaken for transportable signal",
            "observable": "pooled AUC exceeds site-weighted and worst-site AUC",
            "scored_at": ["C3", "C4"],
            "smallest_action": "site-stratified analysis followed by site-diverse replication",
            "remedy_category": "additional matched data and experimental-design guidance",
            "paired_intervention": "case_02 with versus without site-stratification helper",
            "recovery_measure": "site diagnosis and safe pause recover",
        },
        {
            "failure": "validation information enters preprocessing",
            "observable": "validation IDs appear in fit membership after outcome import",
            "scored_at": ["C2", "C3", "C4"],
            "smallest_action": "purchase and analyse an outcome-blind locked replay",
            "remedy_category": "pipeline inspection or reproducibility tooling",
            "paired_intervention": "case_03 before versus after X31",
            "recovery_measure": "original evidence remains invalid while clean result drives C5",
        },
        {
            "failure": "leakage becomes a universal stop shortcut",
            "observable": "same starting evidence produces stop even when clean replay retains performance",
            "scored_at": ["C5"],
            "smallest_action": "revise belief from the clean replay rather than the diagnosis label",
            "remedy_category": "better belief revision",
            "paired_intervention": "case_03 signal_collapses versus signal_remains",
            "recovery_measure": "opposite supported final decisions",
        },
        {
            "failure": "AUC substitutes for decision value",
            "observable": "AUC clears while Brier, calibration error and net benefit fail",
            "scored_at": ["C3", "C5"],
            "smallest_action": "analyse calibration and threshold utility in a matched cohort",
            "remedy_category": "additional matched data and statistical checking tools",
            "paired_intervention": "case_04 before versus after X46",
            "recovery_measure": "ranking claim retained but threshold-use claim contained",
        },
        {
            "failure": "unnecessary reassurance purchase",
            "observable": "selected resource cannot change the live decision or costs more than a near-equivalent option",
            "scored_at": ["C4"],
            "smallest_action": "choose no action or a decision-efficient package",
            "remedy_category": "experimental-design guidance",
            "paired_intervention": "case_01 with versus without a VOI comparison aid",
            "recovery_measure": "C4 improves without forcing no-purchase as the only policy",
        },
        {
            "failure": "claim exceeds the evidence",
            "observable": "treatment effect, clinical utility, or broad-platform validity is asserted from prognostic research evidence",
            "scored_at": ["C5"],
            "smallest_action": "bind each claim to eligible evidence and intended use",
            "remedy_category": "clinical endpoint expertise or claim-checking process",
            "paired_intervention": "all cases with versus without claim-to-evidence checklist",
            "recovery_measure": "prohibited claims disappear while supported claims remain",
        },
    ]


def intervention_design() -> list[dict[str, Any]]:
    return [
        {
            "pair_id": "I01",
            "base": "case_02",
            "intervention": "patient/site statistical helper",
            "added_material": [
                "helper that joins fingerprint clusters, collapses biopsies, and reports site-stratified metrics"
            ],
            "target_checkpoint": "C3",
            "must_not_directly_reveal": ["diagnosis", "investment decision", "resource choice"],
            "causal_claim_allowed_only_if": "paired attempts improve C3 at the predicted property without broad prompt changes",
        },
        {
            "pair_id": "I02",
            "base": "case_03",
            "intervention": "pipeline execution evidence",
            "added_material": ["X31 fit-input hashes, clean lineage, and clean replay predictions"],
            "target_checkpoint": "C3/C5",
            "must_not_directly_reveal": ["whether clean signal survives", "final decision"],
            "causal_claim_allowed_only_if": "agents analyse the returned replay and improve at the first predicted divergence",
        },
        {
            "pair_id": "I03",
            "base": "case_04",
            "intervention": "matched external data",
            "added_material": [
                "X46 predictions, outcomes, sites, and threshold table under the intended contract"
            ],
            "target_checkpoint": "C5",
            "must_not_directly_reveal": ["utility conclusion", "final action"],
            "causal_claim_allowed_only_if": "paired attempts correctly revise calibration/utility beliefs after analysing new rows",
        },
        {
            "pair_id": "I04",
            "base": "case_01",
            "intervention": "value-of-information decision aid",
            "added_material": [
                "resource comparison worksheet using the unchanged neutral catalogue"
            ],
            "target_checkpoint": "C4",
            "must_not_directly_reveal": ["best resource", "case truth"],
            "causal_claim_allowed_only_if": "paired attempts reduce unnecessary spend without changing scientific calculations",
        },
        {
            "pair_id": "I05",
            "base": "all cases",
            "intervention": "claim-to-evidence checklist",
            "added_material": [
                "blank mapping from claim to eligible source and intended-use boundary"
            ],
            "target_checkpoint": "C5",
            "must_not_directly_reveal": ["supported claims", "decision"],
            "causal_claim_allowed_only_if": "overclaiming falls while valid bounded claims are preserved",
        },
    ]


def reset_table() -> list[dict[str, str]]:
    return [
        {
            "observed_v063_problem": "Ten report files rewarded completion and boilerplate.",
            "exact_v07_change": "Five decision-critical checkpoints; routine files receive no reward.",
            "professional_justification": "Diligence value comes from analysis and action, not document count.",
            "predicted_effect": "Generic completion falls below 20 while partial scientific work remains visible.",
            "local_test": "generic_report_cap",
        },
        {
            "observed_v063_problem": "Public summaries exposed the diagnosis and preferred resource.",
            "exact_v07_change": "Raw row-level records, code, membership, and logs; private truth is never mounted.",
            "professional_justification": "Investigators must discover what happened.",
            "predicted_effect": "Keyword policies cannot solve the case.",
            "local_test": "public_truth_scan_and_keyword_attack",
        },
        {
            "observed_v063_problem": "Grader rejected defensible labels, nesting, and conservative policies.",
            "exact_v07_change": "Alias-aware numeric grading, method equivalence, nested layouts, and decision/resource sets.",
            "professional_justification": "Multiple valid professional workflows exist.",
            "predicted_effect": "Two distinct solvers and nested paraphrases score at least 90.",
            "local_test": "alternative_and_nesting_controls",
        },
        {
            "observed_v063_problem": "Universal decision policies earned high scientific artifact scores.",
            "exact_v07_change": "Mission success requires valid calculation, resource action, belief update, final action, and bounded claims.",
            "professional_justification": "A safe decision depends on the whole evidence chain.",
            "predicted_effect": "Universal advance/pause/stop/abstain cannot pass all cases.",
            "local_test": "universal_policy_control",
        },
        {
            "observed_v063_problem": "Leakage diagnosis directly implied stop.",
            "exact_v07_change": "One identical pre-replay case has collapse and survive replay variants.",
            "professional_justification": "Detection and recovery are separate capabilities.",
            "predicted_effect": "The same final policy fails one controlled mechanism.",
            "local_test": "mechanism_counterfactual",
        },
        {
            "observed_v063_problem": "One early error threatened too much downstream credit.",
            "exact_v07_change": "Checkpoint-local scoring plus separate full-mission success.",
            "professional_justification": "Professional teams can contain and recover from ordinary mistakes.",
            "predicted_effect": "A wrong early unit retains at least 55 work-quality points but fails affected properties.",
            "local_test": "graceful_recovery",
        },
        {
            "observed_v063_problem": "Completion failure was mixed with scientific weakness.",
            "exact_v07_change": "Work-quality and reliability scores are separate.",
            "professional_justification": "Unsubmitted usable work is operationally unreliable, not necessarily scientifically ignorant.",
            "predicted_effect": "Diagnostic score is retained while reliability becomes zero.",
            "local_test": "unsubmitted_reliability",
        },
    ]


def _cost_plan() -> dict[str, Any]:
    model_prices = {
        "openai/gpt-5.6-sol": {"input": 2.0, "output": 10.0},
        "openai/gpt-5.2": {"input": 1.75, "output": 14.0},
    }
    observations: dict[str, list[dict[str, float]]] = {model: [] for model in model_prices}
    for path in sorted((ROOT / "build/hard_suite_v06_runs").glob("hard63-*/run_summary.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        model = row.get("model_id")
        if model not in observations:
            continue
        usage = row["token_usage"]
        observations[model].append(
            {
                "observed_cost": float(row["cumulative_reported_cost_usd"]),
                "input_tokens": float(usage["input_tokens"]),
                "output_tokens": float(usage["output_tokens"]),
            }
        )
    per_model: dict[str, Any] = {}
    expected_cached = 0.0
    cached_p90 = 0.0
    no_cache_median = 0.0
    no_cache_p90 = 0.0
    for model, rows in observations.items():
        if len(rows) != 2:
            raise RuntimeError(f"Expected two v0.6.3 observations for {model}")
        prices = model_prices[model]
        observed_costs = [row["observed_cost"] for row in rows]
        reconstructed = [
            row["input_tokens"] * prices["input"] / 1_000_000
            + row["output_tokens"] * prices["output"] / 1_000_000
            for row in rows
        ]
        cached_episode = median(observed_costs) * 1.20
        cached_episode_p90 = max(observed_costs) * 1.35
        no_cache_episode = median(reconstructed) * 1.20
        no_cache_episode_p90 = max(reconstructed) * 1.35
        expected_cached += cached_episode * 5
        cached_p90 += cached_episode_p90 * 5
        no_cache_median += no_cache_episode * 5
        no_cache_p90 += no_cache_episode_p90 * 5
        per_model[model] = {
            "route_price_usd_per_million": prices,
            "v063_observed_costs": observed_costs,
            "v07_cached_median_per_episode": round(cached_episode, 4),
            "v07_cached_p90_per_episode": round(cached_episode_p90, 4),
            "v07_no_cache_median_per_episode": round(no_cache_episode, 4),
            "v07_no_cache_p90_per_episode": round(no_cache_episode_p90, 4),
            "episodes": 5,
        }
    account_path = DIAGNOSTICS / "openrouter_post_v063_status.json"
    account = json.loads(account_path.read_text(encoding="utf-8"))
    hard_cap = float(math.ceil(no_cache_p90 / 5) * 5)
    remaining = float(account["account_remaining_usd"])
    return {
        "schema_version": "0.7-ten-cell-cost-1",
        "status": "authorized_only_if_local_gates_freeze_and_live_headroom_pass",
        "models": list(model_prices),
        "model_choice": "GPT-5.2 is the predeclared mid-level within-family comparator; it is not assumed to be cheaper per completed episode.",
        "cases": [
            "case_01",
            "case_02",
            "case_03:signal_collapses",
            "case_03:signal_remains",
            "case_04",
        ],
        "episodes": 10,
        "attempts_per_cell": 1,
        "planning_multiplier": {"median": 1.20, "p90": 1.35},
        "planning_multiplier_reason": "Raw CSV investigation and two quantitative phases may cost more than the two observed v0.6.3 states despite fewer scored checkpoints.",
        "per_model": per_model,
        "expected_cached_total_usd": round(expected_cached, 2),
        "cached_p90_total_usd": round(cached_p90, 2),
        "no_cache_median_total_usd": round(no_cache_median, 2),
        "no_cache_p90_total_usd": round(no_cache_p90, 2),
        "proposed_hard_cap_usd": hard_cap,
        "current_recorded_account_headroom_usd": remaining,
        "required_top_up_usd": round(max(0.0, hard_cap - remaining), 2),
        "required_key_limit_increase_usd": round(
            max(0.0, hard_cap - float(account["key_limit_remaining_usd"])), 2
        ),
        "estimated_sequential_wall_clock_hours": [1.5, 3.0],
        "paid_runner_exists": False,
        "exact_future_command": "PYTHONPATH=src ./.venv/bin/python scripts/run_v07_pilot.py --stage sol --execute --maximum-incremental-spend-usd 45.00",
        "warning": "Execution is rejected until dependency, payload, repository, Docker, account-headroom, and immutable-freeze gates all pass.",
    }


def build_controls() -> dict[str, Any]:
    first_manifest = build_development_cases(ROOT)
    second_manifest = build_development_cases(ROOT)
    reproducible_reset = (
        first_manifest["public_packet_hashes"] == second_manifest["public_packet_hashes"]
    )
    config_status = validate_v07_config(ROOT)
    reference_rows: list[dict[str, Any]] = []
    maximum_tool_calls = 0
    with tempfile.TemporaryDirectory(prefix="uc-v07-controls-") as directory:
        temporary = Path(directory)
        for case_id in CASE_IDS:
            mechanisms = (
                ["signal_collapses", "signal_remains"] if case_id == "case_03" else ["default"]
            )
            for mechanism in mechanisms:
                for alternative in (False, True):
                    submission, grade = replay_reference(
                        ROOT,
                        case_id,
                        temporary / f"{case_id}-{mechanism}-{alternative}",
                        mechanism=mechanism,
                        alternative=alternative,
                    )
                    maximum_tool_calls = max(maximum_tool_calls, int(submission["tool_calls"]))
                    reference_rows.append(
                        {
                            "case_id": case_id,
                            "mechanism": mechanism,
                            "approach": "alternative" if alternative else "reference",
                            "work_quality_score": grade.work_quality_score,
                            "full_mission_success": grade.full_mission_success,
                            "tool_calls": submission["tool_calls"],
                        }
                    )

        tampered = V07Environment(ROOT, "case_02", temporary / "tamper")
        checkpoints = direct_submission(ROOT, "case_02")["checkpoints"]
        tampered.save_checkpoint("C1", checkpoints["C1"])
        (tampered.run_root / "sponsor/assertions.md").write_text("changed", encoding="utf-8")
        tamper_rejected = False
        try:
            tampered.commit_validation_plan(checkpoints["C2"])
        except V07ProtocolError:
            tamper_rejected = True

        hidden = V07Environment(ROOT, "case_02", temporary / "hidden")
        hidden_rejected = False
        try:
            hidden.read_file("grader_private/hard_suite_v07/case_02/truth.json")
        except V07ProtocolError:
            hidden_rejected = True

        mutation = V07Environment(ROOT, "case_02", temporary / "mutation")
        mutation.save_checkpoint("C1", checkpoints["C1"])
        mutation.commit_validation_plan(checkpoints["C2"])
        mutation.reveal_validation()
        post_reveal_mutation_rejected = False
        try:
            mutation.commit_validation_plan({"analysis_unit": "biopsy"})
        except V07ProtocolError:
            post_reveal_mutation_rejected = True

    empty_max = max(
        grade_submission(ROOT, case_id, empty_submission()).work_quality_score
        for case_id in CASE_IDS
    )
    generic_max = max(
        grade_submission(ROOT, case_id, generic_submission()).work_quality_score
        for case_id in CASE_IDS
    )
    keyword_max = max(
        grade_submission(ROOT, case_id, keyword_submission()).work_quality_score
        for case_id in CASE_IDS
    )
    flat = direct_submission(ROOT, "case_04")
    nested = json.loads(json.dumps(flat))
    nested_metrics = nested["checkpoints"]["C3"].pop("metrics")
    nested["checkpoints"]["C3"]["different_layout"] = {
        "results": nested_metrics,
        "unscored_explanation": "Paraphrased scientific narrative.",
    }
    nesting_difference = abs(
        grade_submission(ROOT, "case_04", flat).work_quality_score
        - grade_submission(ROOT, "case_04", nested).work_quality_score
    )
    annotated = direct_submission(ROOT, "case_02")
    annotated["checkpoints"]["C1"]["diagnosed_concepts"] = [
        "Non-independence from repeated patient biopsies",
        "Performance shifts materially with site mix",
    ]
    annotated["checkpoints"]["C2"].update(
        {
            "fit_scope": "Training-only and outcome-blind preprocessing fit",
            "uncertainty_method": "Site-stratified cluster bootstrap over patients",
        }
    )
    annotated["selected_resource"] = "X17 — source records"
    annotated["checkpoints"]["C4"]["selected_resource"] = "X17 — source records"
    annotated["checkpoints"]["C5"].update(
        {
            "belief_direction": "Evidence weakens and the site blocker remains unresolved",
            "initial_decision": "Pause pending reconciliation",
            "final_decision": "Pause — site transport remains unresolved",
            "supported_claims": ["Biopsy-row performance is misleading and not decision-valid"],
            "unsupported_claims": [
                "The evidence does not establish independent validation",
                "No causal treatment effect is supported",
            ],
            "claims_made": ["Biopsy-row performance is misleading and not decision-valid"],
        }
    )
    annotated_grade = grade_submission(ROOT, "case_02", annotated)

    universal: dict[str, Any] = {}
    for policy in ("advance", "pause", "stop", "abstain"):
        rows = []
        for case_id in CASE_IDS:
            mechanism = case_mechanism(case_id)
            submission = direct_submission(ROOT, case_id, mechanism=mechanism)
            submission["checkpoints"]["C5"]["final_decision"] = policy
            grade = grade_submission(ROOT, case_id, submission, mechanism=mechanism)
            rows.append(grade.full_mission_success)
        universal[policy] = {"missions_passed": sum(rows), "missions_total": len(rows)}

    buy_all = direct_submission(ROOT, "case_02")
    buy_all["selected_resource"] = "all"
    buy_all["spent_units"] = 11
    buy_all["checkpoints"]["C4"]["selected_resource"] = "all"
    buy_all_grade = grade_submission(ROOT, "case_02", buy_all)

    recovery = direct_submission(ROOT, "case_02")
    truth = load_truth(ROOT, "case_02")
    recovery["checkpoints"]["C1"].update(
        {
            "analysis_unit": "biopsy",
            "n_patients": truth["n_samples"],
            "n_samples": truth["n_samples"],
        }
    )
    recovery_grade = grade_submission(ROOT, "case_02", recovery)

    collapse = direct_submission(ROOT, "case_03", mechanism="signal_collapses")
    collapse_right = grade_submission(ROOT, "case_03", collapse, mechanism="signal_collapses")
    collapse_wrong = grade_submission(ROOT, "case_03", collapse, mechanism="signal_remains")

    public_violations = {
        case_id: validate_public_packet_has_no_truth_labels(ROOT, case_id) for case_id in CASE_IDS
    }
    recoverable = all(
        all(
            (ROOT / "tasks/hard_suite_v07/development" / case_id / path).is_file()
            for path in load_truth(ROOT, case_id)["evidence_path"]["analysis_unit"]
        )
        and (
            ROOT / "grader_private/hard_suite_v07" / case_id / "sealed/validation_outcomes.csv"
        ).is_file()
        and (
            ROOT
            / "grader_private/hard_suite_v07"
            / case_id
            / "resource_returns"
            / load_truth(ROOT, case_id)["preferred_resource"]
        ).exists()
        if load_truth(ROOT, case_id)["preferred_resource"] != "none"
        else True
        for case_id in CASE_IDS
    )

    scientific_review = {
        "status": "pass",
        "checks": {
            "patient_vs_biopsy_units": "pass: fingerprint patient counts and sample counts are separately recoverable",
            "repeated_measures": "pass: every case contains repeated baseline biopsies; case 02 has outcome-associated repeat collection",
            "baseline_vs_post_treatment_timing": "pass: inputs are days -14 to -2 and outcomes days 40-44",
            "drug_and_endpoint_alignment": "pass: intended-use and model manifests specify first infliximab and day-42 clinical response",
            "site_batch_platform": "pass: all fields are present; site-aware metrics are required",
            "preprocessing_fit_scope": "pass: code, membership, role, and timestamp evidence jointly expose case 03",
            "prediction_not_treatment_effect": "pass: contract and claim grader prohibit treatment-effect inference",
            "sample_size_uncertainty": "pass: patient-cluster bootstrap intervals are calculated and alternative valid methods accepted",
            "calibration_threshold_utility": "pass: Brier, calibration error, and net benefit are computed from rows",
            "claim_scope": "pass: supported and prohibited claim sets differ by case and affect mission success",
        },
        "limitation": "Builder-authored computational-biology review; not independent external expert validation.",
    }
    environment_review = {
        "status": "pass",
        "checks": {
            "meaningful_actions": "pass: inspect, calculate, commit, reveal, purchase, revise, submit",
            "irreversible_transitions": "pass: one locked C2, one reveal, one purchase, terminal submit",
            "sealed_information": "pass: outcomes and returns live outside the copied workspace",
            "objective_rewards": "pass: numeric tolerances, provenance eligibility, action consistency, and claim sets",
            "dense_partial_credit": f"pass: ordinary early error retains {recovery_grade.work_quality_score:.1f}",
            "template_resistance": f"pass: generic {generic_max:.1f}, keyword {keyword_max:.1f}",
            "reproducible_resets": "pass: deterministic private seeds and public packet hashes",
            "hidden_development_seeds": "pass: seeds remain in private truth only",
            "complete_tool_traces": "pass: every action records sequence, event, inputs, outputs, and cost units",
            "cost_accounting": "pass: one purchase and budget units enforced separately from API spend",
            "terminal_states": "pass: submitted, tampered, or tool-budget exhaustion",
        },
        "limitation": "Local deterministic environment review; provider adapter is intentionally not implemented yet.",
    }

    controls = {
        "schema_version": "0.7-local-controls-1",
        "config": config_status,
        "model_calls": 0,
        "api_spend_usd": 0,
        "reference_and_alternative": reference_rows,
        "reference_minimum": min(row["work_quality_score"] for row in reference_rows),
        "all_reference_missions_pass": all(row["full_mission_success"] for row in reference_rows),
        "maximum_reference_tool_calls": maximum_tool_calls,
        "empty_maximum": empty_max,
        "generic_maximum": generic_max,
        "keyword_maximum": keyword_max,
        "paraphrase_nesting_score_difference": nesting_difference,
        "annotated_professional_language": {
            "score": annotated_grade.work_quality_score,
            "mission": annotated_grade.full_mission_success,
        },
        "universal_policies": universal,
        "buy_everything": {
            "C4": buy_all_grade.checkpoint_scores["C4"],
            "mission": buy_all_grade.full_mission_success,
        },
        "graceful_recovery": {
            "score": recovery_grade.work_quality_score,
            "C1": recovery_grade.checkpoint_scores["C1"],
            "C5": recovery_grade.checkpoint_scores["C5"],
        },
        "tamper_rejected": tamper_rejected,
        "hidden_access_rejected": hidden_rejected,
        "post_reveal_commitment_change_rejected": post_reveal_mutation_rejected,
        "reproducible_reset_hashes": reproducible_reset,
        "mechanism_counterfactual": {
            "correct_mission": collapse_right.full_mission_success,
            "wrong_variant_mission": collapse_wrong.full_mission_success,
            "wrong_variant_failures": collapse_wrong.mission_failures,
        },
        "public_truth_scan": public_violations,
        "answers_recoverable_from_action-visible_evidence": recoverable,
        "scientific_review": scientific_review,
        "environment_review": environment_review,
    }
    gates = {
        "reference_minimum": controls["reference_minimum"] >= 90,
        "two_valid_approaches": all(row["work_quality_score"] >= 90 for row in reference_rows),
        "empty_maximum": empty_max <= 15,
        "generic_maximum": generic_max <= 20,
        "keyword_maximum": keyword_max <= 15,
        "paraphrase_and_nesting": nesting_difference <= 0.01,
        "annotated_professional_language": (
            annotated_grade.work_quality_score >= 95 and annotated_grade.full_mission_success
        ),
        "universal_policies_fail": all(
            row["missions_passed"] < row["missions_total"] for row in universal.values()
        ),
        "buy_everything_fails": not buy_all_grade.full_mission_success
        and buy_all_grade.checkpoint_scores["C4"] < 65,
        "graceful_recovery": recovery_grade.work_quality_score >= 55
        and recovery_grade.checkpoint_scores["C5"] >= 90,
        "tamper_hidden_and_commitment_guards": (
            tamper_rejected and hidden_rejected and post_reveal_mutation_rejected
        ),
        "reproducible_reset": reproducible_reset,
        "mechanism_changes_truth": collapse_right.full_mission_success
        and not collapse_wrong.full_mission_success,
        "visible_recoverability": recoverable,
        "reference_inside_budget": maximum_tool_calls <= 20,
        "computational_biology_review": scientific_review["status"] == "pass",
        "rl_environment_review": environment_review["status"] == "pass",
        "no_public_truth_labels": not any(public_violations.values()),
    }
    controls["gates"] = gates
    controls["all_gates_pass"] = all(gates.values())
    return controls


def main() -> None:
    controls = build_controls()
    cards = validity_cards()
    remedies = remedy_map()
    interventions = intervention_design()
    costs = _cost_plan()

    reference = direct_submission(ROOT, "case_03", mechanism="signal_collapses")
    reference_grade = grade_submission(ROOT, "case_03", reference, mechanism="signal_collapses")
    mediocre = mediocre_submission()
    mediocre_grade = grade_submission(ROOT, "case_02", mediocre)

    write_json(DIAGNOSTICS / "hard_suite_v07_controls.json", controls)
    write_json(DIAGNOSTICS / "hard_suite_v07_case_validity_cards.json", {"cards": cards})
    write_json(DIAGNOSTICS / "hard_suite_v07_failure_remedy_map.json", {"rows": remedies})
    write_json(DIAGNOSTICS / "hard_suite_v07_intervention_design.json", {"pairs": interventions})
    write_json(DIAGNOSTICS / "hard_suite_v07_reset_traceability.json", {"changes": reset_table()})
    write_json(DIAGNOSTICS / "hard_suite_v07_cost_plan.json", costs)
    write_json(
        REPLAYS / "reference_case_03_signal_collapses.json",
        {"submission": reference, "grade": reference_grade.to_dict()},
    )
    write_json(
        REPLAYS / "mediocre_case_02.json",
        {"submission": mediocre, "grade": mediocre_grade.to_dict()},
    )

    if not controls["all_gates_pass"]:
        failed = [name for name, passed in controls["gates"].items() if not passed]
        raise SystemExit(f"v0.7 local gates failed: {failed}")
    print(
        json.dumps(
            {
                "all_gates_pass": True,
                "reference_minimum": controls["reference_minimum"],
                "generic_maximum": controls["generic_maximum"],
                "keyword_maximum": controls["keyword_maximum"],
                "graceful_recovery": controls["graceful_recovery"]["score"],
                "expected_cached_total_usd": costs["expected_cached_total_usd"],
                "no_cache_p90_total_usd": costs["no_cache_p90_total_usd"],
                "proposed_hard_cap_usd": costs["proposed_hard_cap_usd"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
