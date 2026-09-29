#!/usr/bin/env python3
"""Create zero-cost RC1.2 fixtures, archived adjudication, and inheritance."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc12_compatibility import (
    create_rc12_compatibility_inheritance,
)
from uc_bench.mmmvp_open_rc12_trajectory import archived_rc11_adjudication
from uc_bench.model_runner import _write_json

ROOT = Path(__file__).resolve().parents[1]
RC11_RUN_ROOT = ROOT / "build/uc_bench_mmmvp_open_rc11_runs"
GLM_RUN = RC11_RUN_ROOT / "open-mmmvp-rc11-sentinel-00-z-ai-glm-5.2-case-02"
MISTRAL_RUN = RC11_RUN_ROOT / "open-mmmvp-rc11-sentinel-01-mistralai-mistral-large-2512-case-02"
FIXTURE_PATH = ROOT / "artifacts/mmmvp_open_rc12/mistral_false_positive_commands.json"
ADJUDICATION_PATH = ROOT / "artifacts/mmmvp_open_rc12/archived_rc11_replay_adjudication.json"


def _mistral_commands() -> list[dict[str, object]]:
    latest = json.loads((MISTRAL_RUN / "host_trajectory/latest.json").read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    expected_indices = (20, 21, 23, 24)
    for index in expected_indices:
        action = next(row for row in latest["tool_actions"] if int(row["action_index"]) == index)
        if (action.get("error") or {}).get("type") != "RecoverableWorkspacePathError":
            raise RuntimeError(
                f"Archived Mistral action {index} is not the preserved false positive"
            )
        command = str(action["invocation_arguments"]["command"])
        rows.append(
            {
                "action_index": index,
                "complete_command": command,
                "command_sha256": canonical_sha256(command),
                "expected_work_outputs": {
                    20: ["work/net_benefit_results.csv"],
                    21: ["work/net_benefit_results.csv"],
                    23: [],
                    24: ["work/subgroup_roc_auc_results.csv"],
                }[index],
            }
        )
    return rows


def main() -> int:
    if FIXTURE_PATH.exists() or ADJUDICATION_PATH.exists():
        raise RuntimeError("RC1.2 preparation artifacts already exist")
    commands = _mistral_commands()
    fixture = {
        "schema_version": "uc-bench-open-mmmvp-rc1-2-mistral-command-fixture-1",
        "created_at": datetime.now(UTC).isoformat(),
        "source_trajectory": MISTRAL_RUN.relative_to(ROOT).as_posix()
        + "/host_trajectory/latest.json",
        "complete_command_count": len(commands),
        "commands": commands,
    }
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_json(FIXTURE_PATH, fixture, secret="")

    glm = archived_rc11_adjudication(GLM_RUN)
    mistral = archived_rc11_adjudication(MISTRAL_RUN)
    if glm["counterfactual_rc12_reliability"] != 0.0:
        raise RuntimeError("Archived GLM reliability did not remain zero")
    if not mistral["trajectory_replay_health"]:
        raise RuntimeError("Archived Mistral trajectory did not reconstruct")
    if mistral["terminal_tool_status"] != "unexecuted_horizon":
        raise RuntimeError("Archived Mistral terminal tool was not closed in memory")
    if mistral["counterfactual_rc12_reliability"] != 0.0:
        raise RuntimeError("Archived Mistral reliability was not corrected to zero")
    adjudication = {
        "schema_version": "uc-bench-open-mmmvp-rc1-2-archived-replay-adjudication-1",
        "created_at": datetime.now(UTC).isoformat(),
        "api_requests": 0,
        "scientific_rescore": False,
        "source_artifacts_modified": False,
        "glm": glm,
        "mistral": mistral,
    }
    _write_json(ADJUDICATION_PATH, adjudication, secret="")
    inheritance = create_rc12_compatibility_inheritance(ROOT)
    print(
        json.dumps(
            {
                "status": "prepared",
                "api_requests": 0,
                "command_fixtures": len(commands),
                "archived_replays": 2,
                "compatibility_models_inherited": inheritance["inherited_model_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
