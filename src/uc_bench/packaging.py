"""Build reproducible, leakage-checked agent start states."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError, SealedCohortLeakageError
from uc_bench.hashing import canonical_sha256, sha256_file

CONDITIONS = ("full_data", "data_withheld")
TASK_ID = "uc_biomarker_diligence_v0"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass(frozen=True, slots=True)
class StartStatePackage:
    condition: str
    workspace_root: Path
    manifest_path: Path
    file_count: int
    package_digest: str


@dataclass(slots=True)
class StartStateBuilder:
    project_root: Path

    def build(
        self,
        condition: str,
        *,
        output_root: Path,
        replace: bool = False,
    ) -> StartStatePackage:
        if condition not in CONDITIONS:
            raise ConfigurationError(f"Unsupported start-state condition: {condition}")

        destination = output_root / condition
        if destination.exists():
            if not replace:
                raise ConfigurationError(f"Start state already exists: {destination}")
            shutil.rmtree(destination)
        destination.mkdir(parents=True)

        task_root = self.project_root / "tasks" / TASK_ID
        if not task_root.is_dir():
            raise ConfigurationError(f"Missing task assets: {task_root}")
        for source in sorted(
            path
            for path in task_root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        ):
            self._copy(source, destination / source.relative_to(task_root))

        public_configs = (
            "benchmark.json",
            "cohorts.json",
            "milestone_weights.json",
            "reward_weights.json",
            f"tasks/{TASK_ID}.json",
        )
        for relative_path in public_configs:
            self._copy(
                self.project_root / "configs" / relative_path,
                destination / "reference" / relative_path,
            )

        if condition == "full_data":
            development_root = self.project_root / "data" / "processed" / "development"
            for name in (
                "metadata.csv",
                "GSE16879_gene_expression.csv.gz",
                "GSE73661_gene_expression.csv.gz",
            ):
                self._copy(development_root / name, destination / "data" / name)
        else:
            withheld = destination / "data" / "DATA_WITHHELD.md"
            withheld.parent.mkdir(parents=True, exist_ok=True)
            withheld.write_text(
                "# Data-withheld control\n\n"
                "Development matrices and patient outcomes are intentionally absent. "
                "Complete the same commitment and decision workflow using only supplied "
                "documentation, and do not represent remembered literature as executed "
                "analysis.\n",
                encoding="utf-8",
            )

        state = {
            "schema_version": "0.1",
            "task_id": TASK_ID,
            "condition": condition,
            "sealed_features_visible": False,
            "sealed_outcomes_visible": False,
            "individual_validation_predictions_visible": False,
        }
        _write_json(destination / "START_STATE.json", state)
        (destination / "submission").mkdir()
        (destination / "results").mkdir()

        sealed_ids = self._load_sealed_sample_ids()
        self._assert_no_sealed_sample_ids(destination, sealed_ids)
        rows = self._file_rows(destination)
        manifest = {
            "schema_version": "0.1",
            "task_id": TASK_ID,
            "condition": condition,
            "files": rows,
            "package_digest": canonical_sha256(rows),
            "sealed_sample_id_scan": {
                "forbidden_id_count": len(sealed_ids),
                "matches": 0,
                "passed": True,
            },
        }
        manifest_path = output_root / "manifests" / f"{condition}.json"
        _write_json(manifest_path, manifest)
        return StartStatePackage(
            condition=condition,
            workspace_root=destination,
            manifest_path=manifest_path,
            file_count=len(rows),
            package_digest=manifest["package_digest"],
        )

    def _copy(self, source: Path, destination: Path) -> None:
        if not source.is_file():
            raise ConfigurationError(f"Required start-state source is missing: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    def _load_sealed_sample_ids(self) -> set[str]:
        import pandas as pd

        path = self.project_root / "grader_private" / "data" / "gse92415_labels.csv"
        if not path.is_file():
            raise ConfigurationError("Private sealed-label manifest is required for leakage scan")
        labels = pd.read_csv(path, usecols=["sample_id"])
        return set(labels["sample_id"].astype(str))

    @staticmethod
    def _assert_no_sealed_sample_ids(root: Path, sealed_ids: set[str]) -> None:
        encoded_ids = {sample_id: sample_id.encode() for sample_id in sealed_ids}
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            content = path.read_bytes()
            matches = [
                sample_id
                for sample_id, encoded in encoded_ids.items()
                if encoded in content
            ]
            if matches:
                relative = path.relative_to(root).as_posix()
                raise SealedCohortLeakageError(
                    f"Start-state file {relative} exposes sealed sample IDs: {matches[:5]}"
                )

    @staticmethod
    def _file_rows(root: Path) -> list[dict[str, Any]]:
        return [
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file())
        ]
