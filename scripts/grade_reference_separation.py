#!/usr/bin/env python3
"""Grade expert and deliberately mediocre attempts on the identical result."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

from uc_bench.grading import ScenarioRubric, grade_episode
from uc_bench.hashing import canonical_sha256, hash_artifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    reward = read_json(PROJECT_ROOT / "configs" / "reward_weights.json")
    rubric = ScenarioRubric.from_dict(
        read_json(PROJECT_ROOT / "configs" / "authentic_rubric.json")
    )
    expert_record = read_json(
        PROJECT_ROOT / "artifacts" / "reference" / "environment_episode.json"
    )
    expert = grade_episode(
        expert_record,
        workspace_root=PROJECT_ROOT / "build" / "reference_replay" / "full_data",
        rubric=rubric,
        weights=reward["weights"],
        soft_contract_failure_ceiling=float(reward["soft_contract_failure_ceiling"]),
    )
    mediocre = grade_episode(
        read_json(PROJECT_ROOT / "artifacts" / "reference" / "mediocre_episode.json"),
        workspace_root=PROJECT_ROOT,
        rubric=rubric,
        weights=reward["weights"],
        soft_contract_failure_ceiling=float(reward["soft_contract_failure_ceiling"]),
    )
    separation = expert.score - mediocre.score
    if separation < 30.0:
        raise RuntimeError(f"Expert separation is too small: {separation:.2f}")
    keyword_record = copy.deepcopy(expert_record)
    keyword_record["commitment"]["artifact_paths"] = []
    keyword_record["committed_artifact_hashes"] = {}
    keyword_record["submission"]["evidence_artifact_paths"] = []
    keyword_only = grade_episode(
        keyword_record,
        workspace_root=PROJECT_ROOT / "build" / "reference_replay" / "full_data",
        rubric=rubric,
        weights=reward["weights"],
        soft_contract_failure_ceiling=float(reward["soft_contract_failure_ceiling"]),
    )
    hard_invalid = grade_episode(
        expert_record,
        workspace_root=PROJECT_ROOT / "build" / "reference_replay" / "full_data",
        rubric=rubric,
        weights=reward["weights"],
        hard_invalid_actions=("access_sealed_outcomes",),
        soft_contract_failure_ceiling=float(reward["soft_contract_failure_ceiling"]),
    )
    wrong_decision_record = copy.deepcopy(expert_record)
    wrong_decision_record["submission"]["decision"] = "advance"
    wrong_decision = grade_episode(
        wrong_decision_record,
        workspace_root=PROJECT_ROOT / "build" / "reference_replay" / "full_data",
        rubric=rubric,
        weights=reward["weights"],
        soft_contract_failure_ceiling=float(reward["soft_contract_failure_ceiling"]),
        incorrect_terminal_decision_ceiling=float(
            reward["incorrect_terminal_decision_ceiling"]
        ),
    )
    if wrong_decision.score > float(reward["incorrect_terminal_decision_ceiling"]):
        raise RuntimeError("Incorrect terminal decision escaped the public score ceiling")
    if keyword_only.score > float(reward["soft_contract_failure_ceiling"]):
        raise RuntimeError("Keyword-only control escaped the soft contract ceiling")
    if hard_invalid.score != 0.0:
        raise RuntimeError("Hard invalidation control did not receive zero")

    forged_root = PROJECT_ROOT / "build" / "grader_controls" / "structured_forgery"
    if forged_root.exists():
        shutil.rmtree(forged_root)
    shutil.copytree(
        PROJECT_ROOT / "build" / "reference_replay" / "full_data",
        forged_root,
    )
    forged_evidence_path = forged_root / "submission" / "development_evidence.json"
    forged_evidence = read_json(forged_evidence_path)
    forged_evidence["audit_checks"]["platform_alignment"]["common_gene_count"] = 999_999
    forged_evidence["audit_checks"]["negative_control"]["p_value"] = 0.0
    forged_evidence["development_results"]["replication"]["auc"] = 1.0
    forged_evidence["development_results"]["replication"]["auc_interval"] = [1.0, 1.0]
    write_json(forged_evidence_path, forged_evidence)

    forged_record = copy.deepcopy(expert_record)
    forged_artifact_paths = tuple(forged_record["commitment"]["artifact_paths"])
    forged_hashes = hash_artifacts(forged_root, forged_artifact_paths)
    forged_record["committed_artifact_hashes"] = forged_hashes
    forged_record["commitment_digest"] = canonical_sha256(
        {
            "commitment": forged_record["commitment"],
            "artifact_hashes": forged_hashes,
        }
    )
    forged_record["events"][0]["payload_digest"] = canonical_sha256(
        {"commitment_digest": forged_record["commitment_digest"]}
    )
    structured_forgery = grade_episode(
        forged_record,
        workspace_root=forged_root,
        rubric=rubric,
        weights=reward["weights"],
        soft_contract_failure_ceiling=float(reward["soft_contract_failure_ceiling"]),
    )
    if structured_forgery.contract_valid or structured_forgery.score > float(
        reward["soft_contract_failure_ceiling"]
    ):
        raise RuntimeError("Structured evidence forgery escaped fail-closed grading")
    expected_false_claims = {"negative_control", "platform_alignment", "uncertainty"}
    if not expected_false_claims <= set(
        structured_forgery.checks.get("false_pass_claims", [])
    ):
        raise RuntimeError("Structured evidence forgery was not independently detected")
    result = {
        "schema_version": "0.1",
        "same_predictor_and_validation_result": True,
        "expert": expert.to_dict(),
        "mediocre": mediocre.to_dict(),
        "keyword_only_control": keyword_only.to_dict(),
        "structured_forgery_control": structured_forgery.to_dict(),
        "hard_invalidation_control": hard_invalid.to_dict(),
        "incorrect_terminal_decision_control": wrong_decision.to_dict(),
        "score_separation": separation,
        "minimum_required_separation": 30.0,
        "passed": True,
    }
    output = PROJECT_ROOT / "artifacts" / "grading" / "reference_separation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
