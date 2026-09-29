from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType

import pandas as pd

from uc_bench.predictor import LinearRankPredictor
from uc_bench.reference import auc_with_stratified_bootstrap, permutation_p_value

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PATH = (
    PROJECT_ROOT / "tasks" / "uc_biomarker_diligence_v0" / "public_evaluator.py"
)


def load_public_module():
    module = ModuleType("uc_bench_public_evaluator")
    exec(compile(PUBLIC_PATH.read_text(encoding="utf-8"), PUBLIC_PATH, "exec"), module.__dict__)
    return module


def test_public_evaluator_matches_private_development_math() -> None:
    public = load_public_module()
    development_root = PROJECT_ROOT / "data" / "processed" / "development"
    metadata = pd.read_csv(development_root / "metadata.csv")
    discovery = pd.read_csv(
        development_root / "GSE16879_gene_expression.csv.gz", index_col=0
    )
    replication = pd.read_csv(
        development_root / "GSE73661_gene_expression.csv.gz", index_col=0
    )
    model_value = json.loads(
        (PROJECT_ROOT / "artifacts" / "reference" / "model.json").read_text(
            encoding="utf-8"
        )
    )
    result = public.evaluate_development(
        model=model_value,
        metadata=metadata,
        discovery_expression=discovery,
        replication_expression=replication,
        resamples=200,
        discovery_seed=11,
        replication_seed=12,
        permutations=300,
        permutation_seed=13,
    )

    private_model = LinearRankPredictor.from_dict(model_value)
    outcomes = metadata.set_index("sample_id")["response"]
    for role, cohort, matrix, seed in (
        ("discovery", "GSE16879", discovery, 11),
        ("replication", "GSE73661", replication, 12),
    ):
        sample_ids = metadata.loc[metadata["cohort"] == cohort, "sample_id"].tolist()
        predictions = private_model.predict_proba(matrix.loc[:, sample_ids])
        auc, interval = auc_with_stratified_bootstrap(
            outcomes, predictions, resamples=200, seed=seed
        )
        assert result["development_results"][role]["auc"] == auc
        assert result["development_results"][role]["auc_interval"] == list(interval)
    replication_ids = metadata.loc[
        metadata["cohort"] == "GSE73661", "sample_id"
    ].tolist()
    replication_predictions = private_model.predict_proba(
        replication.loc[:, replication_ids]
    )
    assert result["development_results"]["replication"][
        "permutation_p_value"
    ] == permutation_p_value(
        outcomes,
        replication_predictions,
        permutations=300,
        seed=13,
    )
    assert result["common_gene_count"] == 17151
