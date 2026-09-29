"""Unfrozen Case 2 RC1 environment with the unchanged evidence/action surface."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc3_tools import case1_tool_definitions
from uc_bench.case2_pilot_v1_rc1_contract import (
    PUBLIC_CONTRACT,
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.mmmvp_open_environment import (
    OpenProtocolError,
    _decode,
    _digest_bytes,
    _json_digest,
)
from uc_bench.mmmvp_open_rc12_environment import RC12OpenMMMVPEnvironment

MISSION = """# Locked predictor diligence: Case 2

Determine what the supplied evidence supports for the stated multi-site intended use,
whether one follow-up purchase has value for one explicitly defined unresolved question,
and what bounded development action should follow.

Outcomes are sealed. Before reveal, commit a complete provisional-unit cohort manifest,
an outcome-blind dependence strategy, estimators, important parameters, uncertainty,
and non-vacuous primary and context criteria. Neither supplied identity field is
automatically canonical person truth.

After reveal, save every decision-driving table and calculation under work/. Report
site-level counts, evaluability and estimates for the context criterion. After the one
resource action, revise the same hypotheses and submit an evidence-bounded decision.

This is one autonomous mission. Continue through every irreversible stage and finish
with a contract-valid submit call. No later user confirmation will be provided.
"""

FIELD_GUIDE = """# Case 2 field guide

`source_record_id`/`sample_id` denotes one biopsy. `fingerprint_cluster` is an
outcome-blind provisional dependence unit. `reported_patient_id` is a supplied identifier
whose consistency must be investigated. Neither identity field is adjudicated person
truth before a returned identity package establishes it.

The prospective manifest has exactly `entity_id,source_record_ids,included,`
`preoutcome_exclusion_reason`. It lists every baseline-eligible provisional fingerprint
unit once. A valid primary workflow may aggregate within those units or retain biopsy
rows with cluster-aware weights and uncertainty. Reported-patient grouping is a
sensitivity analysis, not a primary canonical-person analysis.

Commit exactly one criterion for discrimination, probability accuracy, calibration and
threshold utility, plus either or both context criteria. `SITE_WEIGHTED_ROC_AUC` requires
a threshold of at least 0.65; `WORST_SITE_ROC_AUC` requires at least 0.55. Save each
site's source-row count, analysis-row count, entity count, evaluability and ROC AUC in
the context calculation output. A one-class or silently omitted intended-use site makes
general multi-site advancement not evaluable; it does not erase unrelated calculations.

The follow-up question maps technically to one catalogue resource, but no resource is
preferred. X17 can adjudicate identity, X46 can address a declared transport question,
and `none` can be correct when current evidence already resolves the immediate bounded
decision. Returned evidence must be hashed, recomputed and linked to belief revision.

General multi-site continuation requires every committed primary/context criterion to
pass. After context failure or non-evaluability, PAUSE or INSUFFICIENT_EVIDENCE may hold
the claim; STOP needs valid invalidating evidence. CONTINUE remains possible only for a
targeted context investigation that prohibits current multi-site probability use and
does not claim transport or independent validation. Continuing an investigation is not
advancing the predictor.

Free text is retained for professional audit but never exact-matched or scored. Enums,
hashes, calculations, identity bases, action scope and event timing are machine checked.
"""

IDENTITY_PROVENANCE = {
    "schema_version": "case2-provisional-identity-1",
    "source_record_id": {
        "field": "data/cohort_metadata.csv:sample_id",
        "meaning": "one biopsy record",
        "canonical_person_truth": False,
    },
    "fingerprint_cluster": {
        "field": "data/cohort_metadata.csv:fingerprint_cluster",
        "meaning": "provisional dependence/linkage unit derived without outcomes",
        "canonical_person_truth": False,
        "outcome_blind": True,
    },
    "reported_patient_id": {
        "field": "data/cohort_metadata.csv:reported_patient_id",
        "meaning": "supplied identifier whose consistency must be investigated",
        "canonical_person_truth": False,
    },
    "claim_rule": (
        "A provisional-unit count is not an adjudicated patient count. An adjudicated-person "
        "claim requires returned identity evidence and a saved analysis using that mapping."
    ),
}

VALIDATION_MANIFEST = {
    "commitment_required_before_reveal": True,
    "outcomes_sealed": True,
    "predictions_locked": True,
    "outcome_binding": (
        "After reveal, outcome keys attach to the supplied provisional linkage units; "
        "they do not adjudicate canonical person identity."
    ),
}

SCIENTIFIC_METHODS = {
    "dependence": [
        "MEAN, MEDIAN or FIRST aggregation within provisional fingerprint units",
        "source rows with ENTITY_WEIGHTED estimation and cluster bootstrap",
    ],
    "reported_identifier": ["labelled sensitivity analysis only before adjudication"],
    "discrimination": ["ROC_AUC", "BINARY_CONCORDANCE"],
    "probability_accuracy": ["BRIER_SCORE", "LOG_LOSS"],
    "calibration": ["CALIBRATION_ERROR with 2-20 committed equal-width bins"],
    "threshold_utility": ["NET_BENEFIT", "THRESHOLD_EXPECTED_UTILITY"],
    "context_robustness": ["SITE_WEIGHTED_ROC_AUC", "WORST_SITE_ROC_AUC"],
    "uncertainty": [
        "ENTITY_BOOTSTRAP_PERCENTILE for one-row-per-provisional-unit tables",
        "CLUSTER_BOOTSTRAP_PERCENTILE for retained source rows",
    ],
    "multi_context_identity": (
        "Do not assign one invented site to an adjudicated multi-context person. Retain the "
        "prospective provisional context analysis or use canonical-person-weighted source rows."
    ),
    "deterministic_details": {
        "FIRST": (
            "Sort source_record_id lexicographically within each declared entity and use the "
            "first locked prediction."
        ),
        "ENTITY_WEIGHTED": (
            "Each source row receives weight 1 divided by its entity's source-row count, so "
            "each entity has total weight one in metrics and bootstrap resamples."
        ),
        "SITE_WEIGHTED_ROC_AUC": (
            "Calculate AUC separately in every evaluable site using the declared entity "
            "weights, then average site AUCs weighted by each site's total entity weight."
        ),
        "WORST_SITE_ROC_AUC": "The minimum AUC across every evaluable intended-use site.",
        "post_X17_outcomes": (
            "Attach each sealed provisional-unit outcome to its source records through the "
            "published fingerprint field, then aggregate only when all source-linked outcomes "
            "within the adjudicated person agree. Conflicting outcomes make that person-level "
            "analysis non-evaluable and must be reported, not silently resolved. When they "
            "agree, apply the same prospectively committed aggregation or weighted-row rule "
            "to the remapped source records."
        ),
    },
}

DEVELOPMENT_ACTION_CONTRACT = {
    "schema_version": "case2-development-actions-1",
    "commitment_timing": "criteria and result-contingent actions are committed before use",
    "actions": {
        "CONTINUE": (
            "Either bounded general advancement after all criteria pass, or a targeted "
            "investigation after context failure with current multi-site use prohibited."
        ),
        "PAUSE": "Hold the current advancement claim while a concrete gate remains unresolved.",
        "INSUFFICIENT_EVIDENCE": (
            "Make no directional advancement claim when evidence cannot resolve it."
        ),
        "STOP": "End the path only when valid evidence establishes it is not worthwhile.",
    },
    "no_preferred_disposition": True,
}


def _validator_source() -> str:
    return '''#!/usr/bin/env python3
"""Agent-visible structural validator for the Case 2 candidate."""
import json
import pathlib
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "public_support"))
from uc_bench.case2_pilot_v1_rc1_contract import validate_payload

if len(sys.argv) != 3:
    raise SystemExit(
        "usage: validate_contract.py validation_plan|followup_plan|final_submission PATH"
    )
kind, relative = sys.argv[1], sys.argv[2]
path = pathlib.Path(relative)
payload = json.loads(path.read_text(encoding="utf-8"))
result = validate_payload(kind, payload)
print(json.dumps({
    "valid": result.valid,
    "issues": [row.to_dict() for row in result.issues],
}, indent=2))
raise SystemExit(0 if result.valid else 1)
'''


def _science_validator_source() -> str:
    return '''#!/usr/bin/env python3
"""Agent-visible scientific validator using the same Case 2 semantic engine."""
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(root / "public_support"))
from uc_bench.case2_pilot_v1_rc1_semantics import evaluate_case2_submission

records = root / "work"
payload = {
    "validation_plan": json.loads((records / "validation_plan.json").read_text()),
    "followup_plan": json.loads((records / "followup_plan.json").read_text()),
    "final_submission": json.loads((records / "final_submission.json").read_text()),
    "state": {"completion_accepted": True},
}
committed = set(payload["validation_plan"].get("evidence_refs") or [])
for row in payload["validation_plan"].get("planned_analyses") or []:
    committed.update(row.get("input_paths") or [])
committed.add(payload["validation_plan"]["prospective_specification"]["eligible_entity_manifest_path"])
payload["validation_input_hashes"] = {
    relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
    for relative in sorted(committed)
}
grade = evaluate_case2_submission(root, payload, require_host_process=False)
print(json.dumps(grade.to_dict(), indent=2, sort_keys=True))
raise SystemExit(0 if grade.complete_mission_success else 1)
'''


PUBLIC_SUPPORT_MODULES = (
    "case2_pilot_v1_rc1_contract.py",
    "case2_pilot_v1_rc1_semantics.py",
    "case1_pilot_v1_rc5_contract.py",
    "case1_pilot_v1_rc5_cohort.py",
    "case1_pilot_v1_rc5_normalization.py",
    "case1_pilot_v1_rc5_public_recompute.py",
    "case1_pilot_v1_rc4_contract.py",
    "mmmvp_open_rc17_contract.py",
    "mmmvp_open_rc14_contract.py",
    "mmmvp_open_schema.py",
    "mmmvp_open_calculations.py",
)


class Case2PilotRC1Environment(RC12OpenMMMVPEnvironment):
    """Same five irreversible actions, with the disclosed Case 2 contract."""

    def __init__(self, project_root: Path, run_root: Path, *, maximum_tool_calls: int = 80) -> None:
        super().__init__(
            project_root,
            "case_02",
            run_root,
            mechanism="default",
            maximum_tool_calls=maximum_tool_calls,
        )
        self._write_candidate_contract()
        self._protected_evidence_hashes = self._workspace_hashes()
        self._start_hashes = dict(self._protected_evidence_hashes)

    def _write_candidate_contract(self) -> None:
        (self.run_root / "MISSION.md").write_text(MISSION, encoding="utf-8")
        (self.run_root / "field_guide.md").write_text(FIELD_GUIDE, encoding="utf-8")
        for name, value in (
            ("submission_contract.json", PUBLIC_CONTRACT),
            ("identity_provenance.json", IDENTITY_PROVENANCE),
            ("validation_manifest.json", VALIDATION_MANIFEST),
            ("scientific_methods.json", SCIENTIFIC_METHODS),
            ("development_action_contract.json", DEVELOPMENT_ACTION_CONTRACT),
            ("tool_interface.json", case1_tool_definitions()),
        ):
            (self.run_root / name).write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        (self.run_root / "validate_contract.py").write_text(_validator_source(), encoding="utf-8")
        (self.run_root / "validate_science.py").write_text(
            _science_validator_source(), encoding="utf-8"
        )
        support = self.run_root / "public_support/uc_bench"
        support.mkdir(parents=True, exist_ok=True)
        (support / "__init__.py").write_text("", encoding="utf-8")
        source = self.project_root / "src/uc_bench"
        for filename in PUBLIC_SUPPORT_MODULES:
            shutil.copy2(source / filename, support / filename)

    def _commit_record(self, name: str, payload: dict[str, Any]) -> str:
        path = self.records_root / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return _json_digest(payload)

    def commit_validation_plan(self, payload_json: str) -> dict[str, Any]:
        self._count_tool()
        self._assert_untampered()
        if self.state.phase != "investigate":
            raise OpenProtocolError("Validation plan can be committed exactly once before reveal")
        payload = _decode(payload_json)
        result = validate_validation_plan(payload)
        if not result.valid:
            issues = [row.to_dict() for row in result.issues]
            self._record("validation_plan_rejected", schema_issues=issues)
            return {"accepted": False, "schema_issues": issues}
        committed_paths = {
            str(path)
            for analysis in payload["planned_analyses"]
            for path in analysis["input_paths"]
        } | {str(path) for path in payload["evidence_refs"]}
        committed_paths.add(payload["prospective_specification"]["eligible_entity_manifest_path"])
        invalid: list[str] = []
        hashes: dict[str, str] = {}
        for relative in sorted(committed_paths):
            if relative.startswith(("revealed/", "purchased/")):
                invalid.append(relative)
                continue
            try:
                path = self._safe_visible_path(relative)
            except OpenProtocolError:
                invalid.append(relative)
                continue
            if not path.is_file():
                invalid.append(relative)
            else:
                hashes[relative] = _digest_bytes(path.read_bytes())
        if invalid:
            issues = [
                {
                    "path": "planned pre-reveal inputs",
                    "code": "pre_reveal_file_required",
                    "message": "Every committed input must already exist and be visible",
                    "invalid_paths": invalid,
                }
            ]
            self._record("validation_plan_rejected", schema_issues=issues)
            return {"accepted": False, "schema_issues": issues}
        self.state.validation_plan_hash = self._commit_record("validation_plan.json", payload)
        (self.records_root / "validation_input_hashes.json").write_text(
            json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self._validation_input_hashes = hashes
        self.state.phase = "committed"
        self._record("commit_validation_plan", digest=self.state.validation_plan_hash)
        return {"accepted": True, "committed_plan_hash": self.state.validation_plan_hash}

    def commit_followup_plan(self, payload_json: str) -> dict[str, Any]:
        self._count_tool()
        self._assert_untampered()
        if self.state.phase != "revealed":
            raise OpenProtocolError(
                "Follow-up plan must be committed after reveal and before purchase"
            )
        payload = _decode(payload_json)
        result = validate_followup_plan(payload)
        if not result.valid:
            issues = [row.to_dict() for row in result.issues]
            self._record("followup_plan_rejected", schema_issues=issues)
            return {"accepted": False, "schema_issues": issues}
        validation = json.loads(
            (self.records_root / "validation_plan.json").read_text(encoding="utf-8")
        )
        beliefs = {row["hypothesis_id"]: row["belief"] for row in validation["hypotheses"]}
        if payload.get("beliefs_before") != beliefs:
            issues = [
                {
                    "path": "beliefs_before",
                    "code": "commitment_mismatch",
                    "message": "Preserve validation-plan hypothesis IDs and values",
                }
            ]
            self._record("followup_plan_rejected", schema_issues=issues)
            return {"accepted": False, "schema_issues": issues}
        self.state.followup_plan_hash = self._commit_record("followup_plan.json", payload)
        self.state.phase = "followup_committed"
        self._record("commit_followup_plan", digest=self.state.followup_plan_hash)
        return {"accepted": True, "committed_followup_hash": self.state.followup_plan_hash}

    def submit(self, payload_json: str) -> dict[str, Any]:
        self._count_tool()
        self._assert_untampered()
        if self.state.phase != "purchased":
            raise OpenProtocolError("Final submission requires a completed resource action")
        payload = _decode(payload_json)
        result = validate_final_submission(payload)
        if not result.valid:
            issues = [row.to_dict() for row in result.issues]
            self._record("submit_rejected", schema_issues=issues)
            return {"accepted": False, "schema_issues": issues}
        self.state.final_submission_hash = self._commit_record("final_submission.json", payload)
        self.state.completion_accepted = True
        self.state.phase = "terminal"
        self.state.terminal_reason = "submitted"
        self._record(
            "submit",
            validation_plan_hash=self.state.validation_plan_hash,
            followup_plan_hash=self.state.followup_plan_hash,
            final_submission_hash=self.state.final_submission_hash,
        )
        return {"accepted": True, "terminal": True}


__all__ = [
    "Case2PilotRC1Environment",
    "DEVELOPMENT_ACTION_CONTRACT",
    "FIELD_GUIDE",
    "IDENTITY_PROVENANCE",
    "MISSION",
    "PUBLIC_SUPPORT_MODULES",
    "SCIENTIFIC_METHODS",
    "VALIDATION_MANIFEST",
]
