"""OFFLINE projection generator for a reviewed role table (WP-17b).

Runtime units import runtime_projection, never this full-record consumer. Actual
table membership/classification remains subject to the AD-27 freeze and provenance
review; names and categories are controls, not automatic semantic classification.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .protocol import Protocol
from .runtime_projection import (NAME, SCHEMA, ProjectionRefused, checked_hash,
                                 checked_identifiers, decode_object, verified_projection)

TABLE_SCHEMA = "assured-aeb.projection-table/1"
PINS_SCHEMA = "assured-aeb.projection-pins/1"
RESERVED_UNITS = frozenset({"projection-pins"})
FORBIDDEN_NAMESPACES = frozenset({"h2", "oracle", "scenario", "fault", "metrics", "metric"})
ALLOWED_CATEGORIES = frozenset({"runtime", "policy"})


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def build(protocol: Protocol, table_data: bytes, *, table_sha256: str,
          expected_roles: dict[str, str]) -> tuple[dict[str, bytes], dict]:
    if type(protocol) is not Protocol:
        raise ProjectionRefused("PROJECTION-PROTOCOL", "validated offline protocol access required")
    checked_hash(table_sha256)
    if not isinstance(table_data, bytes) or hashlib.sha256(table_data).hexdigest() != table_sha256:
        raise ProjectionRefused("PROJECTION-DIGEST", "table differs from reviewed pin")
    table = decode_object(table_data)
    if set(table) != {"schema", "protocolRecordSha256", "roles"} or table["schema"] != TABLE_SCHEMA:
        raise ProjectionRefused("PROJECTION-TABLE", "unknown table schema or extra members")
    if table["protocolRecordSha256"] != protocol.digest:
        raise ProjectionRefused("PROJECTION-DIGEST", "table belongs to another protocol")
    if (not isinstance(expected_roles, dict) or not all(
            isinstance(r, str) and NAME.fullmatch(r) and isinstance(u, str) and NAME.fullmatch(u)
            for r, u in expected_roles.items())):
        raise ProjectionRefused("PROJECTION-ROLES", "reviewed role-to-unit inventory required")
    if any(unit in RESERVED_UNITS for unit in expected_roles.values()):
        raise ProjectionRefused("PROJECTION-UNIT", "unit name is reserved for bundle metadata")
    roles = table["roles"]
    if not isinstance(roles, dict) or set(roles) != set(expected_roles):
        raise ProjectionRefused("PROJECTION-ROLES", "omitted or extra role")
    per_unit = {}
    for role, definition in roles.items():
        if not isinstance(definition, dict) or set(definition) != {"unit", "identifiers"}:
            raise ProjectionRefused("PROJECTION-ROLES", f"malformed role {role}")
        if definition["unit"] != expected_roles[role]:
            raise ProjectionRefused("PROJECTION-ROLES", f"role {role} moved from its declared unit")
        consumed = checked_identifiers(definition["identifiers"])
        values = per_unit.setdefault(expected_roles[role], {})
        for identifier in sorted(consumed):
            entry = protocol.entry(identifier)
            if (entry["category"] not in ALLOWED_CATEGORIES
                    or identifier.split(".", 1)[0] in FORBIDDEN_NAMESPACES):
                raise ProjectionRefused("PROJECTION-FORBIDDEN", identifier)
            values[identifier] = entry["value"]
    outputs = {}
    for unit, values in sorted(per_unit.items()):
        outputs[unit] = _canonical({"schema": SCHEMA, "protocolRecordSha256": protocol.digest,
                                    "unit": unit, "entries": values})
    receipt = {"schema": PINS_SCHEMA, "protocolRecordSha256": protocol.digest,
               "tableSha256": table_sha256,
               "units": {unit: {"sha256": hashlib.sha256(data).hexdigest(), "identifiers": sorted(per_unit[unit])}
                         for unit, data in outputs.items()}}
    return outputs, receipt


def write_bundle(directory: Path, outputs: dict[str, bytes], receipt: dict, *,
                 expected_table_sha256: str, protocol_record_sha256: str) -> None:
    """Write a fresh offline artifact directory; never overwrite a previous bundle.

    A failed write leaves an unaccepted partial artifact for diagnosis. The receipt
    is written last and does not grant run authorization or replace file verification.
    The two expected pins are admitted inputs, independent of this mutable receipt.
    """
    directory = Path(directory)
    checked_hash(expected_table_sha256)
    checked_hash(protocol_record_sha256)
    if not isinstance(outputs, dict):
        raise ProjectionRefused("PROJECTION-RECEIPT", "output byte mapping required")
    payloads = dict(outputs)
    try:
        receipt_data = _canonical(receipt)
        pins = decode_object(receipt_data)
    except (TypeError, ValueError, RecursionError) as error:
        if isinstance(error, ProjectionRefused):
            raise
        raise ProjectionRefused("PROJECTION-RECEIPT", "receipt must be finite JSON") from error
    if (set(pins) != {"schema", "protocolRecordSha256", "tableSha256", "units"}
            or pins["schema"] != PINS_SCHEMA or not isinstance(pins["units"], dict)):
        raise ProjectionRefused("PROJECTION-RECEIPT", "closed projection-pins receipt required")
    if (checked_hash(pins["tableSha256"]) != expected_table_sha256
            or checked_hash(pins["protocolRecordSha256"]) != protocol_record_sha256):
        raise ProjectionRefused("PROJECTION-DIGEST", "receipt differs from admitted table/protocol pins")
    for unit in payloads:
        if not isinstance(unit, str) or NAME.fullmatch(unit) is None or unit in RESERVED_UNITS:
            raise ProjectionRefused("PROJECTION-UNIT", "unsafe output unit id")
    if set(payloads) != set(pins["units"]):
        raise ProjectionRefused("PROJECTION-DIGEST", "output inventory differs from receipt")
    for unit, data in payloads.items():
        entry = pins["units"][unit]
        if (not isinstance(entry, dict) or set(entry) != {"sha256", "identifiers"}
                or not isinstance(entry["identifiers"], list)):
            raise ProjectionRefused("PROJECTION-RECEIPT", "closed unit hash/identifier entry required")
        checked_identifiers(entry["identifiers"])
        verified_projection(data, expected_sha256=entry["sha256"], expected_unit=unit,
                            protocol_record_sha256=protocol_record_sha256, identifiers=entry["identifiers"])
    directory.mkdir(exist_ok=False)
    for unit, data in payloads.items():
        with (directory / f"{unit}.json").open("xb") as stream:
            stream.write(data)
    with (directory / "projection-pins.json").open("xb") as stream:
        stream.write(receipt_data)
