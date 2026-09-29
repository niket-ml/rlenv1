"""One process-wide lock for RC5's inherited-module extension contexts."""

from __future__ import annotations

from threading import RLock

INHERITED_EXTENSION_LOCK = RLock()

__all__ = ["INHERITED_EXTENSION_LOCK"]
