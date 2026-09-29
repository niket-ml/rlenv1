"""RC1.4 environment: RC1.3 science and mechanics with complete public contract."""

from __future__ import annotations

import json

from uc_bench.mmmvp_open_rc12_environment import RC12OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc14_contract import RC14_AGENT_VISIBLE_CONTRACT


class RC14OpenMMMVPEnvironment(RC12OpenMMMVPEnvironment):
    """Replace only submission_contract.json before start-state hashes are captured."""

    def _neutralise_public_descriptions(self) -> None:
        super()._neutralise_public_descriptions()  # noqa: SLF001
        (self.run_root / "submission_contract.json").write_text(
            json.dumps(RC14_AGENT_VISIBLE_CONTRACT, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


__all__ = ["RC14OpenMMMVPEnvironment"]
