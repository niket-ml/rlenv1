"""Zero-cost crash-only corpus for RC1.6 verifier hardening."""

from __future__ import annotations

import copy
import json
import random
import shutil
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from uc_bench.mmmvp_open_controls import CONDITIONS, build_open_reference, run_open_controls
from uc_bench.mmmvp_open_rc16_verifier import verify_rc16_open_submission
from uc_bench.mmmvp_open_verifier import verify_open_submission

_SCORE_KEYS = (
    "complete_mission_success",
    "partial_scientific_quality",
    "reliability_score",
    "mission_failures",
    "first_decision_critical_failure",
    "failure_class",
)


def _score(grade: Any) -> dict[str, Any]:
    value = json.loads(json.dumps(grade.to_dict()))
    return {key: value[key] for key in _SCORE_KEYS}


def _grade_safely(
    grader: Any,
    root: Path,
    workspace: Path,
    submission: dict[str, Any],
    condition_id: str,
) -> tuple[dict[str, Any] | None, str | None, float]:
    started = time.monotonic()
    try:
        grade = _score(grader(root, workspace, submission, condition_id=condition_id))
        error = None
    except Exception as exc:
        grade = None
        error = type(exc).__name__
    return grade, error, time.monotonic() - started


def _relocate_submission(submission: dict[str, Any], workspace: Path) -> dict[str, Any]:
    value = json.loads(json.dumps(submission))
    value["host_record_locator"] = (
        (workspace.parent / ".mmmvp_host_records" / workspace.name).resolve().as_posix()
    )
    return value


def _mutate(path: Path, mutation: str) -> None:
    if mutation == "json_scalar":
        path.write_text("0.730311\n", encoding="utf-8")
    elif mutation == "json_null":
        path.write_text("null\n", encoding="utf-8")
    elif mutation == "json_malformed":
        path.write_text("{\n", encoding="utf-8")
    elif mutation == "json_invalid_utf8":
        path.write_bytes(b"\xff\xfe")
    elif mutation == "csv_empty":
        path.write_bytes(b"")
    elif mutation == "csv_ragged":
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join([*lines, "too,few"]) + "\n", encoding="utf-8")
    elif mutation == "csv_nonfinite":
        lines = path.read_text(encoding="utf-8").splitlines()
        header = lines[0].split(",")
        prediction = header.index("score")
        row = lines[1].split(",")
        row[prediction] = "nan"
        path.write_text("\n".join([lines[0], ",".join(row), *lines[2:]]) + "\n")
    elif mutation == "csv_extra_column":
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text(
            "\n".join([lines[0] + ",harmless", *[line + ",x" for line in lines[1:]]]) + "\n",
            encoding="utf-8",
        )
    else:
        raise ValueError(f"Unknown mutation {mutation}")


def run_rc16_crash_corpus(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    exceptions: list[dict[str, str]] = []
    changed_gradeable: list[str] = []
    prior_crashes_repaired: list[str] = []
    maximum_seconds = 0.0
    with TemporaryDirectory(prefix="uc-rc16-corpus-") as directory:
        scratch = Path(directory)
        base_controls = run_open_controls(root, scratch / "base-controls")
        with patch(
            "uc_bench.mmmvp_open_controls.verify_open_submission",
            verify_rc16_open_submission,
        ):
            rc16_controls = run_open_controls(root, scratch / "rc16-controls")
        control_keys = (
            "condition_id",
            "control",
            "complete_mission_success",
            "partial_scientific_quality",
            "mission_failures",
            "failure_class",
        )
        controls_unchanged = [
            tuple(row[key] for key in control_keys) for row in base_controls["results"]
        ] == [tuple(row[key] for key in control_keys) for row in rc16_controls["results"]]

        mutation_rows: list[dict[str, Any]] = []
        for condition_index, condition_id in enumerate(CONDITIONS):
            for alternative in (False, True):
                label = f"{condition_id}-{'alternative' if alternative else 'reference'}"
                submission, source = build_open_reference(
                    root,
                    condition_id,
                    scratch / f"source-{condition_index}-{int(alternative)}",
                    alternative=alternative,
                )
                final = submission["final_submission"]
                output = next(
                    row for row in final["artifact_manifest"] if row["role"] == "CALCULATION_OUTPUT"
                )
                table = next(
                    row for row in final["artifact_manifest"] if row["role"] == "ANALYSIS_TABLE"
                )
                for mutation, relative in (
                    ("json_scalar", output["path"]),
                    ("json_malformed", output["path"]),
                    ("csv_nonfinite", table["path"]),
                    ("csv_extra_column", table["path"]),
                ):
                    workspace = scratch / f"mutation-{label}-{mutation}"
                    shutil.copytree(source, workspace)
                    host_source = source.parent / ".mmmvp_host_records" / source.name
                    host_target = workspace.parent / ".mmmvp_host_records" / workspace.name
                    if host_source.is_dir():
                        shutil.copytree(host_source, host_target)
                    relocated = _relocate_submission(submission, workspace)
                    _mutate(workspace / relative, mutation)
                    base, base_error, base_seconds = _grade_safely(
                        verify_open_submission, root, workspace, relocated, condition_id
                    )
                    hardened, hardened_error, hardened_seconds = _grade_safely(
                        verify_rc16_open_submission,
                        root,
                        workspace,
                        relocated,
                        condition_id,
                    )
                    maximum_seconds = max(maximum_seconds, base_seconds, hardened_seconds)
                    case = f"{label}:{mutation}"
                    if hardened_error:
                        exceptions.append({"case": case, "error": hardened_error})
                    if base_error and not hardened_error:
                        prior_crashes_repaired.append(case)
                    if base is not None and hardened != base:
                        changed_gradeable.append(case)
                    mutation_rows.append(
                        {
                            "case": case,
                            "prior_error": base_error,
                            "rc16_error": hardened_error,
                            "scores_unchanged_when_previously_gradeable": (
                                base is None or hardened == base
                            ),
                            "elapsed_seconds": round(hardened_seconds, 6),
                        }
                    )

        archived_rows: list[dict[str, Any]] = []
        for summary_path in sorted(root.glob("build/**/run_summary.json")):
            if "mmmvp_open" not in summary_path.as_posix():
                continue
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            submission = summary.get("submission") or {}
            if not (submission.get("state") or {}).get("completion_accepted"):
                continue
            workspace = summary_path.parent / "workspace"
            condition_id = str(summary.get("condition_id") or "")
            if not workspace.is_dir() or condition_id not in CONDITIONS:
                continue
            hardened, error, seconds = _grade_safely(
                verify_rc16_open_submission,
                root,
                workspace,
                submission,
                condition_id,
            )
            maximum_seconds = max(maximum_seconds, seconds)
            previous = summary.get("diagnostic_grade")
            previous_score = (
                {key: previous[key] for key in _SCORE_KEYS} if isinstance(previous, dict) else None
            )
            unchanged = previous_score is None or previous_score == hardened
            if error:
                exceptions.append(
                    {"case": summary_path.relative_to(root).as_posix(), "error": error}
                )
            if previous_score is not None and not unchanged:
                changed_gradeable.append(summary_path.relative_to(root).as_posix())
            archived_rows.append(
                {
                    "summary": summary_path.relative_to(root).as_posix(),
                    "previously_gradeable": previous_score is not None,
                    "rc16_error": error,
                    "previous_score_unchanged": unchanged,
                    "rc16_score": hardened,
                }
            )

        fuzz_submission, fuzz_workspace = build_open_reference(
            root, "case_02", scratch / "submission-fuzz-source", alternative=False
        )
        leaves: list[tuple[Any, ...]] = []

        def visit(value: Any, path: tuple[Any, ...] = ()) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    visit(child, (*path, key))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, (*path, index))
            else:
                leaves.append(path)

        visit(fuzz_submission["final_submission"])
        random.Random(16).shuffle(leaves)
        shapes: list[Any] = [None, True, 0, 1e309, "", [], {}, [None], {"x": None}]
        fuzz_count = 0
        for path in leaves[:150]:
            for shape in random.Random(str(path)).sample(shapes, 2):
                candidate = copy.deepcopy(fuzz_submission)
                cursor = candidate["final_submission"]
                for key in path[:-1]:
                    cursor = cursor[key]
                cursor[path[-1]] = shape
                _, error, seconds = _grade_safely(
                    verify_rc16_open_submission,
                    root,
                    fuzz_workspace,
                    candidate,
                    "case_02",
                )
                fuzz_count += 1
                maximum_seconds = max(maximum_seconds, seconds)
                if error:
                    exceptions.append({"case": f"submission-fuzz:{path}:{shape!r}", "error": error})

    passed = bool(
        base_controls["status"] == rc16_controls["status"] == "passed"
        and controls_unchanged
        and not exceptions
        and not changed_gradeable
        and maximum_seconds < 30
    )
    return {
        "schema_version": "uc-bench-open-mmmvp-rc1-6-crash-corpus-1",
        "status": "passed" if passed else "failed",
        "api_requests": 0,
        "base_control_count": len(base_controls["results"]),
        "declared_scientific_control_count": 35,
        "full_control_row_count": len(rc16_controls["results"]),
        "controls_unchanged": controls_unchanged,
        "reference_and_alternative_passes_unchanged": rc16_controls[
            "reference_and_two_workflows_pass"
        ],
        "anti_gaming_failures_unchanged": rc16_controls["negative_controls_rejected"],
        "mutated_workspace_count": len(mutation_rows),
        "mutations": mutation_rows,
        "archived_accepted_workspace_count": len(archived_rows),
        "archived": archived_rows,
        "systematic_submission_field_mutation_count": fuzz_count,
        "prior_crashes_repaired": prior_crashes_repaired,
        "previously_gradeable_changes": changed_gradeable,
        "verifier_exceptions": exceptions,
        "hangs": [],
        "maximum_single_grade_seconds": round(maximum_seconds, 6),
    }


__all__ = ["run_rc16_crash_corpus"]
