"""Offline, digest-bound protocol access (WP-17a; no runtime-unit import).

Pins are trusted external approval records under WP-17 DN-1. Checking a digest and
decision reference does not authenticate an author or establish a cryptographic
signature. Characterisation access never admits principal evidence or a live run.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

RECORD_SCHEMA = "assured-aeb.protocol-record/1"
PIN_SCHEMA = "assured-aeb.protocol-pin/1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[a-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9_]*)+\Z")
CATEGORIES = ("runtime", "oracle", "scenario", "fault", "metric", "policy")
H2_IDENTIFIERS = (
    "h2.safetyMetric", "h2.nonInferiorityMargin", "h2.minimumBenefit",
    "h2.seeds", "h2.invalidRunRule", "h2.statisticalMethod",
)
RUNTIME_LIMIT = "runtime.pathLimit"
_ADMITTED = object()


class ProtocolRefused(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")


def _refuse(code: str, detail: str) -> None:
    raise ProtocolRefused(code, detail)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _members(value: Any, names: set[str], code: str) -> dict:
    if not isinstance(value, dict) or set(value) != names:
        _refuse(code, f"members must be exactly {sorted(names)}")
    return value


def _hash(value: Any, code: str) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        _refuse(code, "expected a lowercase SHA-256")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _refuse("PROTOCOL-JSON", f"duplicate member {key!r}")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    _refuse("PROTOCOL-JSON", f"non-finite JSON value {value}")


def _finite_tree(value: Any) -> None:
    if type(value) is float and not math.isfinite(value):
        _refuse("PROTOCOL-JSON", "non-finite JSON number")
    if isinstance(value, dict):
        for child in value.values():
            _finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            _finite_tree(child)


def _json(data: bytes, code: str) -> dict:
    if not isinstance(data, bytes) or not data:
        _refuse(code, "non-empty original JSON bytes are required")
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_nonfinite)
        _finite_tree(value)
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, ProtocolRefused):
            raise
        _refuse("PROTOCOL-JSON", str(error))
    if not isinstance(value, dict):
        _refuse("PROTOCOL-JSON", "top-level object required")
    return value


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str):
        _refuse(code, "explicit UTC timestamp required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _refuse(code, "invalid UTC timestamp")
    if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
        _refuse(code, "timestamp must have an explicit UTC offset")
    return result


def _approval(value: Any) -> datetime:
    _members(value, {"reference", "acceptedAt"}, "PROTOCOL-UNSIGNED")
    if not _text(value["reference"]):
        _refuse("PROTOCOL-UNSIGNED", "approval decision reference is missing")
    return _time(value["acceptedAt"], "PROTOCOL-CHRONOLOGY")


def _placeholder(value: Any) -> bool:
    if isinstance(value, str):
        word = value.strip().upper()
        return word.startswith(("TODO", "NEEDS DATA", "PENDING"))
    if isinstance(value, dict):
        return any(_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(_placeholder(v) for v in value)
    return False


def _record(data: bytes, digest: str) -> dict:
    _hash(digest, "PROTOCOL-DIGEST")
    if not isinstance(data, bytes) or not data:
        _refuse("PROTOCOL-ABSENT", "protocol record is absent")
    if hashlib.sha256(data).hexdigest() != digest:
        _refuse("PROTOCOL-DIGEST", "record differs from the supplied pin")
    record = _json(data, "PROTOCOL-ABSENT")
    _members(record, {"schema", "recordId", "declaredAt", "entries"}, "PROTOCOL-RECORD")
    if record["schema"] != RECORD_SCHEMA or not _text(record["recordId"]):
        _refuse("PROTOCOL-RECORD", "unknown schema or empty record id")
    _time(record["declaredAt"], "PROTOCOL-CHRONOLOGY")
    if not isinstance(record["entries"], dict):
        _refuse("PROTOCOL-RECORD", "entries must be an identifier map")
    for identifier, entry in record["entries"].items():
        if IDENTIFIER.fullmatch(identifier) is None:
            _refuse("PROTOCOL-RECORD", f"invalid identifier {identifier!r}")
        _members(entry, {"value", "unit", "source", "status", "category"}, "PROTOCOL-ENTRY")
        if (not _text(entry["unit"]) or entry["status"] not in ("final", "provisional", "unresolved")
                or entry["category"] not in CATEGORIES):
            _refuse("PROTOCOL-ENTRY", f"invalid entry metadata: {identifier}")
        source = _members(entry["source"], {"kind", "reference"}, "PROTOCOL-ENTRY")
        if source["kind"] not in ("decision", "measurement", "policy") or not _text(source["reference"]):
            _refuse("PROTOCOL-ENTRY", f"invalid source: {identifier}")
    return record


def _h2(entries: dict) -> None:
    for identifier in H2_IDENTIFIERS:
        if identifier not in entries:
            _refuse("PROTOCOL-H2-MISSING", identifier)
        entry = entries[identifier]
        value = entry["value"]
        if entry["status"] != "final" or _placeholder(value) or value is None:
            _refuse("PROTOCOL-H2-UNRESOLVED", identifier)
        if identifier in ("h2.safetyMetric", "h2.invalidRunRule", "h2.statisticalMethod"):
            valid = _text(value)
        elif identifier == "h2.seeds":
            valid = (isinstance(value, list) and bool(value) and all(type(v) is int for v in value)
                     and len(set(value)) == len(value))
        else:
            try:
                valid = type(value) in (int, float) and math.isfinite(float(value))
            except OverflowError:
                valid = False
        if not valid:
            _refuse("PROTOCOL-H2-UNRESOLVED", f"invalid value for {identifier}")


def policy_digest(entries: dict) -> str:
    """Digest the stable H2 policy subset, including its status and provenance."""
    _h2(entries)
    subset = {identifier: entries[identifier] for identifier in H2_IDENTIFIERS}
    return hashlib.sha256(json.dumps(subset, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _pre_pilot(entries: dict, pin: Any, first_pilot_at: str) -> None:
    _members(pin, {"sha256", "acceptance"}, "PROTOCOL-PILOT-POLICY")
    if _hash(pin["sha256"], "PROTOCOL-PILOT-POLICY") != policy_digest(entries):
        _refuse("PROTOCOL-PILOT-POLICY", "H2 policy changed after its acceptance")
    if _approval(pin["acceptance"]) > _time(first_pilot_at, "PROTOCOL-CHRONOLOGY"):
        _refuse("PROTOCOL-PILOT-POLICY", "H2 policy was accepted after pilot start")


class Protocol:
    """Offline identifier access after explicit principal or characterisation admission."""

    __slots__ = ("_record", "_digest", "_kind")

    def __init__(self, record: dict, digest: str, kind: str, *, _admission: object = None):
        if _admission is not _ADMITTED:
            _refuse("PROTOCOL-ADMISSION", "use principal() or characterisation()")
        self._record = copy.deepcopy(record)
        self._digest = digest
        self._kind = kind

    @property
    def digest(self) -> str:
        return self._digest

    @property
    def kind(self) -> str:
        return self._kind

    @classmethod
    def principal(cls, data: bytes, pin_data: bytes, *, started_at: str,
                  first_pilot_at: str | None) -> Protocol:
        pin = _json(pin_data, "PROTOCOL-PIN-ABSENT")
        _members(pin, {"schema", "recordSha256", "acceptance", "prePilotPolicy"}, "PROTOCOL-PIN")
        if pin["schema"] != PIN_SCHEMA:
            _refuse("PROTOCOL-PIN", "unknown pin schema")
        record = _record(data, pin["recordSha256"])
        start = _time(started_at, "PROTOCOL-CHRONOLOGY")
        declared = _time(record["declaredAt"], "PROTOCOL-CHRONOLOGY")
        accepted = _approval(pin["acceptance"])
        if declared > accepted or accepted > start:
            _refuse("PROTOCOL-CHRONOLOGY", "record must be declared, accepted, then used")
        entries = record["entries"]
        _h2(entries)
        for identifier, entry in entries.items():
            if entry["status"] != "final" or _placeholder(entry["value"]):
                _refuse("PROTOCOL-NONFINAL", identifier)
        if RUNTIME_LIMIT not in entries:
            _refuse("PROTOCOL-RUNTIME-LIMIT", "AD-21 runtime-path limit is missing")
        limit = entries[RUNTIME_LIMIT]["value"]
        if (not isinstance(limit, dict) or set(limit) != {"path", "m1Admitted", "limitation"}
                or limit["path"] != "lite" or limit["m1Admitted"] is not False or not _text(limit["limitation"])):
            _refuse("PROTOCOL-RUNTIME-LIMIT", "AD-21 requires a declared Lite non-M1 limit")
        if first_pilot_at is not None:
            if _time(first_pilot_at, "PROTOCOL-CHRONOLOGY") > start:
                _refuse("PROTOCOL-CHRONOLOGY", "first pilot follows principal start")
            _pre_pilot(entries, pin["prePilotPolicy"], first_pilot_at)
        elif pin["prePilotPolicy"] is not None:
            _refuse("PROTOCOL-PILOT-POLICY", "pilot approval supplied without pilot chronology")
        return cls(record, pin["recordSha256"], "principal", _admission=_ADMITTED)

    @classmethod
    def characterisation(cls, data: bytes, *, expected_digest: str, started_at: str,
                         pilot_policy: dict | None = None, is_pilot: bool = False) -> Protocol:
        record = _record(data, expected_digest)
        if _time(record["declaredAt"], "PROTOCOL-CHRONOLOGY") > _time(started_at, "PROTOCOL-CHRONOLOGY"):
            _refuse("PROTOCOL-CHRONOLOGY", "parameters were declared after run start")
        if type(is_pilot) is not bool:
            _refuse("PROTOCOL-PILOT-POLICY", "is_pilot must be boolean")
        if is_pilot:
            _pre_pilot(record["entries"], pilot_policy, started_at)
        elif pilot_policy is not None:
            _refuse("PROTOCOL-PILOT-POLICY", "pilot approval supplied for a non-pilot declaration")
        return cls(record, expected_digest, "characterisation", _admission=_ADMITTED)

    def value(self, identifier: str) -> Any:
        if identifier not in self._record["entries"]:
            _refuse("PROTOCOL-IDENTIFIER", f"missing identifier {identifier!r}; no default")
        entry = self._record["entries"][identifier]
        allowed = ("final",) if self.kind == "principal" else ("final", "provisional")
        if entry["status"] not in allowed or _placeholder(entry["value"]):
            _refuse("PROTOCOL-NONFINAL", identifier)
        return copy.deepcopy(entry["value"])

    def metadata(self) -> dict:
        result = {"runKind": self.kind, "protocolRecordSha256": self.digest,
                  "engineeringDataOnly": self.kind == "characterisation"}
        if self.kind == "principal":
            result["runtimePathLimit"] = self.value(RUNTIME_LIMIT)
        return result


def read_bytes(path: Path) -> bytes:
    """Read an explicitly supplied offline artifact; never resolve message-borne paths."""
    try:
        return Path(path).read_bytes()
    except OSError as error:
        _refuse("PROTOCOL-ABSENT", str(error))
