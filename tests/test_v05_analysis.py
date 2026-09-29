"""Analysis-only regression tests for the BixBench3-informed v0.5 report."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import analyze_v05_extended as analysis  # noqa: E402


def test_artifact_dag_is_acyclic_and_depth_ordered() -> None:
    nodes = {node["artifact_id"]: node for node in analysis.ARTIFACT_DAG}
    for node in nodes.values():
        for parent in node["depends_on"]:
            assert parent in nodes
            assert nodes[parent]["depth"] < node["depth"]


def test_semantic_contract_match_accepts_professional_paraphrase() -> None:
    expected = "adults_with_moderate_to_severe_ulcerative_colitis_starting_first_anti_tnf"
    observed = (
        "Adults with moderate-to-severe ulcerative colitis starting first anti-TNF "
        "(infliximab)"
    )
    assert analysis._semantic_contract_match(observed, expected)
    assert not analysis._semantic_contract_match("adults with Crohn disease", expected)


def test_dependency_divergence_preserves_graceful_downstream_credit() -> None:
    milestones = {f"M{index:02d}": 100.0 for index in range(1, 11)}
    milestones["M03"] = 60.0
    result = analysis._dependency_analysis(milestones)
    first = result["first_substantive_divergence"]
    assert first["milestone"] == "M03"
    divergence = result["divergences"][0]
    assert "A07" in divergence["downstream_artifacts_at_risk"]
    assert divergence["mechanically_invalidated"] == []


def test_every_annotation_requires_concrete_evidence() -> None:
    try:
        analysis._annotation("tag", "process", "description", [])
    except ValueError as error:
        assert "requires concrete evidence" in str(error)
    else:
        raise AssertionError("Evidence-free annotation should be rejected")


def test_vocabulary_audit_flags_semantically_valid_fingerprint_unit_without_rescoring() -> None:
    record = {
        "commitment": {
            "plan": {
                "analysis_unit": "fingerprint_group",
                "uncertainty_unit": "fingerprint_group bootstrap",
                "preprocessing_fit_scope": "frozen transforms fitted on DISCOVERY-01 only",
            }
        }
    }
    audit = analysis._frozen_grader_vocabulary_audit(record)
    assert audit["flag_count"] == 3
    assert audit["rescore_applied"] is False


def test_incomplete_matrix_cannot_pass_acceptance() -> None:
    result = analysis._acceptance([], [], {}, 18)
    assert result["evaluated"] is False
    assert result["planned_rows"] == 18
