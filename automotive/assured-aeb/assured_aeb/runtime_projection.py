"""Runtime-side, own-unit projection checks; standard library only (FR-028).

This module must never import the complete protocol, table, experiment topology,
oracle or offline projection builder. Expected hashes/identifiers are admitted
launch inputs, not fields selected by a received runtime message.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any

SCHEMA = "assured-aeb.runtime-parameter-projection/1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[a-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9_]*)+\Z")
NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")


class ProjectionRefused(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProjectionRefused("PROJECTION-JSON", f"duplicate member {key!r}")
        result[key] = value
    return result


def _constant(value):
    raise ProjectionRefused("PROJECTION-JSON", f"non-finite JSON value {value}")


def _finite(value):
    if type(value) is float and not math.isfinite(value):
        raise ProjectionRefused("PROJECTION-JSON", "non-finite JSON number")
    if isinstance(value, dict):
        for child in value.values():
            _finite(child)
    elif isinstance(value, list):
        for child in value:
            _finite(child)


def decode_object(data: bytes) -> dict:
    if not isinstance(data, bytes) or not data:
        raise ProjectionRefused("PROJECTION-JSON", "original JSON bytes required")
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
        _finite(value)
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, ProjectionRefused):
            raise
        raise ProjectionRefused("PROJECTION-JSON", str(error)) from error
    if not isinstance(value, dict):
        raise ProjectionRefused("PROJECTION-JSON", "object required")
    return value


def checked_hash(value: Any) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise ProjectionRefused("PROJECTION-DIGEST", "lowercase SHA-256 required")
    return value


def checked_identifiers(values: Any) -> frozenset[str]:
    if not isinstance(values, (list, tuple, set, frozenset)) or not all(
            isinstance(v, str) and IDENTIFIER.fullmatch(v) for v in values):
        raise ProjectionRefused("PROJECTION-IDENTIFIERS", "dotted identifier collection required")
    if len(set(values)) != len(values):
        raise ProjectionRefused("PROJECTION-IDENTIFIERS", "duplicate consumed identifier")
    return frozenset(values)


def verified_projection(data: bytes, *, expected_sha256: str, expected_unit: str,
                        protocol_record_sha256: str, identifiers) -> dict:
    """Return a private closed projection for the existing typed parameter reader."""
    checked_hash(expected_sha256)
    checked_hash(protocol_record_sha256)
    consumed = checked_identifiers(identifiers)
    if not isinstance(expected_unit, str) or NAME.fullmatch(expected_unit) is None:
        raise ProjectionRefused("PROJECTION-UNIT", "explicit own unit id required")
    if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ProjectionRefused("PROJECTION-DIGEST", "projection differs from admitted bytes")
    record = decode_object(data)
    if set(record) != {"schema", "protocolRecordSha256", "unit", "entries"} or record["schema"] != SCHEMA:
        raise ProjectionRefused("PROJECTION-RECORD", "unknown schema or unexpected projection members")
    if record["protocolRecordSha256"] != protocol_record_sha256:
        raise ProjectionRefused("PROJECTION-DIGEST", "foreign protocol record")
    if record["unit"] != expected_unit:
        raise ProjectionRefused("PROJECTION-UNIT", "projection belongs to another unit")
    if not isinstance(record["entries"], dict) or set(record["entries"]) != consumed:
        raise ProjectionRefused("PROJECTION-IDENTIFIERS", "missing or foreign consumed parameters")
    return copy.deepcopy(record)
