from pathlib import Path

from uc_bench.case2_mmmvp_v1_release import read_release_freeze
from uc_bench.case2_mmmvp_v1_supplemental import (
    MAXIMUM_AUTHORIZED_COST_USD,
    MODEL_ID,
    create_or_read_freeze,
)

ROOT = Path(__file__).resolve().parents[1]


def test_gpt5_supplement_locks_science_and_route() -> None:
    base = read_release_freeze(ROOT)
    supplement = create_or_read_freeze(ROOT)
    lock = supplement["science_lock"]
    binding = supplement["supplemental_budget_binding"]

    assert lock["case2_release_digest"] == base["aggregate_release_digest"]
    assert lock["agent_visible_archive_sha256"] == base["agent_visible_archive_sha256"]
    assert lock["host_only_archive_sha256"] == base["host_only_archive_sha256"]
    assert binding["model_configuration"][0]["model_id"] == MODEL_ID
    assert set(binding["provider_adapters"]) == {MODEL_ID}
    adapter = binding["provider_adapters"][MODEL_ID]
    assert adapter["provider_order"] == ["OpenAI"]
    assert adapter["allow_fallbacks"] is False
    assert supplement["maximum_authorized_cost_usd"] == MAXIMUM_AUTHORIZED_COST_USD
