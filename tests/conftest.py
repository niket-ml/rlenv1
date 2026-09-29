"""Repository-wide test safety guards."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def archived_release_write_guard(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force the one legacy replay-writing test to operate on a temporary copy.

    The old test calls a diagnostic generator with the repository root. That generator
    writes a timestamped file inside frozen RC1.4. Preserve the test's assertions while
    removing its authority to mutate archived release evidence.
    """

    if request.node.nodeid != (
        "tests/test_mmmvp_open_rc14.py::"
        "test_archived_replay_is_diagnostic_only_and_all_old_rules_are_now_disclosed"
    ):
        return
    function = request.node.function
    original = function.__globals__["replay_archived_submissions"]
    source_root = Path(__file__).resolve().parents[1]
    safe_root = tmp_path_factory.mktemp("archived-replay") / "copy"
    runs = Path("build/uc_bench_mmmvp_open_rc12_runs")
    shutil.copytree(source_root / runs, safe_root / runs)

    def safe_replay(_ignored_root: Path) -> dict[str, Any]:
        return original(safe_root)

    monkeypatch.setitem(function.__globals__, "replay_archived_submissions", safe_replay)
