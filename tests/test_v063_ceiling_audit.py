from __future__ import annotations

from pathlib import Path

from uc_bench.v063_ceiling_audit import build_v063_ceiling_audit

ROOT = Path(__file__).resolve().parents[1]


def test_audit_covers_every_frozen_cell_and_artifact_without_rescoring() -> None:
    audit = build_v063_ceiling_audit(ROOT)
    assert audit["sentinel"]["cell_count"] == 10
    assert audit["sentinel"]["valid_episode_count"] == 9
    assert all(len(cell["artifacts"]) == 10 for cell in audit["cells"])
    assert audit["frozen_result_policy"]["v063_rescored"] is False
    assert audit["frozen_result_policy"]["heldout_or_astra_used"] is False


def test_audit_identifies_ceiling_and_shallow_policy_failures() -> None:
    audit = build_v063_ceiling_audit(ROOT)
    assert audit["verdict"]["decision"] == "no_go_preserve_v063"
    assert audit["artifact_analysis"]["A06"]["mean"] == 100
    assert audit["shallow_policy_diagnostic"]["conclusion"] == "yes_excessive_credit"
    assert audit["sentinel"]["diagnostic_scientific_mean_by_model"]["openai/gpt-5.6-sol"] > 80


def test_unresolved_discovery_count_is_not_called_model_science_error() -> None:
    audit = build_v063_ceiling_audit(ROOT)
    matching = [
        deduction
        for cell in audit["cells"]
        for artifact in cell["artifacts"]
        for deduction in artifact["deductions"]
        if artifact["artifact_id"] == "A01"
        and deduction["invariant"] == "row_and_patient_counts_reconciled"
        and deduction["adjudication"] == "E"
    ]
    assert len(matching) >= 5
