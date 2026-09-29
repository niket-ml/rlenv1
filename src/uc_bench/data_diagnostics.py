"""Deterministic data-analysis diagnostics with sealed, recomputing graders."""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError, ContractError
from uc_bench.hashing import canonical_sha256, sha256_file

_EXPECTED_LADDERS = {
    "T03": {"duplicate_pair_count"},
    "T04": {"required_feature_dropout_fraction"},
    "T05": {"outcome_batch_phi"},
    "T06": {"sample_size", "label_noise"},
}
_METHODS = {
    "T03": "exact_expression_fingerprint",
    "T04": "unambiguous_gene_mapping_then_intersection",
    "T05": "binary_phi_coefficient",
    "T06": "prespecified_stratified_bootstrap",
}


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot load JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"Expected JSON object: {path}")
    return value


def _require_science() -> tuple[Any, Any]:
    try:
        import numpy as np
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - minimal installation only
        raise ConfigurationError(
            "Data diagnostics require the project science dependencies"
        ) from exc
    return np, pd


def _set_f1(expected: set[str], submitted: set[str]) -> float:
    if not expected and not submitted:
        return 100.0
    overlap = len(expected & submitted)
    if overlap == 0:
        return 0.0
    precision = overlap / len(submitted)
    recall = overlap / len(expected)
    return 100.0 * 2.0 * precision * recall / (precision + recall)


def validate_data_diagnostic_config(value: dict[str, Any]) -> dict[str, Any]:
    """Check ladder coverage and ensure paired variants change one factor only."""

    tasks = value.get("tasks")
    if not isinstance(tasks, list):
        raise ContractError("Data diagnostic config requires a task list")
    observed_ladders: dict[str, set[str]] = {}
    scenario_keys: set[tuple[str, str]] = set()
    scenario_count = 0
    for task in tasks:
        if not isinstance(task, dict):
            raise ContractError("Data diagnostic task entries must be objects")
        task_id = str(task.get("task_id"))
        ladder_id = str(task.get("ladder_id"))
        if task_id not in _EXPECTED_LADDERS:
            raise ContractError(f"Unexpected data diagnostic task: {task_id}")
        observed_ladders.setdefault(task_id, set()).add(ladder_id)
        scenarios = task.get("scenarios")
        if not isinstance(scenarios, list) or len(scenarios) < 2:
            raise ContractError(f"Ladder {task_id}/{ladder_id} needs at least two levels")
        varying_keys: set[str] = set()
        parameter_rows = []
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                raise ContractError("Data diagnostic scenarios must be objects")
            scenario_id = str(scenario.get("scenario_id"))
            key = (task_id, scenario_id)
            if key in scenario_keys:
                raise ContractError(f"Duplicate scenario key: {key}")
            scenario_keys.add(key)
            scenario_count += 1
            parameters = {k: v for k, v in scenario.items() if k != "scenario_id"}
            parameter_rows.append(parameters)
        all_parameter_keys = set().union(*(set(row) for row in parameter_rows))
        for parameter in all_parameter_keys:
            values = {json.dumps(row.get(parameter), sort_keys=True) for row in parameter_rows}
            if len(values) > 1:
                varying_keys.add(parameter)
        expected_varying = {
            "duplicate_pair_count": "duplicate_pair_count",
            "required_feature_dropout_fraction": "dropout_fraction",
            "outcome_batch_phi": "target_phi",
            "sample_size": "sample_size",
            "label_noise": "label_noise",
        }[ladder_id]
        if varying_keys != {expected_varying}:
            raise ContractError(
                f"Ladder {task_id}/{ladder_id} changes {sorted(varying_keys)}; "
                f"expected only {expected_varying}"
            )
    if observed_ladders != _EXPECTED_LADDERS:
        raise ContractError(f"Data diagnostic ladder coverage mismatch: {observed_ladders}")
    return {
        "task_ids": sorted(observed_ladders),
        "ladder_count": sum(len(value) for value in observed_ladders.values()),
        "scenario_count": scenario_count,
        "one_factor_per_ladder": True,
    }


def load_data_diagnostic_scenario(
    project_root: Path, task_id: str, scenario_id: str
) -> dict[str, Any]:
    config = _read_object(project_root / "configs" / "data_diagnostics.json")
    validate_data_diagnostic_config(config)
    matches = []
    for task in config["tasks"]:
        if task["task_id"] != task_id:
            continue
        for scenario in task["scenarios"]:
            if scenario["scenario_id"] == scenario_id:
                matches.append(
                    {
                        "task_id": task_id,
                        "task_name": task["name"],
                        "ladder_id": task["ladder_id"],
                        "generation_seed": int(config["generation_seed"]),
                        **scenario,
                    }
                )
    if len(matches) != 1:
        raise ConfigurationError(
            f"Expected one data scenario for {task_id}/{scenario_id}; found {len(matches)}"
        )
    return matches[0]


def iter_data_diagnostic_scenarios(project_root: Path) -> list[tuple[str, str]]:
    """Return every unique task/scenario key in deterministic config order."""

    config = _read_object(project_root / "configs" / "data_diagnostics.json")
    validate_data_diagnostic_config(config)
    return [
        (str(task["task_id"]), str(scenario["scenario_id"]))
        for task in config["tasks"]
        for scenario in task["scenarios"]
    ]


def _public_task_contract(task_id: str, scenario_id: str) -> dict[str, Any]:
    shared = {
        "schema_version": "0.1",
        "task_id": task_id,
        "scenario_id": scenario_id,
        "analysis_method": _METHODS[task_id],
        "decision_classes": ["advance", "insufficient_evidence", "stop"],
        "confidence_scoring": "reported_across_scenarios_not_scored_per_scenario",
        "wrong_decision_score_cap": 59.0,
    }
    if task_id == "T03":
        return {
            **shared,
            "files": [{"path": "data/samples.csv", "role": "sample metadata and expression"}],
            "metric_contract": {
                "duplicate_group_count": {
                    "definition": (
                        "count groups of two or more rows with exactly equal GENE_* values"
                    ),
                    "absolute_tolerance": 0.0,
                },
                "conflicting_duplicate_group_count": {
                    "definition": "duplicate groups spanning patient IDs or outcome labels",
                    "absolute_tolerance": 0.0,
                },
                "duplicated_sample_count": {
                    "definition": "number of rows belonging to conflicting duplicate groups",
                    "absolute_tolerance": 0.0,
                },
            },
            "affected_ids_contract": "all sample_id values in conflicting duplicate groups",
            "decision_policy": {
                "stop_if": "conflicting_duplicate_group_count > 0",
                "advance_otherwise": True,
            },
            "diagnosis_policy": {
                "conflict": ["sample_identity_conflict"],
                "clean": ["none"],
            },
            "next_action_policy": {
                "stop": "resolve_sample_identity",
                "advance": "continue_prespecified_analysis",
            },
            "scoring_weights": {
                "decision": 0.20,
                "metrics": 0.20,
                "diagnosis": 0.15,
                "affected_ids": 0.30,
                "method_and_action": 0.15,
            },
        }
    if task_id == "T04":
        return {
            **shared,
            "files": [
                {"path": "data/development_annotation.csv", "role": "development map"},
                {"path": "data/validation_annotation.csv", "role": "validation map"},
                {"path": "data/required_signature.txt", "role": "one required gene per line"},
                {"path": "data/development_expression.csv", "role": "development matrix"},
                {"path": "data/validation_expression.csv", "role": "validation matrix"},
            ],
            "mapping_rule": (
                "A feature is unambiguous only when gene_symbol is one non-empty symbol "
                "without '///'. Collapse repeated unambiguous features to the gene level, "
                "then intersect gene symbols across platforms."
            ),
            "metric_contract": {
                "development_unambiguous_gene_count": {
                    "definition": "unique unambiguous development gene symbols",
                    "absolute_tolerance": 0.0,
                },
                "validation_unambiguous_gene_count": {
                    "definition": "unique unambiguous validation gene symbols",
                    "absolute_tolerance": 0.0,
                },
                "common_unambiguous_gene_count": {
                    "definition": "intersection size of unambiguous gene symbols",
                    "absolute_tolerance": 0.0,
                },
                "required_signature_retention": {
                    "definition": "fraction of required signature genes in the intersection",
                    "absolute_tolerance": 0.001,
                },
            },
            "affected_ids_contract": "required gene symbols absent from the platform intersection",
            "decision_policy": {
                "advance_if": "required_signature_retention >= 0.80",
                "insufficient_evidence_otherwise": True,
            },
            "diagnosis_policy": {
                "any_required_gene_missing": ["feature_dropout"],
                "none_missing": ["none"],
            },
            "next_action_policy": {
                "advance": "continue_prespecified_analysis",
                "insufficient_evidence": "restore_required_features",
            },
            "scoring_weights": {
                "decision": 0.20,
                "metrics": 0.25,
                "diagnosis": 0.15,
                "affected_ids": 0.20,
                "method_and_action": 0.20,
            },
        }
    if task_id == "T05":
        return {
            **shared,
            "files": [{"path": "data/metadata.csv", "role": "outcome and batch metadata"}],
            "metric_contract": {
                "phi_coefficient": {
                    "definition": "signed binary phi coefficient for batch=1 and outcome=1",
                    "absolute_tolerance": 0.001,
                },
                "absolute_batch_response_rate_gap": {
                    "definition": "absolute difference in response rates between batch 1 and 0",
                    "absolute_tolerance": 0.001,
                },
            },
            "affected_ids_contract": "empty; do not infer individual confounded samples",
            "decision_policy": {
                "advance_if": "abs(phi_coefficient) < 0.20",
                "insufficient_evidence_if": "0.20 <= abs(phi_coefficient) < 0.50",
                "stop_if": "abs(phi_coefficient) >= 0.50",
            },
            "diagnosis_policy": {
                "abs_phi_at_least_0_20": ["batch_confounding"],
                "otherwise": ["none"],
            },
            "next_action_policy": {
                "advance": "continue_prespecified_analysis",
                "insufficient_evidence": "batch_stratified_resampling",
                "stop": "independent_batch_balanced_validation",
            },
            "scoring_weights": {
                "decision": 0.25,
                "metrics": 0.30,
                "diagnosis": 0.20,
                "affected_ids": 0.0,
                "method_and_action": 0.25,
            },
        }
    if task_id == "T06":
        return {
            **shared,
            "files": [{"path": "data/predictions.csv", "role": "labels and locked scores"}],
            "bootstrap_contract": {
                "seed": 20260906,
                "resamples": 1000,
                "method": (
                    "For each resample, independently sample positive-row indices and "
                    "negative-row indices with replacement at their observed class counts "
                    "using numpy.random.default_rng(seed), concatenate them, and compute "
                    "sklearn.metrics.roc_auc_score. Use numpy.percentile at 2.5 and 97.5 "
                    "and numpy.std with ddof=1."
                ),
            },
            "metric_contract": {
                "evaluated_n": {"definition": "row count", "absolute_tolerance": 0.0},
                "auc": {"definition": "ROC AUC on all rows", "absolute_tolerance": 0.001},
                "auc_ci_lower": {
                    "definition": "2.5th bootstrap percentile",
                    "absolute_tolerance": 0.005,
                },
                "auc_ci_upper": {
                    "definition": "97.5th bootstrap percentile",
                    "absolute_tolerance": 0.005,
                },
                "auc_ci_width": {"definition": "upper minus lower", "absolute_tolerance": 0.007},
                "bootstrap_auc_sd": {
                    "definition": "bootstrap AUC SD with ddof=1",
                    "absolute_tolerance": 0.005,
                },
            },
            "affected_ids_contract": "empty; exact latent label perturbations are not identifiable",
            "decision_policy": {
                "advance_requires_all": [
                    "evaluated_n >= 100",
                    "auc >= 0.70",
                    "auc_ci_lower > 0.50",
                    "auc_ci_width <= 0.25",
                ],
                "insufficient_evidence_otherwise": True,
            },
            "diagnosis_policy": {
                "underpowered_validation": "evaluated_n < 100",
                "unstable_validation": "auc < 0.70 or auc_ci_lower <= 0.50 or auc_ci_width > 0.25",
                "none": "no failure criterion is met",
            },
            "next_action_policy": {
                "underpowered": "expand_validation_sample",
                "adequately_sized_but_unstable": "revisit_model_specification",
                "advance": "independent_replication",
            },
            "scoring_weights": {
                "decision": 0.30,
                "metrics": 0.40,
                "diagnosis": 0.15,
                "affected_ids": 0.0,
                "method_and_action": 0.15,
            },
        }
    raise ConfigurationError(f"Unsupported data diagnostic task: {task_id}")


def _write_t03_data(destination: Path, scenario: dict[str, Any]) -> None:
    np, pd = _require_science()
    rng = np.random.default_rng(scenario["generation_seed"])
    sample_count = 120
    gene_count = 64
    values = rng.normal(size=(sample_count, gene_count)).round(8)
    outcomes = np.array([index % 2 for index in range(sample_count)], dtype=int)
    pair_count = int(scenario["duplicate_pair_count"])
    for pair_index in range(pair_count):
        source = pair_index
        target = sample_count - 1 - pair_index
        values[target] = values[source]
        outcomes[target] = 1 - outcomes[source]
    frame = pd.DataFrame(values, columns=[f"GENE_{index:04d}" for index in range(gene_count)])
    frame.insert(0, "outcome", outcomes)
    frame.insert(0, "patient_id", [f"PATIENT_{index:04d}" for index in range(sample_count)])
    frame.insert(0, "sample_id", [f"SAMPLE_{index:04d}" for index in range(sample_count)])
    frame.to_csv(destination / "samples.csv", index=False)


def _annotation_rows(prefix: str, genes: list[str]) -> list[dict[str, str]]:
    rows = [
        {"feature_id": f"{prefix}_{index:05d}", "gene_symbol": gene}
        for index, gene in enumerate(genes)
    ]
    rows.extend(
        {"feature_id": f"{prefix}_REPEAT_{index:05d}", "gene_symbol": gene}
        for index, gene in enumerate(genes[::10])
    )
    rows.extend(
        {
            "feature_id": f"{prefix}_AMBIG_{index:05d}",
            "gene_symbol": f"{genes[index]} /// {genes[index + 1]}",
        }
        for index in range(0, min(20, len(genes) - 1), 2)
    )
    return rows


def _write_t04_data(destination: Path, scenario: dict[str, Any]) -> None:
    np, pd = _require_science()
    rng = np.random.default_rng(scenario["generation_seed"])
    common_genes = [f"GENE{index:04d}" for index in range(1, 301)]
    required = common_genes[:40]
    dropout_count = int(round(float(scenario["dropout_fraction"]) * len(required)))
    dropped = set(required[:dropout_count])
    validation_genes = [gene for gene in common_genes if gene not in dropped]
    validation_genes.extend(f"VALONLY{index:04d}" for index in range(1, 41))
    development_rows = _annotation_rows("DEV", common_genes)
    validation_rows = _annotation_rows("VAL", validation_genes)
    pd.DataFrame(development_rows).to_csv(destination / "development_annotation.csv", index=False)
    pd.DataFrame(validation_rows).to_csv(destination / "validation_annotation.csv", index=False)
    (destination / "required_signature.txt").write_text(
        "\n".join(required) + "\n", encoding="utf-8"
    )
    for name, rows in (("development", development_rows), ("validation", validation_rows)):
        expression = pd.DataFrame(
            rng.normal(size=(len(rows), 8)).round(6),
            columns=[f"{name[:3].upper()}_S{index:02d}" for index in range(8)],
        )
        expression.insert(0, "feature_id", [row["feature_id"] for row in rows])
        expression.to_csv(destination / f"{name}_expression.csv", index=False)


def _write_t05_data(destination: Path, scenario: dict[str, Any]) -> None:
    np, pd = _require_science()
    rng = np.random.default_rng(scenario["generation_seed"])
    sample_count = 200
    target_phi = float(scenario["target_phi"])
    agreements = int(round(sample_count * (1.0 + target_phi) / 2.0))
    if agreements % 2:
        raise ConfigurationError("T05 agreement count must be even")
    disagreements = sample_count - agreements
    rows = []
    for batch, outcome, count in (
        (0, 0, agreements // 2),
        (1, 1, agreements // 2),
        (0, 1, disagreements // 2),
        (1, 0, disagreements // 2),
    ):
        rows.extend({"batch": batch, "outcome": outcome} for _ in range(count))
    order = rng.permutation(sample_count)
    shuffled = [rows[int(index)] for index in order]
    frame = pd.DataFrame(shuffled)
    frame.insert(0, "sample_id", [f"SAMPLE_{index:04d}" for index in range(sample_count)])
    frame.to_csv(destination / "metadata.csv", index=False)


def _prediction_pool(seed: int) -> tuple[Any, Any]:
    np, _ = _require_science()
    rng = np.random.default_rng(seed)
    labels = np.array([0, 1] * 120, dtype=int)
    scores = labels + rng.normal(0.0, 0.62, size=240)
    return labels, scores


def _write_t06_data(destination: Path, scenario: dict[str, Any]) -> None:
    np, pd = _require_science()
    labels, scores = _prediction_pool(int(scenario["generation_seed"]))
    sample_size = int(scenario["sample_size"])
    labels = labels[:sample_size].copy()
    scores = scores[:sample_size].copy()
    noise = float(scenario["label_noise"])
    flips_per_class_per_block = int(round(noise * 10))
    noise_rng = np.random.default_rng(int(scenario["generation_seed"]) + 17)
    flip_indices = []
    for block_start in range(0, sample_size, 20):
        negatives = np.arange(block_start, block_start + 20, 2)
        positives = np.arange(block_start + 1, block_start + 20, 2)
        noise_rng.shuffle(negatives)
        noise_rng.shuffle(positives)
        flip_indices.extend(negatives[:flips_per_class_per_block])
        flip_indices.extend(positives[:flips_per_class_per_block])
    if flip_indices:
        labels[np.asarray(flip_indices, dtype=int)] ^= 1
    frame = pd.DataFrame(
        {
            "sample_id": [f"SAMPLE_{index:04d}" for index in range(sample_size)],
            "observed_label": labels,
            "locked_score": scores.round(8),
        }
    )
    frame.to_csv(destination / "predictions.csv", index=False)


@dataclass(frozen=True, slots=True)
class DataDiagnosticPackage:
    task_id: str
    scenario_id: str
    workspace_root: Path
    package_digest: str


class DataDiagnosticBuilder:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def build(
        self,
        task_id: str,
        scenario_id: str,
        *,
        output_root: Path,
        replace: bool = False,
        expert_playbook: bool = False,
    ) -> DataDiagnosticPackage:
        scenario = load_data_diagnostic_scenario(self.project_root, task_id, scenario_id)
        destination = output_root / f"{task_id}-{scenario_id}"
        if destination.exists():
            if not replace:
                raise ConfigurationError(f"Data diagnostic workspace exists: {destination}")
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        task_root = self.project_root / "tasks" / "diagnostic_data_v0"
        for source in sorted(path for path in task_root.rglob("*") if path.is_file()):
            target = destination / source.relative_to(task_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if expert_playbook:
            shutil.copyfile(
                self.project_root / "tasks" / "EXPERT_PLAYBOOK.md",
                destination / "EXPERT_PLAYBOOK.md",
            )
        data_root = destination / "data"
        data_root.mkdir()
        writers = {
            "T03": _write_t03_data,
            "T04": _write_t04_data,
            "T05": _write_t05_data,
            "T06": _write_t06_data,
        }
        writers[task_id](data_root, scenario)
        task_contract = _public_task_contract(task_id, scenario_id)
        (destination / "task.json").write_text(
            json.dumps(task_contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (destination / "submission").mkdir()
        rows = [
            {
                "path": path.relative_to(destination).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(path for path in destination.rglob("*") if path.is_file())
        ]
        digest = canonical_sha256(rows)
        (destination / "START_STATE.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "task_id": task_id,
                    "scenario_id": scenario_id,
                    "package_digest": digest,
                    "private_answer_visible": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return DataDiagnosticPackage(task_id, scenario_id, destination, digest)


def _unambiguous_genes(path: Path) -> set[str]:
    _, pd = _require_science()
    frame = pd.read_csv(path, dtype=str).fillna("")
    values = (str(value).strip() for value in frame["gene_symbol"])
    return {value for value in values if value and "///" not in value}


def _binary_phi(batch: Any, outcome: Any) -> float:
    np, _ = _require_science()
    x = np.asarray(batch, dtype=int)
    y = np.asarray(outcome, dtype=int)
    n11 = int(((x == 1) & (y == 1)).sum())
    n10 = int(((x == 1) & (y == 0)).sum())
    n01 = int(((x == 0) & (y == 1)).sum())
    n00 = int(((x == 0) & (y == 0)).sum())
    denominator = math.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    if denominator == 0:
        raise ContractError("Phi coefficient is undefined for a constant variable")
    return (n11 * n00 - n10 * n01) / denominator


def _bootstrap_metrics(frame: Any, contract: dict[str, Any]) -> dict[str, float]:
    np, _ = _require_science()
    from sklearn.metrics import roc_auc_score

    labels = frame["observed_label"].to_numpy(dtype=int)
    scores = frame["locked_score"].to_numpy(dtype=float)
    positives = np.flatnonzero(labels == 1)
    negatives = np.flatnonzero(labels == 0)
    rng = np.random.default_rng(int(contract["seed"]))
    estimates = []
    for _ in range(int(contract["resamples"])):
        chosen = np.concatenate(
            [
                rng.choice(positives, size=len(positives), replace=True),
                rng.choice(negatives, size=len(negatives), replace=True),
            ]
        )
        estimates.append(float(roc_auc_score(labels[chosen], scores[chosen])))
    lower, upper = (float(value) for value in np.percentile(estimates, [2.5, 97.5]))
    return {
        "evaluated_n": float(len(frame)),
        "auc": float(roc_auc_score(labels, scores)),
        "auc_ci_lower": lower,
        "auc_ci_upper": upper,
        "auc_ci_width": upper - lower,
        "bootstrap_auc_sd": float(np.std(estimates, ddof=1)),
    }


def solve_data_diagnostic(workspace_root: Path) -> dict[str, Any]:
    """Recompute the full expected answer using only agent-visible files."""

    _, pd = _require_science()
    root = workspace_root.resolve()
    task = _read_object(root / "task.json")
    task_id = str(task["task_id"])
    if task_id == "T03":
        frame = pd.read_csv(root / "data" / "samples.csv")
        gene_columns = [column for column in frame.columns if column.startswith("GENE_")]
        grouped = frame.groupby(gene_columns, sort=False, dropna=False)
        duplicate_groups = [group for _, group in grouped if len(group) > 1]
        conflicts = [
            group
            for group in duplicate_groups
            if group["patient_id"].nunique() > 1 or group["outcome"].nunique() > 1
        ]
        affected = sorted(str(sample_id) for group in conflicts for sample_id in group["sample_id"])
        metrics = {
            "duplicate_group_count": float(len(duplicate_groups)),
            "conflicting_duplicate_group_count": float(len(conflicts)),
            "duplicated_sample_count": float(len(affected)),
        }
        decision = "stop" if conflicts else "advance"
        codes = ["sample_identity_conflict"] if conflicts else ["none"]
        action = "resolve_sample_identity" if conflicts else "continue_prespecified_analysis"
    elif task_id == "T04":
        development = _unambiguous_genes(root / "data" / "development_annotation.csv")
        validation = _unambiguous_genes(root / "data" / "validation_annotation.csv")
        required = {
            line.strip()
            for line in (root / "data" / "required_signature.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        }
        common = development & validation
        affected = sorted(required - common)
        retention = len(required & common) / len(required)
        metrics = {
            "development_unambiguous_gene_count": float(len(development)),
            "validation_unambiguous_gene_count": float(len(validation)),
            "common_unambiguous_gene_count": float(len(common)),
            "required_signature_retention": float(retention),
        }
        decision = "advance" if retention >= 0.80 else "insufficient_evidence"
        codes = ["feature_dropout"] if affected else ["none"]
        action = (
            "continue_prespecified_analysis"
            if decision == "advance"
            else "restore_required_features"
        )
    elif task_id == "T05":
        frame = pd.read_csv(root / "data" / "metadata.csv")
        phi = float(_binary_phi(frame["batch"], frame["outcome"]))
        rates = frame.groupby("batch")["outcome"].mean()
        gap = abs(float(rates.loc[1]) - float(rates.loc[0]))
        metrics = {
            "phi_coefficient": phi,
            "absolute_batch_response_rate_gap": gap,
        }
        absolute_phi = abs(phi)
        if absolute_phi >= 0.50 - 1e-12:
            decision = "stop"
        elif absolute_phi >= 0.20 - 1e-12:
            decision = "insufficient_evidence"
        else:
            decision = "advance"
        codes = ["batch_confounding"] if absolute_phi >= 0.20 - 1e-12 else ["none"]
        action = {
            "advance": "continue_prespecified_analysis",
            "insufficient_evidence": "batch_stratified_resampling",
            "stop": "independent_batch_balanced_validation",
        }[decision]
        affected = []
    elif task_id == "T06":
        frame = pd.read_csv(root / "data" / "predictions.csv")
        metrics = _bootstrap_metrics(frame, task["bootstrap_contract"])
        underpowered = metrics["evaluated_n"] < 100
        unstable = (
            metrics["auc"] < 0.70
            or metrics["auc_ci_lower"] <= 0.50
            or metrics["auc_ci_width"] > 0.25
        )
        failures = []
        if underpowered:
            failures.append("underpowered_validation")
        if unstable:
            failures.append("unstable_validation")
        codes = failures or ["none"]
        decision = "insufficient_evidence" if failures else "advance"
        if underpowered:
            action = "expand_validation_sample"
        elif unstable:
            action = "revisit_model_specification"
        else:
            action = "independent_replication"
        affected = []
    else:
        raise ContractError(f"Unsupported task_id in task.json: {task_id}")
    return {
        "task_id": task_id,
        "scenario_id": task["scenario_id"],
        "decision": decision,
        "diagnostic_codes": codes,
        "metrics": metrics,
        "affected_ids": affected,
        "analysis_method": _METHODS[task_id],
        "next_action_type": action,
    }


class DataDiagnosticEnvironment:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.submission: dict[str, Any] | None = None

    def submit_data_audit(self, submission_path: str) -> str:
        if self.submission is not None:
            raise ContractError("submit_data_audit may be called only once")
        relative = Path(submission_path)
        if relative.is_absolute():
            raise ContractError("submission_path must be relative")
        path = (self.workspace_root / relative).resolve()
        if self.workspace_root not in path.parents or not path.is_file():
            raise ContractError("Submission is missing or outside the workspace")
        value = _read_object(path)
        schema = _read_object(self.workspace_root / "schemas" / "final_submission.schema.json")
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import ValidationError

        try:
            Draft202012Validator(schema).validate(value)
        except ValidationError as exc:
            location = ".".join(str(part) for part in exc.absolute_path)
            suffix = f" at {location}" if location else ""
            raise ContractError(
                f"Submission violates public schema{suffix}: {exc.message}"
            ) from exc
        task = _read_object(self.workspace_root / "task.json")
        if value["task_id"] != task["task_id"] or value["scenario_id"] != task["scenario_id"]:
            raise ContractError("Submission task_id or scenario_id does not match task.json")
        expected_metrics = set(task["metric_contract"])
        if set(value["metrics"]) != expected_metrics:
            raise ContractError(
                f"Submission metric keys must be exactly {sorted(expected_metrics)}"
            )
        codes = set(value["diagnostic_codes"])
        if "none" in codes and len(codes) != 1:
            raise ContractError("Diagnostic code 'none' cannot be combined with failures")
        self.submission = value
        return json.dumps({"submitted": True}, sort_keys=True)


@dataclass(frozen=True, slots=True)
class DataDiagnosticGrade:
    score: float
    contract_valid: bool
    decision_correct: bool
    component_scores: dict[str, float]
    checks: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "contract_valid": self.contract_valid,
            "decision_correct": self.decision_correct,
            "component_scores": self.component_scores,
            "checks": self.checks,
        }


def grade_data_diagnostic(
    workspace_root: Path, submission: dict[str, Any] | None
) -> DataDiagnosticGrade:
    if submission is None:
        empty = {
            "decision": 0.0,
            "metrics": 0.0,
            "diagnosis": 0.0,
            "affected_ids": 0.0,
            "method_and_action": 0.0,
        }
        return DataDiagnosticGrade(0.0, False, False, empty, {"submitted": False})
    root = workspace_root.resolve()
    expected = solve_data_diagnostic(root)
    task = _read_object(root / "task.json")
    metric_checks = {}
    for name, specification in task["metric_contract"].items():
        submitted_value = float(submission["metrics"][name])
        expected_value = float(expected["metrics"][name])
        tolerance = float(specification["absolute_tolerance"])
        metric_checks[name] = abs(submitted_value - expected_value) <= tolerance + 1e-12
    metrics_score = 100.0 * sum(metric_checks.values()) / len(metric_checks)
    decision_correct = submission["decision"] == expected["decision"]
    diagnosis_score = _set_f1(
        set(expected["diagnostic_codes"]), set(submission["diagnostic_codes"])
    )
    affected_score = _set_f1(set(expected["affected_ids"]), set(submission["affected_ids"]))
    method_correct = submission["analysis_method"] == expected["analysis_method"]
    action_correct = submission["next_action_type"] == expected["next_action_type"]
    method_action_score = 50.0 * method_correct + 50.0 * action_correct
    components = {
        "decision": 100.0 * decision_correct,
        "metrics": metrics_score,
        "diagnosis": diagnosis_score,
        "affected_ids": affected_score,
        "method_and_action": method_action_score,
    }
    weights = {key: float(value) for key, value in task["scoring_weights"].items()}
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12):
        raise ContractError("Public data diagnostic weights must sum to one")
    score = sum(weights[name] * components[name] for name in weights)
    if not decision_correct:
        score = min(score, float(task["wrong_decision_score_cap"]))
    return DataDiagnosticGrade(
        score=score,
        contract_valid=True,
        decision_correct=decision_correct,
        component_scores=components,
        checks={
            "submitted": True,
            "metric_checks": metric_checks,
            "diagnostic_codes_exact": set(submission["diagnostic_codes"])
            == set(expected["diagnostic_codes"]),
            "affected_ids_exact": set(submission["affected_ids"]) == set(expected["affected_ids"]),
            "analysis_method_correct": method_correct,
            "next_action_correct": action_correct,
        },
    )


def reference_submission(workspace_root: Path) -> dict[str, Any]:
    expected = solve_data_diagnostic(workspace_root)
    return {
        **expected,
        "confidence": 0.90,
        "rationale": "Recomputed from the supplied files under the prespecified contract.",
    }
