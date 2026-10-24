"""Shared helpers for the AD-36 check classes and the parameter records (WP-07; review-wp07 finding 1)."""

from __future__ import annotations

import math
import re
from typing import Any

IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
CLASSES = ("logical", "plausibility", "statistical")


def is_int(value: Any) -> bool:
    return type(value) is int


def is_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def exact(record: Any, schema: str, members: set[str] | frozenset[str]) -> dict[str, Any]:
    """Refuse a record that is not exactly ``members`` with ``schema`` (no defaults)."""

    if not isinstance(record, dict) or set(record) != set(members):
        raise ValueError(f"{schema} members must be exactly {sorted(members)}; got "
                         f"{sorted(record) if isinstance(record, dict) else type(record).__name__}")
    if record["schema"] != schema:
        raise ValueError(f"schema must be {schema}")
    return record


def verdict(failed: list[str], evaluated: bool = True) -> dict[str, Any]:
    if not evaluated:
        return {"verdict": "not-evaluated", "failed": []}
    return {"verdict": "fail" if failed else "pass", "failed": sorted(failed)}


def sequence_status(last: int | None, sequence: int) -> tuple[str, int]:
    """``(status, gap)`` of a consecutive per-flow sequence: ``ok``, ``gap`` (``gap`` items missing), ``duplicate`` or
    ``regressed``; the first item is ``ok``."""

    if last is None or sequence == last + 1:
        return "ok", 0
    if sequence == last:
        return "duplicate", 0
    if sequence < last:
        return "regressed", 0
    return "gap", sequence - last - 1
