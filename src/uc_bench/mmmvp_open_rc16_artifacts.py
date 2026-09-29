"""Total, provenance-aware artifact validation for open MMMVP RC1.6.

The scientific rules remain those of the frozen open-MMMVP verifier.  This
module owns only the trust boundary around agent-created files.
"""

from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from uc_bench.mmmvp_open_calculations import (
    _VALUE_TOLERANCE,
    CalculationResult,
    VerifiedTable,
    _cluster_bootstrap_interval,
    _expected_records,
    calculate_metric,
    verify_analysis_table,
)

ArtifactOrigin = Literal["agent_controlled", "environment_controlled"]


@dataclass(frozen=True, slots=True)
class ArtifactValidationResult:
    valid: bool
    artifact_id: str
    artifact_path: str | None
    expected_artifact_role: str
    observed_top_level_type: str
    fault_codes: tuple[str, ...]
    linked_calculation_ids: tuple[str, ...]
    origin: ArtifactOrigin

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _add_fault(faults: list[str], code: str) -> None:
    if code not in faults:
        faults.append(code)


class _AgentArtifactParseError(ValueError):
    """Expected malformed input from an agent-owned JSON artifact."""


class _JsonStream:
    """Small bounded-memory JSON reader for calculation-output artifacts."""

    def __init__(self, path: Path) -> None:
        self._handle = path.open(encoding="utf-8", errors="strict", newline="")
        self._buffer = ""
        self._index = 0
        self._ended = False

    def close(self) -> None:
        self._handle.close()

    def _fill(self) -> None:
        if self._index < len(self._buffer) or self._ended:
            return
        self._buffer = self._handle.read(65_536)
        self._index = 0
        self._ended = not self._buffer

    def peek(self) -> str:
        self._fill()
        return "" if self._ended else self._buffer[self._index]

    def take(self) -> str:
        value = self.peek()
        if value:
            self._index += 1
        return value

    def whitespace(self) -> None:
        while self.peek() in {" ", "\t", "\r", "\n"}:
            self.take()

    def require(self, expected: str) -> None:
        if self.take() != expected:
            raise _AgentArtifactParseError(f"expected {expected!r}")

    def string(self, *, capture_limit: int = 0) -> str | None:
        self.require('"')
        captured: list[str] = []
        overflow = False
        escapes = {
            '"': '"',
            "\\": "\\",
            "/": "/",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
        }
        while True:
            char = self.take()
            if not char:
                raise _AgentArtifactParseError("unterminated string")
            if char == '"':
                return None if overflow else "".join(captured)
            if ord(char) < 0x20:
                raise _AgentArtifactParseError("control character in string")
            if char == "\\":
                escaped = self.take()
                if escaped == "u":
                    digits = "".join(self.take() for _ in range(4))
                    if len(digits) != 4 or any(
                        item not in "0123456789abcdefABCDEF" for item in digits
                    ):
                        raise _AgentArtifactParseError("invalid unicode escape")
                    char = chr(int(digits, 16))
                elif escaped in escapes:
                    char = escapes[escaped]
                else:
                    raise _AgentArtifactParseError("invalid string escape")
            if capture_limit:
                if len(captured) < capture_limit:
                    captured.append(char)
                else:
                    overflow = True

    def literal(self, expected: str) -> None:
        for char in expected:
            self.require(char)

    def number(self) -> float:
        sign = -1.0 if self.peek() == "-" else 1.0
        if sign < 0:
            self.take()
        first = self.take()
        if not first or not first.isdigit():
            raise _AgentArtifactParseError("invalid number")
        digits: list[str] = []
        total_digits = 1
        fraction_digits = 0
        first_nonzero: int | None = 0 if first != "0" else None
        if first != "0":
            digits.append(first)
            while self.peek().isdigit():
                char = self.take()
                if len(digits) < 40:
                    digits.append(char)
                total_digits += 1
        elif self.peek().isdigit():
            raise _AgentArtifactParseError("leading zero in number")
        if self.peek() == ".":
            self.take()
            if not self.peek().isdigit():
                raise _AgentArtifactParseError("fraction requires a digit")
            while self.peek().isdigit():
                char = self.take()
                if first_nonzero is None and char != "0":
                    first_nonzero = total_digits
                if first_nonzero is not None and len(digits) < 40:
                    digits.append(char)
                total_digits += 1
                fraction_digits += 1
        explicit_exponent = 0
        if self.peek() in {"e", "E"}:
            self.take()
            exponent_sign = -1 if self.peek() == "-" else 1
            if self.peek() in {"+", "-"}:
                self.take()
            if not self.peek().isdigit():
                raise _AgentArtifactParseError("exponent requires a digit")
            while self.peek().isdigit():
                digit = int(self.take())
                if explicit_exponent <= 10_000:
                    explicit_exponent = explicit_exponent * 10 + digit
            explicit_exponent *= exponent_sign
        if first_nonzero is None:
            return math.copysign(0.0, sign)
        exponent = total_digits - fraction_digits - first_nonzero - 1 + explicit_exponent
        significand = digits[0]
        if len(digits) > 1:
            significand += "." + "".join(digits[1:])
        try:
            return sign * float(f"{significand}e{exponent}")
        except (OverflowError, ValueError):
            return math.copysign(math.inf, sign)

    def skip_value(self) -> None:
        """Validate and discard one arbitrary JSON value without recursive state."""

        stack: list[str] = []
        while True:
            self.whitespace()
            char = self.peek()
            if char == '"':
                self.string()
            elif char == "{":
                self.take()
                self.whitespace()
                if self.peek() == "}":
                    self.take()
                else:
                    if self.peek() != '"':
                        raise _AgentArtifactParseError("object key must be a string")
                    self.string()
                    self.whitespace()
                    self.require(":")
                    stack.append("object")
                    continue
            elif char == "[":
                self.take()
                self.whitespace()
                if self.peek() == "]":
                    self.take()
                else:
                    stack.append("array")
                    continue
            elif char == "t":
                self.literal("true")
            elif char == "f":
                self.literal("false")
            elif char == "n":
                self.literal("null")
            elif char == "-" or char.isdigit():
                self.number()
            else:
                raise _AgentArtifactParseError("invalid JSON value")

            while stack:
                self.whitespace()
                container = stack[-1]
                separator = self.take()
                closing = "]" if container == "array" else "}"
                if separator == closing:
                    stack.pop()
                    continue
                if separator != ",":
                    raise _AgentArtifactParseError(f"invalid {container} separator")
                if container == "object":
                    self.whitespace()
                    if self.peek() != '"':
                        raise _AgentArtifactParseError("object key must be a string")
                    self.string()
                    self.whitespace()
                    self.require(":")
                break
            else:
                return


def _observed_json_type(char: str) -> str:
    if char == "{":
        return "object"
    if char == "[":
        return "array"
    if char == '"':
        return "string"
    if char in {"t", "f"}:
        return "boolean"
    if char == "n":
        return "null"
    if char == "-" or char.isdigit():
        return "number"
    return "unknown"


def _parse_calculation_item(
    reader: _JsonStream,
    calculation_id: str,
) -> tuple[str | None, float | None, list[str]]:
    reader.require("{")
    linked_id: str | None = None
    reported: float | None = None
    faults: list[str] = []
    seen_calculation_id = False
    seen_reported_value = False
    reader.whitespace()
    if reader.peek() == "}":
        reader.take()
        return linked_id, reported, faults
    while True:
        reader.whitespace()
        key = reader.string(capture_limit=64)
        reader.whitespace()
        reader.require(":")
        reader.whitespace()
        if key == "calculation_id":
            if seen_calculation_id:
                _add_fault(faults, "typed_calculation_field_duplicate")
            seen_calculation_id = True
        elif key == "reported_value":
            if seen_reported_value:
                _add_fault(faults, "typed_calculation_field_duplicate")
            seen_reported_value = True
        if key == "calculation_id" and reader.peek() == '"':
            linked_id = reader.string(capture_limit=max(129, len(calculation_id) + 1))
        elif key == "reported_value" and (reader.peek() == "-" or reader.peek().isdigit()):
            reported = reader.number()
        else:
            reader.skip_value()
        reader.whitespace()
        separator = reader.take()
        if separator == "}":
            return linked_id, reported, faults
        if separator != ",":
            raise _AgentArtifactParseError("invalid calculation object separator")


def _stream_calculation_output(
    path: Path,
    calculation_id: str,
) -> tuple[str, bool, int, float | None, list[str]]:
    reader = _JsonStream(path)
    linked = False
    match_count = 0
    matched_value: float | None = None
    faults: list[str] = []
    observed = "empty"
    try:
        reader.whitespace()
        observed = _observed_json_type(reader.peek())
        if reader.peek() != "{":
            if reader.peek():
                reader.skip_value()
                reader.whitespace()
                if reader.peek():
                    raise _AgentArtifactParseError("trailing JSON data")
            _add_fault(faults, "top_level_object_required")
            return observed, linked, match_count, matched_value, faults
        reader.take()
        seen_typed = False
        reader.whitespace()
        if reader.peek() == "}":
            reader.take()
        else:
            while True:
                reader.whitespace()
                key = reader.string(capture_limit=64)
                reader.whitespace()
                reader.require(":")
                reader.whitespace()
                if key == "typed_calculations":
                    if seen_typed:
                        _add_fault(faults, "typed_calculations_duplicate")
                    seen_typed = True
                    if reader.peek() != "[":
                        reader.skip_value()
                        _add_fault(faults, "typed_calculations_list_required")
                    else:
                        reader.take()
                        reader.whitespace()
                        if reader.peek() == "]":
                            reader.take()
                        else:
                            while True:
                                reader.whitespace()
                                if reader.peek() != "{":
                                    reader.skip_value()
                                    _add_fault(
                                        faults, "typed_calculation_item_object_required"
                                    )
                                else:
                                    linked_id, reported, item_faults = _parse_calculation_item(
                                        reader, calculation_id
                                    )
                                    for fault in item_faults:
                                        _add_fault(faults, fault)
                                    if linked_id == calculation_id:
                                        linked = True
                                        match_count += 1
                                        matched_value = reported
                                reader.whitespace()
                                separator = reader.take()
                                if separator == "]":
                                    break
                                if separator != ",":
                                    raise _AgentArtifactParseError("invalid array separator")
                else:
                    reader.skip_value()
                reader.whitespace()
                separator = reader.take()
                if separator == "}":
                    break
                if separator != ",":
                    raise _AgentArtifactParseError("invalid object separator")
        reader.whitespace()
        if reader.peek():
            raise _AgentArtifactParseError("trailing JSON data")
        if not seen_typed:
            _add_fault(faults, "typed_calculations_missing")
        return observed, linked, match_count, matched_value, faults
    finally:
        reader.close()


def validate_calculation_output(
    artifact: tuple[dict[str, Any], Path] | None,
    calculation_id: str,
    reported_value: float,
) -> ArtifactValidationResult:
    """Validate one disclosed CALCULATION_OUTPUT link without throwing.

    The payload must be an object containing a list of objects.  Exactly one
    row must link the requested calculation and its value must be finite.
    """

    artifact_id = ""
    relative: str | None = None
    faults: list[str] = []
    linked: list[str] = []
    observed = "missing"
    if artifact is None:
        return ArtifactValidationResult(
            False,
            artifact_id,
            relative,
            "CALCULATION_OUTPUT",
            observed,
            ("artifact_missing",),
            (),
            "agent_controlled",
        )
    manifest, path = artifact
    artifact_id = str(manifest.get("artifact_id") or "")
    relative = str(manifest.get("path") or path.name)
    if manifest.get("role") != "CALCULATION_OUTPUT":
        faults.append("artifact_role_mismatch")
    try:
        if path.stat().st_size == 0:
            faults.append("artifact_empty")
            parsed_output = None
        else:
            parsed_output = _stream_calculation_output(path, calculation_id)
    except OSError:
        faults.append("artifact_unreadable")
        parsed_output = None
    except UnicodeDecodeError:
        faults.append("invalid_utf8")
        parsed_output = None
    except (MemoryError, RecursionError, _AgentArtifactParseError):
        faults.append("malformed_json")
        parsed_output = None
    if parsed_output is not None:
        observed, parsed_linked, match_count, matched_value, parsed_faults = parsed_output
        if parsed_linked:
            linked.append(calculation_id)
        faults.extend(parsed_faults)
        if match_count == 0:
            faults.append("calculation_id_missing")
        elif match_count > 1:
            faults.append("calculation_id_duplicate")
        else:
            value = matched_value
            if value is None or not math.isfinite(value):
                faults.append("reported_value_not_finite_numeric")
            elif not math.isclose(value, reported_value, abs_tol=1e-12):
                faults.append("reported_value_mismatch")
    return ArtifactValidationResult(
        valid=not faults,
        artifact_id=artifact_id,
        artifact_path=relative,
        expected_artifact_role="CALCULATION_OUTPUT",
        observed_top_level_type=observed,
        fault_codes=_dedupe(faults),
        linked_calculation_ids=tuple(sorted(set(linked))),
        origin="agent_controlled",
    )


def _csv_shape_faults(
    path: Path,
    mapping: Any,
    *,
    maximum_scientifically_possible_rows: int | None,
) -> tuple[list[str], str]:
    faults: list[str] = []
    try:
        handle = path.open(encoding="utf-8", newline="")
    except OSError:
        return ["artifact_unreadable"], "missing"
    try:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader)
        except StopIteration:
            return ["artifact_empty"], "empty"
        if not header or all(not str(item).strip() for item in header):
            return ["csv_header_missing"], "csv"
        if len(header) != len(set(header)):
            faults.append("duplicate_csv_header")
        if not isinstance(mapping, dict):
            faults.append("column_map_object_required")
            return faults, "csv"
        required_roles = {
            "entity_id",
            "source_record_ids",
            "prediction",
            "outcome",
            "split",
        }
        if not required_roles <= set(mapping):
            faults.append("mapped_column_role_missing")
        mapped = [value for value in mapping.values() if isinstance(value, str)]
        if any(column not in header for column in mapped):
            faults.append("mapped_csv_column_missing")
        if faults:
            return faults, "csv"
        positions = {name: header.index(name) for name in mapped}
        entity_col = str(mapping["entity_id"])
        source_col = str(mapping["source_record_ids"])
        pred_col = str(mapping["prediction"])
        outcome_col = str(mapping["outcome"])
        split_col = str(mapping["split"])
        sources: set[str] = set()
        entity_outcomes: dict[str, str] = {}
        row_count = 0
        for row in reader:
            row_count += 1
            # This is not a hidden size rule: a valid table must map exactly
            # to the finite environment-owned records, so additional rows can
            # never satisfy the existing scientific invariant.
            if (
                maximum_scientifically_possible_rows is not None
                and row_count > maximum_scientifically_possible_rows
            ):
                faults.append("unexpected_row_count")
                break
            if len(row) != len(header):
                faults.append("ragged_csv_row")
                continue
            entity = row[positions[entity_col]].strip()
            source_parts = [
                item.strip()
                for item in row[positions[source_col]].replace(",", "|").split("|")
                if item.strip()
            ]
            split = row[positions[split_col]].strip()
            if not entity or not source_parts or not split:
                faults.append("blank_required_identifier")
            if any(source in sources for source in source_parts):
                faults.append("duplicate_source_record")
            sources.update(source_parts)
            outcome = row[positions[outcome_col]].strip()
            if outcome not in {"0", "1"}:
                faults.append("invalid_binary_outcome")
            prior = entity_outcomes.get(entity)
            if entity and prior is not None and prior != outcome:
                faults.append("entity_outcome_conflict")
            if entity:
                entity_outcomes[entity] = outcome
            try:
                prediction = float(row[positions[pred_col]])
            except (TypeError, ValueError, OverflowError):
                faults.append("prediction_not_numeric")
            else:
                if not math.isfinite(prediction):
                    faults.append("prediction_not_finite")
        if row_count == 0:
            faults.append("analysis_table_empty")
        return list(dict.fromkeys(faults)), "csv"
    except UnicodeDecodeError:
        return ["invalid_utf8"], "bytes"
    except (csv.Error, MemoryError, RecursionError):
        return ["malformed_csv"], "csv"
    finally:
        handle.close()


def validate_analysis_table_artifact(
    workspace: Path,
    artifact_id: str,
    artifact: tuple[dict[str, Any], Path],
    resource_id: str,
    *,
    linked_calculation_ids: tuple[str, ...] = (),
) -> tuple[ArtifactValidationResult, VerifiedTable | None]:
    manifest, path = artifact
    maximum_rows: int | None = None
    expected_pair: tuple[dict[str, dict[str, Any]], str] | None = None
    try:
        expected_pair = _expected_records(
            workspace,
            tuple(str(item) for item in manifest.get("source_paths") or []),
            resource_id,
        )
        if expected_pair is not None:
            records, _ = expected_pair
            if manifest.get("analysis_structure") == "ENTITY_AGGREGATED":
                maximum_rows = len({str(row["entity_id"]) for row in records.values()})
            else:
                maximum_rows = len(records)
    except (KeyError, OSError, TypeError, UnicodeError, ValueError, OverflowError):
        pass
    if expected_pair is None:
        # No table can satisfy the existing source-provenance invariant when
        # its declared sources do not resolve to a supported evidence set.
        maximum_rows = 0
    faults, observed = _csv_shape_faults(
        path,
        manifest.get("column_map"),
        maximum_scientifically_possible_rows=maximum_rows,
    )
    table: VerifiedTable | None = None
    if manifest.get("role") != "ANALYSIS_TABLE":
        faults.append("artifact_role_mismatch")
    if not faults:
        try:
            table = verify_analysis_table(workspace, artifact_id, manifest, path, resource_id)
        except (csv.Error, KeyError, OSError, TypeError, UnicodeError, ValueError, OverflowError):
            table = None
        if table is None:
            faults.append("scientific_table_invariant_mismatch")
    result = ArtifactValidationResult(
        valid=table is not None and not faults,
        artifact_id=artifact_id,
        artifact_path=str(manifest.get("path") or path.name),
        expected_artifact_role="ANALYSIS_TABLE",
        observed_top_level_type=observed,
        fault_codes=_dedupe(faults),
        linked_calculation_ids=linked_calculation_ids,
        origin="agent_controlled",
    )
    return result, table


def verify_typed_calculations_total(
    final: dict[str, Any],
    artifacts: dict[str, tuple[dict[str, Any], Path]],
    tables: dict[str, VerifiedTable],
) -> tuple[dict[str, CalculationResult], list[ArtifactValidationResult]]:
    """Preserve the frozen calculation semantics with total artifact parsing."""

    results: dict[str, CalculationResult] = {}
    validations: list[ArtifactValidationResult] = []
    for calculation in final.get("calculations") or []:
        calculation_id = str(calculation.get("calculation_id") or "")
        metric = str(calculation.get("metric") or "")
        estimator = str(calculation.get("estimator") or "")
        role = str(calculation.get("role") or "")
        table_id = str(calculation.get("source_analysis_table_id") or "")
        faults: list[str] = []
        table = tables.get(table_id)
        try:
            raw_reported = calculation["reported_value"]
            if isinstance(raw_reported, bool):
                raise TypeError
            reported = float(raw_reported)
            if not math.isfinite(reported):
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            reported = None
            faults.append("reported_value_invalid")
        if table is None:
            faults.append("source_table_not_verified")
        from uc_bench.mmmvp_open_calculations import (
            CALCULATION_ROLES,
            ESTIMATORS,
            METRICS,
            UNCERTAINTY_METHODS,
        )

        if metric not in METRICS:
            faults.append("metric_unknown")
        if estimator not in ESTIMATORS:
            faults.append("estimator_unknown")
        if role not in CALCULATION_ROLES:
            faults.append("role_unknown")
        if table is not None:
            if calculation.get("unit_of_analysis") not in {
                "BIOLOGICAL_ENTITY",
                "SOURCE_RECORD_CLUSTERED",
            }:
                faults.append("unit_invalid")
            if table.structure == "ENTITY_AGGREGATED" and estimator != "EMPIRICAL":
                faults.append("estimator_structure_mismatch")
            if table.structure == "SOURCE_RECORD_CLUSTERED" and estimator == "EMPIRICAL":
                faults.append("dependence_ignored")
            if calculation.get("outcome_column") != table.outcome_column:
                faults.append("outcome_column_mismatch")
            if calculation.get("prediction_column") != table.prediction_column:
                faults.append("prediction_column_mismatch")
            declared_context = tuple(calculation.get("context_columns") or [])
            if declared_context != table.context_columns:
                faults.append("context_columns_mismatch")
            if calculation.get("evidence_source") != table.evidence_source:
                faults.append("evidence_source_mismatch")
        cohort = calculation.get("cohort") or {}
        split_values = {str(item).upper() for item in cohort.get("split_values") or []}
        entity_ids = {str(item) for item in cohort.get("entity_ids") or []}
        rows = [] if table is None else [row for row in table.rows if row.split in split_values]
        if entity_ids:
            rows = [row for row in rows if row.entity_id in entity_ids]
        included = cohort.get("included_row_count")
        if (
            not split_values
            or not rows
            or isinstance(included, bool)
            or not isinstance(included, int)
            or included != len(rows)
        ):
            faults.append("cohort_mismatch")
        parameters = calculation.get("parameters") or {}
        recomputed: float | None = None
        if not faults:
            try:
                recomputed = calculate_metric(rows, metric, estimator, parameters)
                if not math.isfinite(recomputed):
                    raise ValueError
            except (ArithmeticError, TypeError, ValueError, OverflowError):
                faults.append("recomputation_failed")
        tolerance = _VALUE_TOLERANCE.get(metric)
        if (
            reported is None
            or recomputed is None
            or tolerance is None
            or not math.isclose(reported, recomputed, abs_tol=tolerance)
        ):
            faults.append("reported_value_mismatch")
        output_id = str(calculation.get("output_artifact_id") or "")
        output_validation = validate_calculation_output(
            artifacts.get(output_id), calculation_id, reported if reported is not None else math.nan
        )
        validations.append(output_validation)
        if not output_validation.valid:
            faults.append("saved_output_mismatch")
        uncertainty = calculation.get("uncertainty")
        uncertainty_valid = uncertainty is None
        if uncertainty is not None:
            uncertainty_valid = False
            try:
                if not isinstance(uncertainty, dict):
                    raise TypeError
                if metric != "ROC_AUC" or uncertainty.get("method") not in UNCERTAINTY_METHODS:
                    raise ValueError
                expected_low, expected_high = _cluster_bootstrap_interval(
                    rows, estimator, parameters, uncertainty
                )
                lower = uncertainty["lower"]
                upper = uncertainty["upper"]
                if isinstance(lower, bool) or isinstance(upper, bool):
                    raise TypeError
                uncertainty_valid = math.isclose(
                    float(lower), expected_low, abs_tol=0.02
                ) and math.isclose(float(upper), expected_high, abs_tol=0.02)
            except (ArithmeticError, KeyError, TypeError, ValueError, OverflowError):
                uncertainty_valid = False
            if not uncertainty_valid:
                faults.append("uncertainty_mismatch")
        results[calculation_id] = CalculationResult(
            calculation_id=calculation_id,
            valid=not faults,
            metric=metric,
            estimator=estimator,
            role=role,
            table_id=table_id,
            reported_value=reported,
            recomputed_value=recomputed,
            value_tolerance=tolerance,
            uncertainty_claimed=uncertainty is not None,
            uncertainty_valid=uncertainty_valid,
            faults=_dedupe(faults),
        )
    return results, validations


__all__ = [
    "ArtifactValidationResult",
    "validate_analysis_table_artifact",
    "validate_calculation_output",
    "verify_typed_calculations_total",
]
