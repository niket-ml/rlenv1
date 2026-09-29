from __future__ import annotations

import json
from pathlib import Path

from scripts.build_v06_cost_plan import _ceil_cents, _episode_cost, v05_workload_profile

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> dict:
    return json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))


def test_v05_workload_profile_is_derived_from_all_frozen_development_runs() -> None:
    profile = v05_workload_profile(PROJECT_ROOT)
    assert profile["episode_count"] == 18
    assert profile["input_tokens"]["median"] == 882_243.5
    assert profile["input_tokens"]["p90"] == 1_281_744.1
    assert profile["output_tokens"]["median"] == 9_524
    assert profile["output_tokens"]["p90"] == 20_948.3


def test_cost_formula_separates_uncached_cached_and_completion_rates() -> None:
    no_cache = _episode_cost(
        input_tokens=1_000_000,
        output_tokens=100_000,
        prompt_price=2,
        completion_price=10,
        cache_read_price=0.2,
        cache_fraction=0,
    )
    cache = _episode_cost(
        input_tokens=1_000_000,
        output_tokens=100_000,
        prompt_price=2,
        completion_price=10,
        cache_read_price=0.2,
        cache_fraction=0.6,
    )
    assert no_cache == 3
    assert cache == 1.92


def test_funding_requirements_round_up_and_never_underfund_a_cap() -> None:
    assert _ceil_cents(14.62223292) == 14.63
    assert _ceil_cents(125.62223292) == 125.63
    assert _ceil_cents(-1) == 0


def test_saved_cost_plan_and_execution_caps_are_consistent_and_non_scientific() -> None:
    plan = _read("artifacts/diagnostics/hard_suite_v06_cost_plan.json")
    execution = _read("configs/hard_suite_v06_execution.json")
    assert plan["inference_requests_made"] == 0
    assert plan["scientific_requests_made"] == 0
    assert plan["heldout_requests_made"] == 0
    assert plan["astra_requests_made"] == 0
    assert plan["full_matrix"]["episode_count"] == 30
    assert plan["sentinel"]["episode_count"] == 10
    assert execution["full_matrix"]["maximum_incremental_spend_usd"] == plan[
        "full_matrix"
    ]["conservative_maximum_cap_usd"]
    assert execution["sentinel"]["maximum_incremental_spend_usd"] == plan[
        "sentinel"
    ]["conservative_maximum_cap_usd"]
