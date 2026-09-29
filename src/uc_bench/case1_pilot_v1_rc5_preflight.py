"""Zero-cost execution rehearsal for the exact RC5 production path."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import uc_bench.case1_pilot_v1_rc4_preflight as inherited
from uc_bench.case1_pilot_v1_rc5_lock import INHERITED_EXTENSION_LOCK
from uc_bench.case1_pilot_v1_rc5_runner import (
    RC5_PREFLIGHT_AUTHORIZATION,
    run_case1_pilot_rc5_episode,
)
from uc_bench.model_runner import _write_json


@contextmanager
def _rc5_preflight_context() -> Iterator[None]:
    with INHERITED_EXTENSION_LOCK:
        originals = {
            "run_case1_pilot_rc4_episode": inherited.run_case1_pilot_rc4_episode,
            "RC4_PREFLIGHT_AUTHORIZATION": inherited.RC4_PREFLIGHT_AUTHORIZATION,
            "PREFLIGHT_KEY": inherited.PREFLIGHT_KEY,
        }
        inherited.run_case1_pilot_rc4_episode = run_case1_pilot_rc5_episode
        inherited.RC4_PREFLIGHT_AUTHORIZATION = RC5_PREFLIGHT_AUTHORIZATION
        inherited.PREFLIGHT_KEY = "sk-" + "or-v1-rc5-fake-transport-secret"
        try:
            yield
        finally:
            for name, value in originals.items():
                setattr(inherited, name, value)


def run_exact_production_preflight(project_root: Path, output_root: Path) -> dict[str, Any]:
    with _rc5_preflight_context():
        value = inherited.run_exact_production_preflight(project_root, output_root)
    checks = dict(value["checks"])
    summaries = sorted(output_root.rglob("run_summary.json"))
    checks["rc5_authoritative_lifecycle_present"] = len(summaries) == 4 and all(
        "authoritative_lifecycle" in __import__("json").loads(path.read_text(encoding="utf-8"))
        for path in summaries
    )
    return {
        **value,
        "schema_version": "uc-bench-case1-pilot-v1-rc5-production-preflight-1",
        "passed": all(checks.values()),
        "checks": checks,
    }


def write_exact_production_preflight(
    project_root: Path, output_root: Path, target: Path
) -> dict[str, Any]:
    value = run_exact_production_preflight(project_root, output_root)
    _write_json(target, value, secret="")
    return value


__all__ = ["run_exact_production_preflight", "write_exact_production_preflight"]
