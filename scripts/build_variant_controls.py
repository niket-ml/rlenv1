#!/usr/bin/env python3
"""Exercise private variant ladders and symmetric policy controls."""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from uc_bench.variants import (
    PolicyAction,
    drop_features,
    inject_confounding_feature,
    inject_duplicate_samples,
    inject_label_noise,
    inject_sample_swaps,
    policy_control_score,
    simulate_sufficient_validation,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def is_nondecreasing(values: list[float]) -> bool:
    return all(
        left <= right + 1e-12
        for left, right in pairwise(values)
    )


def main() -> int:
    ladder_config = read_json(PROJECT_ROOT / "configs" / "variant_ladders.json")
    state_config = read_json(PROJECT_ROOT / "configs" / "evidence_states.json")
    expression = pd.read_csv(
        PROJECT_ROOT / "data" / "processed" / "sealed" / "GSE92415_gene_expression.csv.gz",
        index_col=0,
    )
    label_frame = pd.read_csv(
        PROJECT_ROOT / "grader_private" / "data" / "gse92415_labels.csv"
    )
    labels = label_frame.set_index("sample_id")["response"].astype(int)
    expression = expression.loc[:, labels.index]
    reference_genes = ("TNFRSF11B", "STC1", "PTGS2", "IL13RA2", "IL11")
    seed = 20260906
    summaries: dict[str, list[dict[str, Any]]] = {}

    label_rows = []
    for level in ladder_config["ladders"]["label_noise_fraction"]:
        _, changed = inject_label_noise(labels, float(level), seed=seed)
        label_rows.append(
            {
                "level": level,
                "affected_n": len(changed),
                "achieved_fraction": len(changed) / len(labels),
            }
        )
    summaries["label_noise_fraction"] = label_rows

    swap_rows = []
    for level in ladder_config["ladders"]["sample_swap_count"]:
        _, pairs = inject_sample_swaps(labels, int(level), seed=seed)
        swap_rows.append({"level": level, "affected_n": 2 * len(pairs)})
    summaries["sample_swap_count"] = swap_rows

    duplicate_rows = []
    for level in ladder_config["ladders"]["duplicate_contamination_fraction"]:
        _, _, mapping = inject_duplicate_samples(expression, labels, float(level), seed=seed)
        duplicate_rows.append(
            {
                "level": level,
                "duplicate_n": len(mapping),
                "achieved_fraction": len(mapping) / len(labels),
            }
        )
    summaries["duplicate_contamination_fraction"] = duplicate_rows

    dropout_rows = []
    for level in ladder_config["ladders"]["feature_dropout_fraction"]:
        _, dropped = drop_features(expression, reference_genes, float(level), seed=seed)
        dropout_rows.append(
            {
                "level": level,
                "dropped_n": len(dropped),
                "achieved_fraction": len(dropped) / len(reference_genes),
            }
        )
    summaries["feature_dropout_fraction"] = dropout_rows

    confounding_rows = []
    for level in ladder_config["ladders"]["confounding_correlation"]:
        feature = inject_confounding_feature(labels, float(level), seed=seed)
        achieved = float(np.corrcoef(feature, labels)[0, 1])
        confounding_rows.append({"level": level, "achieved_correlation": achieved})
    summaries["confounding_correlation"] = confounding_rows

    monotonic_checks = {
        "label_noise_fraction": is_nondecreasing(
            [row["affected_n"] for row in label_rows]
        ),
        "sample_swap_count": is_nondecreasing([row["affected_n"] for row in swap_rows]),
        "duplicate_contamination_fraction": is_nondecreasing(
            [row["duplicate_n"] for row in duplicate_rows]
        ),
        "feature_dropout_fraction": is_nondecreasing(
            [row["dropped_n"] for row in dropout_rows]
        ),
        "confounding_correlation": is_nondecreasing(
            [row["achieved_correlation"] for row in confounding_rows]
        ),
    }
    if not all(monotonic_checks.values()):
        raise RuntimeError(f"Variant ladder failed monotonicity: {monotonic_checks}")

    positive_config = state_config["sufficient_evidence_positive_control"]
    positive = simulate_sufficient_validation(
        target_auc=float(positive_config["target_auc"]),
        n=int(positive_config["n"]),
        seed=int(positive_config["seed"]),
        bootstrap_resamples=int(positive_config["bootstrap_resamples"]),
        permutations=int(positive_config["permutations"]),
    )
    if not (
        positive.auc >= 0.70
        and positive.auc_interval[0] > 0.50
        and positive.permutation_p_value <= 0.05
    ):
        raise RuntimeError("Synthetic sufficient-evidence control missed advancement threshold")

    expected = [
        PolicyAction(
            state["expected_decision"],
            tuple(state["expected_diagnostic_codes"]),
            state["accepted_next_action_types"][0],
        )
        for state in state_config["states"]
    ]
    universal_actions = {
        "always_insufficient": PolicyAction(
            "insufficient_evidence", ("generic_uncertainty",), "collect_more_data"
        ),
        "always_advance": PolicyAction("advance", ("none",), "deploy"),
        "always_stop": PolicyAction("stop", ("generic_failure",), "abandon"),
        "auc_chaser": PolicyAction("advance", ("none",), "deploy"),
    }
    policy_scores = {
        name: policy_control_score(expected, [action] * len(expected))
        for name, action in universal_actions.items()
    }
    policy_scores["state_aware_reference"] = policy_control_score(expected, expected)
    pass_threshold = float(state_config["universal_policy_pass_threshold"])
    if any(policy_scores[name] >= pass_threshold for name in universal_actions):
        raise RuntimeError(f"A universal policy passed symmetric controls: {policy_scores}")

    output = {
        "schema_version": "0.1",
        "controlled_results_are_biology_claims": False,
        "source_cohort_n": len(labels),
        "variant_ladders": summaries,
        "monotonic_checks": monotonic_checks,
        "sufficient_evidence_positive_control": positive.to_dict(),
        "policy_control_scores": policy_scores,
        "universal_policy_pass_threshold": pass_threshold,
        "all_universal_policies_fail": True,
    }
    output_path = PROJECT_ROOT / "artifacts" / "variants" / "scenario_controls.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
