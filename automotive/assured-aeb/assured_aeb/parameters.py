"""FR-028 runtime-parameter projection: parameters read by identifier, with no default (WP-13 #1; review-wp13-logic
finding 1 §1.2).

The projection record is ``{schema, protocolRecordSha256, unit, entries: {identifier: value}}``. It is the proposed
form, to be fixed with the AD-27 freeze, which also fixes the identifiers. A role declares its identifiers with their
kinds and reads exactly those. ``check_exact`` refuses entries that none of the unit's roles consumes (FR-028: only what
the roles consume).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from .checks import is_number

PROJECTION = "assured-aeb.runtime-parameter-projection/1"
IDENTIFIER = re.compile(r"[a-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9_]*)+\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
#: Kinds a parameter can declare. Each is a validation of the projected value, never a default.
KINDS = ("positive-number", "non-negative-number", "probability", "unit-interval-open-low", "positive-int",
         "non-negative-int", "sign", "xy", "increasing-positive-list", "enum", "digest", "finite-number")


def _number(value: Any) -> bool:
    return is_number(value)


def _valid(kind: str, value: Any, choices: tuple[str, ...] | None) -> bool:
    if kind == "digest":
        return type(value) is str and HEX64.fullmatch(value) is not None
    if kind == "finite-number":
        return _number(value)
    if kind == "positive-number":
        return _number(value) and value > 0
    if kind == "non-negative-number":
        return _number(value) and value >= 0
    if kind == "probability":
        return _number(value) and 0 <= value <= 1
    if kind == "unit-interval-open-low":
        return _number(value) and 0 < value <= 1
    if kind == "positive-int":
        return type(value) is int and value > 0
    if kind == "non-negative-int":
        return type(value) is int and value >= 0
    if kind == "sign":
        return type(value) is int and value in (-1, 1)
    if kind == "xy":
        return isinstance(value, list) and len(value) == 2 and all(_number(v) for v in value)
    if kind == "increasing-positive-list":
        return isinstance(value, list) and bool(value) and all(_number(v) and v > 0 for v in value) \
            and all(b > a for a, b in zip(value, value[1:]))
    if kind == "enum":
        return isinstance(value, str) and value in (choices or ())
    raise ValueError(f"undeclared parameter kind {kind!r}")


class Projection:
    """A validated runtime-parameter projection for one unit."""

    def __init__(self, record: Any) -> None:
        if not isinstance(record, dict) or set(record) != {"schema", "protocolRecordSha256", "unit", "entries"}:
            raise ValueError(f"{PROJECTION} members must be exactly schema, protocolRecordSha256, unit, entries")
        if record["schema"] != PROJECTION:
            raise ValueError(f"schema must be {PROJECTION}")
        if not (isinstance(record["protocolRecordSha256"], str) and HEX64.match(record["protocolRecordSha256"])):
            raise ValueError("protocolRecordSha256 must be the SHA-256 of the signed protocol record")
        if not isinstance(record["unit"], str) or not record["unit"]:
            raise ValueError("unit must be a non-empty string")
        entries = record["entries"]
        if not isinstance(entries, dict) or not all(isinstance(k, str) and IDENTIFIER.match(k) for k in entries):
            raise ValueError("entries must map dotted identifiers to values")
        self.record = json.loads(json.dumps(record, allow_nan=False))  # a private copy; refuses NaN and infinities
        self.entries: dict[str, Any] = self.record["entries"]

    def take(self, declared: Mapping[str, tuple]) -> dict[str, Any]:
        """Read exactly the declared identifiers: ``{identifier: (kind,) | ("enum", choices)}``. No default."""

        values = {}
        for identifier, spec in declared.items():
            if identifier not in self.entries:
                raise ValueError(f"{identifier}: missing from the runtime-parameter projection (no default)")
            kind, choices = spec[0], (spec[1] if len(spec) > 1 else None)
            value = self.entries[identifier]
            if not _valid(kind, value, choices):
                raise ValueError(f"{identifier}: {value!r} is not a valid {kind}" + (f" {choices}" if choices else ""))
            values[identifier] = value
        return values

    def check_exact(self, consumed: Iterable[str]) -> None:
        """Refuse entries that no role of the unit consumes (FR-028)."""

        extra = sorted(set(self.entries) - set(consumed))
        if extra:
            raise ValueError(f"entries not consumed by this unit's roles: {extra}")


def params_digest(values: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical consumed entries (carried in every record of the role)."""

    return hashlib.sha256(json.dumps(dict(values), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
