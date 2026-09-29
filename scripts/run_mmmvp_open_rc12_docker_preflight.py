#!/usr/bin/env python3
"""Exercise the exact RC1.2 physical boundary without contacting a model."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from uc_bench.mmmvp_open_controls import build_open_reference
from uc_bench.mmmvp_open_rc12_environment import (
    ProtectedEvidenceTampering,
    RC12OpenMMMVPEnvironment,
    RecoverableWorkspacePathError,
    rc12_isolation_passed,
)
from uc_bench.mmmvp_open_rc12_runner import rc12_runtime_factory

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "artifacts/mmmvp_open_rc12/mistral_false_positive_commands.json"
RC11_MISTRAL = ROOT / (
    "build/uc_bench_mmmvp_open_rc11_runs/"
    "open-mmmvp-rc11-sentinel-01-mistralai-mistral-large-2512-case-02/workspace"
)


def _denied(runtime: object, command: str) -> str:
    try:
        runtime.run_command(command)  # type: ignore[attr-defined]
    except RecoverableWorkspacePathError:
        return "recoverable"
    raise AssertionError(f"Expected a physical read-only denial: {command}")


def _success(runtime: object, command: str) -> dict[str, object]:
    value = json.loads(runtime.run_command(command))  # type: ignore[attr-defined]
    if value["exit_code"] != 0:
        raise AssertionError(f"Command failed unexpectedly: {command}\n{value}")
    return value


def _new_runtime(root: Path, name: str) -> tuple[object, object]:
    core = RC12OpenMMMVPEnvironment(ROOT, "case_02", root / name / "workspace")
    runtime = rc12_runtime_factory(
        core.run_root,
        container_name=f"uc-mmmvp-rc12-{name}",
        image="uc-bench-agent:0.1",
        core=core,
    )
    runtime.start()
    isolation = runtime.security_snapshot()
    if not rc12_isolation_passed(isolation):
        runtime.stop()
        raise AssertionError("Nested read-only/writable mount boundary failed")
    core.mark_workspace_boundary_enforced(True)
    return core, runtime


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="uc-mmmvp-rc12-docker-") as temporary:
        root = Path(temporary)
        core, runtime = _new_runtime(root, "commands")
        isolation = runtime.security_snapshot()
        try:
            source = RC11_MISTRAL / "work/patient_level_data.csv"
            shutil.copy2(source, core.run_root / "work/patient_level_data.csv")
            fixtures = json.loads(FIXTURE.read_text(encoding="utf-8"))["commands"]
            exact_results: list[dict[str, object]] = []
            for fixture in fixtures:
                before_count = core.recoverable_contract_violation_count
                result = _success(runtime, fixture["complete_command"])
                for relative in fixture["expected_work_outputs"]:
                    if not (core.run_root / relative).is_file():
                        raise AssertionError(f"Exact command omitted {relative}")
                if core.recoverable_contract_violation_count != before_count:
                    raise AssertionError("Exact Mistral command triggered a path violation")
                if not core.integrity_status()["protected_evidence_untampered"]:
                    raise AssertionError("Exact Mistral command changed protected evidence")
                exact_results.append(
                    {
                        "action_index": fixture["action_index"],
                        "exit_code": result["exit_code"],
                        "stdout": result["stdout"],
                    }
                )

            quoted = [
                'python3 -c "threshold=.5; y_pred=.7; print(y_pred >= threshold)"',
                'python3 -c "subset=[1,2]; print(len(subset) > 1)"',
                'python3 -c "x=2; upper=3; print(x <= upper)"',
                "python3 -c \"print({'symbol': '>', 'nested': {'value': '>>'}})\"",
                "python3 - <<'PY'\nprint({'comparison': 'x > 1'})\nPY",
                "awk 'BEGIN { x=2; if (x > 1) print x }'",
                "printf 'a,b\\n1,2\\n' > work/result.csv",
            ]
            for command in quoted:
                _success(runtime, command)
            if not (core.run_root / "work/result.csv").is_file():
                raise AssertionError("work/ shell redirection did not succeed")
            root_denials = {
                "relative_root": _denied(runtime, "printf x > result.csv"),
                "absolute_root": _denied(runtime, "printf x > /workspace/result-absolute.csv"),
                "traversal": _denied(runtime, "printf x > work/../result-traversal.csv"),
                "tmp": _denied(runtime, "printf x > /tmp/result-tmp.csv"),
            }
            for relative in ("result.csv", "result-absolute.csv", "result-traversal.csv"):
                if (core.run_root / relative).exists():
                    raise AssertionError(f"Outside-work file was created: {relative}")
            denied_mutations = [
                "rm data/locked_predictions.csv",
                "mv data/locked_predictions.csv work/moved.csv",
                "cp work/result.csv data/locked_predictions.csv",
                "sed -i 's/a/b/' data/locked_predictions.csv",
                "truncate -s 0 data/locked_predictions.csv",
                "python3 -c \"open('data/locked_predictions.csv','w').write('x')\"",
                "printf x > work/../data/locked_predictions.csv",
                "printf x > /workspace/data/locked_predictions.csv",
                "ln data/locked_predictions.csv work/hard.csv",
            ]
            original = (core.run_root / "data/locked_predictions.csv").read_bytes()
            for command in denied_mutations:
                _denied(runtime, command)
                if (core.run_root / "data/locked_predictions.csv").read_bytes() != original:
                    raise AssertionError(f"Protected evidence changed: {command}")
        finally:
            runtime.stop()

        alias_core, alias_runtime = _new_runtime(root, "alias")
        try:
            try:
                alias_runtime.run_command(
                    "ln -s ../data/locked_predictions.csv work/protected-link.csv"
                )
            except ProtectedEvidenceTampering:
                alias_terminal = True
            else:
                raise AssertionError("Writable symlink alias did not fail closed")
            if alias_core.state.phase != "terminal":
                raise AssertionError("Alias escape did not terminate the episode")
            if not alias_core.integrity_status()["protected_evidence_untampered"]:
                raise AssertionError("Symlink attempt changed protected evidence")
        finally:
            alias_runtime.stop()

        reference, _ = build_open_reference(ROOT, "case_02", root / "reference", alternative=False)
        reveal_core, reveal_runtime = _new_runtime(root, "reveal")
        try:
            reveal_core.commit_validation_plan(json.dumps(reference["validation_plan"]))
            reveal_core.reveal_validation()
            revealed = next((reveal_core.run_root / "revealed").rglob("*.csv"))
            _denied(
                reveal_runtime,
                f"rm {revealed.relative_to(reveal_core.run_root).as_posix()}",
            )
            if not reveal_core.integrity_status()["protected_evidence_untampered"]:
                raise AssertionError("Revealed evidence changed")
            reveal_core.commit_followup_plan(json.dumps(reference["followup_plan"]))
            reveal_core.purchase_resource(reference["followup_plan"]["chosen_resource"])
            purchased = next((reveal_core.run_root / "purchased").rglob("*.csv"))
            _denied(
                reveal_runtime,
                'python3 -c "open('
                f"'{purchased.relative_to(reveal_core.run_root).as_posix()}',"
                "'w').write('x')\"",
            )
            if not reveal_core.integrity_status()["protected_evidence_untampered"]:
                raise AssertionError("Purchased evidence changed")
        finally:
            reveal_runtime.stop()

        output = {
            "status": "passed",
            "api_requests": 0,
            "scientific_requests": 0,
            "exact_mistral_commands": exact_results,
            "quoted_payload_count": len(quoted),
            "root_denials": root_denials,
            "denied_mutation_count": len(denied_mutations),
            "symlink_alias_terminal": alias_terminal,
            "revealed_and_purchased_evidence_unchanged": True,
            "isolation": isolation,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
