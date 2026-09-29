from __future__ import annotations

import pytest

from uc_bench.errors import ConfigurationError
from uc_bench.hard_suite_runner import HardSuiteRunConfig


def test_hard_suite_runner_has_realistic_long_horizon_budget() -> None:
    config = HardSuiteRunConfig(
        model_id="provider/model",
        run_id="run",
        variant_id="dev_identity_more_rows",
        seed=1,
    )
    assert config.maximum_turns == 20
    assert config.maximum_total_completion_tokens == 24_000


@pytest.mark.parametrize("partition", ["answers", "astra_tuning"])
def test_hard_suite_runner_rejects_unknown_partition(partition: str) -> None:
    with pytest.raises(ConfigurationError):
        HardSuiteRunConfig(
            model_id="provider/model",
            run_id="run",
            variant_id="variant",
            seed=1,
            partition=partition,
        )
