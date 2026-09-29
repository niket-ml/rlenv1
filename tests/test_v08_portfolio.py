from __future__ import annotations

import copy
from pathlib import Path

from uc_bench.v08_portfolio import load_v08_portfolio, validate_v08_portfolio

ROOT = Path(__file__).resolve().parents[1]


def test_v08_portfolio_has_eight_validity_cards_and_sixteen_states() -> None:
    result = validate_v08_portfolio(load_v08_portfolio(ROOT))
    assert result.passed, result.errors
    assert result.investigation_count == 8
    assert result.new_investigation_count == 7
    assert result.controlled_state_count == 16
    assert result.trap_free_case_count == 8


def test_every_case_has_same_appearance_opposite_action_variants() -> None:
    portfolio = load_v08_portfolio(ROOT)
    for case in portfolio["cases"]:
        assert len({row["shared_start_state_id"] for row in case["hidden_variants"]}) == 1
        assert len({row["supported_final_action"] for row in case["hidden_variants"]}) >= 2


def test_contract_trap_is_rejected() -> None:
    portfolio = copy.deepcopy(load_v08_portfolio(ROOT))
    portfolio["cases"][0]["contract_trap_audit"]["requires_exact_prose"] = True
    result = validate_v08_portfolio(portfolio)
    assert not result.passed
    assert "V08-D01:contract_trap_present" in result.errors


def test_unpaired_intervention_claim_is_rejected() -> None:
    portfolio = copy.deepcopy(load_v08_portfolio(ROOT))
    portfolio["cases"][0]["failure_interventions"][0][
        "demonstrated_only_if_paired"
    ] = False
    result = validate_v08_portfolio(portfolio)
    assert not result.passed
    assert "V08-D01:intervention_claim_not_conditioned_on_pair" in result.errors
