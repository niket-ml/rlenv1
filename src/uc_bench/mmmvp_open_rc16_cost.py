"""RC1.6 cost gate over the unchanged nine-model launch panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from uc_bench.mmmvp_open_rc15_cost import _funding, calculate_rc15_cost_plan
from uc_bench.model_runner import _write_json

COST_PLAN_PATH = Path("artifacts/mmmvp_open_rc16/cost_plan.json")
SCIENTIFIC_HARD_CAP_USD = 50.0


def calculate_rc16_cost_plan(project_root: Path, *, key: str | None = None) -> dict[str, Any]:
    source = calculate_rc15_cost_plan(project_root)
    funding = _funding(key) if key is not None else None
    p90 = float(source["sentinel_no_cache_p90_usd"])
    allowed = bool(
        funding is not None
        and p90 <= SCIENTIFIC_HARD_CAP_USD
        and funding["effective_remaining_usd"] >= SCIENTIFIC_HARD_CAP_USD
    )
    return {
        **source,
        "schema_version": "uc-bench-open-mmmvp-rc1-6-cost-plan-1",
        "status": "passed" if allowed else "rehearsal_only",
        "scientific_hard_cap_usd": SCIENTIFIC_HARD_CAP_USD,
        "funding": funding,
        "paid_execution_allowed": allowed,
        "minimum_account_top_up_required_usd": (
            None
            if funding is None
            else max(0.0, SCIENTIFIC_HARD_CAP_USD - funding["effective_remaining_usd"])
        ),
        "minimum_cap_increase_required_usd": (
            None
            if funding is None
            else max(0.0, SCIENTIFIC_HARD_CAP_USD - funding["key_limit_remaining_usd"])
        ),
    }


def write_rc16_cost_plan(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / COST_PLAN_PATH
    if target.exists():
        raise FileExistsError("RC1.6 cost plan already exists")
    value = calculate_rc16_cost_plan(root, key=key)
    _write_json(target, value, secret=key)
    return value


__all__ = [
    "COST_PLAN_PATH",
    "SCIENTIFIC_HARD_CAP_USD",
    "calculate_rc16_cost_plan",
    "write_rc16_cost_plan",
]
