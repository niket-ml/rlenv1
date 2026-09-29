"""Auditable private evidence-producing interventions for the open MMMVP RC."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from uc_bench.v07_cases import PUBLIC_ROOT

RC_PRIVATE_ROOT = Path("grader_private/mmmvp_open_rc1")
X31_FEATURES = ("IFN_score", "epithelial_score", "library_size_log10")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def build_rc_private_assets(project_root: Path) -> dict[str, Any]:
    """Generate private RC evidence from public source features without reading outcomes."""

    root = project_root.resolve()
    private = root / RC_PRIVATE_ROOT

    validity_cards = json.loads(
        (root / "grader_private/mmmvp_open/validity_cards.json").read_text(encoding="utf-8")
    )
    case1_card = next(
        row for row in validity_cards["conditions"] if row["condition_id"] == "case_01"
    )
    case1_card["defensible_final_dispositions"] = ["CONTINUE", "PAUSE"]
    case1_card["defensible_development_stages"] = [
        "INTERNAL_VALIDATION",
        "EXTERNAL_VALIDATION",
    ]
    case1_card["defensible_use_scopes"] = [
        "NO_USE",
        "RETROSPECTIVE_AUDIT",
        "RESEARCH_RANKING",
        "RESEARCH_PROBABILITY",
    ]
    _write_json(private / "validity_cards.json", validity_cards)

    case2_public = root / PUBLIC_ROOT / "case_02"
    metadata = _read_csv(case2_public / "data/cohort_metadata.csv")
    crosswalk = [
        {
            "source_record_id": row["sample_id"],
            "reported_patient_id": row["reported_patient_id"],
            "fingerprint_cluster": row["fingerprint_cluster"],
            "canonical_person_id": row["reported_patient_id"],
            "adjudication_status": "adjudicated",
            "adjudication_basis": "source_registry_plus_fingerprint_review",
        }
        for row in metadata
        if str(row.get("baseline_eligible", "")).lower() == "true"
    ]
    x17 = private / "case_02/X17"
    _write_csv(x17 / "canonical_person_crosswalk.csv", crosswalk)
    _write_json(
        x17 / "adjudication_provenance.json",
        {
            "blinded_to_outcomes": True,
            "canonical_key_source": "source_registry",
            "fingerprint_review_used": True,
            "adjudication_rule": (
                "records sharing one registry person are one canonical person; fingerprint "
                "discordance is retained as provenance rather than silently splitting identity"
            ),
            "remaining_uncertainty": [],
            "source_record_count": len(crosswalk),
            "canonical_person_count": len({row["canonical_person_id"] for row in crosswalk}),
        },
    )

    case3_public = root / PUBLIC_ROOT / "case_03"
    case3_metadata = {
        row["sample_id"]: row for row in _read_csv(case3_public / "data/cohort_metadata.csv")
    }
    grouped: dict[str, list[list[float]]] = {}
    for row in _read_csv(case3_public / "data/expression_feature_summary.csv"):
        entity = case3_metadata[row["sample_id"]]["fingerprint_cluster"]
        grouped.setdefault(entity, []).append([float(row[name]) for name in X31_FEATURES])
    remains_rows = [
        {
            "patient_key": entity,
            **{
                name: f"{mean(values[index] for values in grouped[entity]):.8f}"
                for index, name in enumerate(X31_FEATURES)
            },
        }
        for entity in sorted(grouped)
    ]
    feature_vectors = [tuple(row[name] for name in X31_FEATURES) for row in remains_rows]
    random.Random(41).shuffle(feature_vectors)
    collapse_rows = [
        {
            "patient_key": row["patient_key"],
            **{name: vector[index] for index, name in enumerate(X31_FEATURES)},
        }
        for row, vector in zip(remains_rows, feature_vectors, strict=True)
    ]

    generator = random.Random(20260731)
    training_rows = [
        {
            "sample_id": f"TR{index:04d}",
            "IFN_score": f"{generator.gauss(0, 1):.8f}",
            "epithelial_score": f"{generator.gauss(0, 1):.8f}",
            "library_size_log10": f"{generator.gauss(6.3, 0.15):.8f}",
        }
        for index in range(1, 181)
    ]
    x31 = private / "case_03/X31"
    _write_csv(x31 / "training_inputs.csv", training_rows)
    _write_csv(x31 / "validation_inputs_signal_collapses.csv", collapse_rows)
    _write_csv(x31 / "validation_inputs_signal_remains.csv", remains_rows)
    _write_json(
        x31 / "frozen_model.json",
        {
            "model_id": "uc-lock-2026-07-clean-replay-rc1",
            "feature_order": list(X31_FEATURES),
            "coefficients": [1.0, -0.2, 0.05],
            "intercept": -0.15,
            "link": "logistic",
            "learned_preprocessing": "training_only_featurewise_zscore",
            "standard_deviation": "sample",
        },
    )
    return {
        "x17_crosswalk_sha256": _sha256(x17 / "canonical_person_crosswalk.csv"),
        "x31_training_sha256": _sha256(x31 / "training_inputs.csv"),
        "x31_model_sha256": _sha256(x31 / "frozen_model.json"),
        "x31_validation_hashes": {
            mechanism: _sha256(x31 / f"validation_inputs_{mechanism}.csv")
            for mechanism in ("signal_collapses", "signal_remains")
        },
        "outcomes_read_during_asset_generation": False,
        "validity_cards_sha256": _sha256(private / "validity_cards.json"),
    }


def execute_frozen_x31(
    training_inputs: Path,
    validation_inputs: Path,
    model_artifact: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Execute training-only preprocessing and a frozen logistic predictor."""

    training = _read_csv(training_inputs)
    validation = _read_csv(validation_inputs)
    model = json.loads(model_artifact.read_text(encoding="utf-8"))
    feature_order = tuple(model["feature_order"])
    if feature_order != X31_FEATURES:
        raise ValueError("Frozen X31 feature contract changed")
    centers = {name: mean(float(row[name]) for row in training) for name in feature_order}
    scales = {name: stdev(float(row[name]) for row in training) for name in feature_order}
    if any(not math.isfinite(value) or value <= 0 for value in scales.values()):
        raise ValueError("Training-only reference scale is invalid")
    coefficients = [float(value) for value in model["coefficients"]]
    intercept = float(model["intercept"])
    predictions: list[dict[str, Any]] = []
    for row in validation:
        standardized = [(float(row[name]) - centers[name]) / scales[name] for name in feature_order]
        linear = intercept + sum(
            coefficient * value
            for coefficient, value in zip(coefficients, standardized, strict=True)
        )
        predictions.append(
            {
                "patient_key": row["patient_key"],
                "predicted_probability": f"{_sigmoid(linear):.8f}",
                "model_version": model["model_id"],
            }
        )
    output_directory.mkdir(parents=True, exist_ok=True)
    prediction_path = output_directory / "replay_predictions.csv"
    _write_csv(prediction_path, predictions)
    lineage = {
        "schema_version": "mmmvp-x31-execution-1",
        "fit_boundary": {
            "learned_preprocessing_fit_role": "training",
            "training_rows": len(training),
            "validation_rows": len(validation),
            "validation_rows_used_for_fit": 0,
            "outcomes_accessible_during_fit_or_prediction": False,
        },
        "input_hashes": {
            "training_inputs_sha256": _sha256(training_inputs),
            "validation_inputs_sha256": _sha256(validation_inputs),
            "model_sha256": _sha256(model_artifact),
        },
        "output_hashes": {"replay_predictions_sha256": _sha256(prediction_path)},
        "determinism": {
            "asset_generation_seed": 20260731,
            "paired_input_generation_seed": 41,
            "runtime_randomness": False,
            "software": "Python standard-library statistics and math",
        },
        "preprocessing": {
            "method": "featurewise_zscore",
            "fit_scope": "training_inputs.csv only",
            "centers": {name: round(value, 12) for name, value in centers.items()},
            "scales": {name: round(value, 12) for name, value in scales.items()},
        },
        "model": {"model_id": model["model_id"], "weights_unchanged": True},
    }
    _write_json(output_directory / "execution_lineage.json", lineage)
    return lineage


def execute_x31_resource(
    project_root: Path,
    mechanism: str,
    output_directory: Path,
) -> dict[str, Any]:
    root = project_root.resolve() / RC_PRIVATE_ROOT / "case_03/X31"
    return execute_frozen_x31(
        root / "training_inputs.csv",
        root / f"validation_inputs_{mechanism}.csv",
        root / "frozen_model.json",
        output_directory,
    )


def verify_x31_resource(project_root: Path, mechanism: str, purchased: Path, scratch: Path) -> bool:
    """Independently rerun X31 into host scratch and compare the returned package."""

    if scratch.exists():
        raise FileExistsError(scratch)
    execute_x31_resource(project_root, mechanism, scratch)
    expected = {
        path.relative_to(scratch).as_posix(): _sha256(path)
        for path in sorted(scratch.rglob("*"))
        if path.is_file()
    }
    observed = {
        path.relative_to(purchased).as_posix(): _sha256(path)
        for path in sorted(purchased.rglob("*"))
        if path.is_file()
    }
    return expected == observed


__all__ = [
    "RC_PRIVATE_ROOT",
    "X31_FEATURES",
    "build_rc_private_assets",
    "execute_frozen_x31",
    "execute_x31_resource",
    "verify_x31_resource",
]
