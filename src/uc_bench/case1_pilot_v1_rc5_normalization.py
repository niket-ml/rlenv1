"""Shared non-secret normalization rules for the Case-1 RC5 contract."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


class NormalizationError(ValueError):
    """An agent-authored representation is ambiguous or invalid."""


def _sha256(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise NormalizationError("sha256 must be a 64-character lower-case hexadecimal string")
    return value


def normalize_source_hashes(value: Any) -> dict[str, str]:
    """Normalize both publicly accepted source-hash containers.

    Accepted forms are ``{path: sha256}`` and
    ``[{"path": path, "sha256": sha256}]``.  Duplicate paths are rejected in
    the list form even when their values agree: repetition is ambiguous and can
    otherwise hide a later conflicting entry.
    """

    pairs: list[tuple[Any, Any]]
    if isinstance(value, Mapping):
        pairs = list(value.items())
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        pairs = []
        for index, row in enumerate(value):
            if not isinstance(row, Mapping) or set(row) != {"path", "sha256"}:
                raise NormalizationError(
                    f"source_hashes[{index}] must contain exactly path and sha256"
                )
            pairs.append((row["path"], row["sha256"]))
    else:
        raise NormalizationError("source_hashes must be an object or a list of path/hash objects")

    result: dict[str, str] = {}
    for raw_path, raw_digest in pairs:
        if not isinstance(raw_path, str) or not raw_path:
            raise NormalizationError("source-hash paths must be nonempty strings")
        if raw_path in result:
            raise NormalizationError(f"duplicate source-hash path: {raw_path}")
        result[raw_path] = _sha256(raw_digest)
    return dict(sorted(result.items()))


def finite_number(value: Any, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NormalizationError("a finite numeric value is required")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise NormalizationError("numeric value is outside the disclosed finite range")
    return result


__all__ = ["NormalizationError", "finite_number", "normalize_source_hashes"]
