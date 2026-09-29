from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = PROJECT_ROOT / "tasks" / "uc_biomarker_diligence_v0" / "schemas"
EXPERT_ROOT = PROJECT_ROOT / "build" / "reference_replay" / "full_data" / "submission"


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_reference_artifacts_satisfy_public_schemas() -> None:
    artifacts = {
        "model.schema.json": "model.json",
        "predictor_manifest.schema.json": "predictor_manifest.json",
        "analysis_evidence.schema.json": "development_evidence.json",
        "commitment.schema.json": "commitment.json",
        "final_submission.schema.json": "final_submission.json",
    }
    for schema_name, artifact_name in artifacts.items():
        schema = read_json(SCHEMA_ROOT / schema_name)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(read_json(EXPERT_ROOT / artifact_name))


def test_public_vocabulary_covers_private_authentic_rubric() -> None:
    schema = read_json(SCHEMA_ROOT / "final_submission.schema.json")
    properties = schema["properties"]
    rubric = read_json(PROJECT_ROOT / "configs" / "authentic_rubric.json")
    assert set(rubric["expected_diagnostic_codes"]) <= set(
        properties["diagnostic_codes"]["items"]["enum"]
    )
    assert set(rubric["accepted_failure_modes"]) <= set(
        properties["failure_mode"]["enum"]
    )
    assert set(rubric["accepted_next_action_types"]) <= set(
        properties["next_action_type"]["enum"]
    )


def test_public_evidence_schema_names_every_recomputed_field() -> None:
    rendered = json.dumps(read_json(SCHEMA_ROOT / "analysis_evidence.schema.json"))
    required_fields = {
        "cohorts",
        "endpoint_mismatch",
        "drug_transfer",
        "strategy",
        "platforms_are_distinct",
        "common_gene_count",
        "untouched_replication",
        "replication_used_during_fit",
        "replication_label_permutation",
        "permutation_count",
        "p_value",
        "stratified_bootstrap",
        "discovery_seed",
        "replication_seed",
        "auc_interval",
    }
    assert all(field in rendered for field in required_fields)
