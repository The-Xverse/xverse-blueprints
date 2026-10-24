"""WP-14a typed role/binding records; no role policy or offline plan is loaded.

XDL URNs name interfaces; ``schema`` names the actual wire record. EndpointBinding
comes from the admitted unit projection. Its expected producer is distinct from
both the received endpoint identity and the record's self-reported source.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any

from . import adas_contract as AC

STATES = ("NOMINAL", "DEGRADED", "UNCERTAIN", "UNSAFE")
CONFIGURATIONS = ("C_NOMINAL", "C_DEGRADED_RADAR", "S_MRC_REQUESTED")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
PROVENANCE = frozenset({"modelDigest", "preprocessParamsSha256", "postprocessSha256"})
BASE = {"schema": "text", "source": "text", "sequence": "uint", "originNs": "uint"}

# Closed typed bodies. Semantic admissibility, freshness, single use and objective
# vocabulary checks belong to later role implementations; no policy default here.
BODIES = {
    "proposal": {"proposalId": "text", "target": "text", "fromConfiguration": "configuration", "basisRefs": "refs", "validUntilNs": "uint"},
    "objective": {"objectiveId": "text", "objective": "text", "validUntilNs": "uint"},
    "goal-model": {"goalId": "text", "objectiveId": "text", "constraints": "object", "basisRefs": "refs"},
    "qualified-evidence": {"evidenceId": "text", "configuration": "configuration", "state": "state", "items": "evidence-items"},
    "vehicle-state-record": {"speedMps": "nullable-number", "accelerationMps2": "nullable-number", "state": "state", "evidenceRefs": "refs"},
    "diagnostic-verdict": {"diagnosticId": "text", "state": "state", "reasons": "refs", "evidenceRefs": "refs"},
    "assessment": {"assessmentId": "text", "configuration": "configuration", "state": "state", "admissible": "bool", "evidenceRefs": "refs", "deadlineMarginNs": "nullable-int", "recurrence": "uint"},
    "authorization": {"authorizationId": "text", "proposalId": "text", "fromConfiguration": "configuration", "toConfiguration": "configuration", "assessmentRef": "text", "issuedAtNs": "uint", "validUntilNs": "uint", "gateSequence": "uint"},
    "gate-state": {"gateSequence": "uint", "state": "gate-state", "monitorAssessmentAgeNs": "nullable-uint"},
    "forced-command": {"commandId": "text", "class": "command-class", "target": "configuration", "trigger": "refs"},
    "transition-request": {"transitionId": "text", "phase": "transition-phase", "outcome": "nullable-text", "evidenceRefs": "refs", "deadlineId": "text"},
    "transition-verdict": {"transitionId": "text", "phase": "transition-phase", "outcome": "text", "evidenceRefs": "refs", "deadlineId": "text"},
    "configuration-state": {"configuration": "configuration", "transitionId": "nullable-text", "phase": "text", "committedAtNs": "uint"},
    "selector-command": {"configuration": "configuration"},  # exact WP-13 five-member record
    "aeb-status": {"status": "availability", "reason": "text", "requestId": "nullable-text"},
    "mrc-request": {"requestId": "text", "reason": "text", "evidenceRefs": "refs"},
}
SOURCES = {
    "proposal": "proposer", "objective": "objective-source", "goal-model": "goal-interpreter",
    "qualified-evidence": "evidence-validator", "vehicle-state-record": "vehicle-state", "diagnostic-verdict": "diagnostics-supervision",
    "assessment": "safety-monitor", "authorization": "safety-gate", "gate-state": "safety-gate",
    "forced-command": "fixed-fallback-supervisor", "transition-request": "configuration-manager",
    "transition-verdict": "transition-verifier", "configuration-state": "configuration-manager",
    "selector-command": "configuration-manager", "aeb-status": "fixed-fallback-supervisor",
    "mrc-request": "fixed-fallback-supervisor",
}
# Only role/command interface pairs, not a deployment graph or an arm table.
CONSUMERS = {
    "proposal": ("safety-gate", "configuration-manager"), "objective": ("goal-interpreter",),
    "goal-model": ("proposer",), "qualified-evidence": ("functional-arbiter", "radar-fallback", "diagnostics-supervision", "fixed-fallback-supervisor", "safety-monitor"),
    "vehicle-state-record": ("evidence-validator",),
    "diagnostic-verdict": ("fixed-fallback-supervisor",), "assessment": ("safety-gate",),
    "authorization": ("configuration-manager",), "gate-state": ("configuration-manager",),
    "forced-command": ("configuration-manager",), "transition-request": ("transition-verifier",),
    "transition-verdict": ("configuration-manager", "safety-monitor"),
    "configuration-state": ("fixed-fallback-supervisor", "safety-monitor", "proposer"),
    "selector-command": ("functional-arbiter",), "aeb-status": ("functional-arbiter", "chassis-zone"),
    "mrc-request": ("mrc-sink",),
}
# Existing owner vocabularies are kept verbatim; these aliases do not add fields.
LEGACY_SCHEMAS = {
    "camera-sensor-out": "assured-aeb.camera-sensor-out/1",
    "smart-camera-evidence": "assured-aeb.camera-selfcheck/1", "smart-radar-evidence": "assured-aeb.radar-selfcheck/1",
    "camera-evidence": "assured-aeb.camera-evidence/1", "radar-evidence": "assured-aeb.radar-evidence/1",
    "motion-evidence": "assured-aeb.motion-evidence/1", "perception-output": "assured-aeb.perception-output/1",
    "proposal-basis": AC.SCHEMA, "adas-cycle": AC.SCHEMA, "fallback-request": "assured-aeb.fallback-request/1",
    "brake-request": "assured-aeb.brake-request/1", "brake-command": "assured-aeb.brake-command/1", "brake-status": "assured-aeb.brake-status/1",
}
HISTORICAL_WIRE_SCHEMAS = {"adas-cycle": AC.HISTORICAL_SCHEMA, "proposal-basis": AC.HISTORICAL_SCHEMA}
WIRE_SCHEMAS = {name: "assured-aeb." + name + "/1" for name in BODIES} | LEGACY_SCHEMAS
def interface_urn(interface):
    return AC.interface_urn(interface) if interface in AC.INTERFACES else "urn:xverse:assured-aeb:" + interface + ":v1"


HISTORICAL_URN_TO_SCHEMAS = {"urn:xverse:assured-aeb:" + name + ":v1": (schema,)
                             for name, schema in HISTORICAL_WIRE_SCHEMAS.items()}
URN_TO_SCHEMAS = {interface_urn(name): (schema,) for name, schema in WIRE_SCHEMAS.items() if name != "gate-state"}
URN_TO_SCHEMAS["urn:xverse:assured-aeb:authorization:v1"] = (WIRE_SCHEMAS["authorization"], WIRE_SCHEMAS["gate-state"])
EVIDENCE_ITEM = {"id": "text", "source": "text", "originNs": "uint", "receptionNs": "uint", "ageNs": "int", "validityWindowId": "text", "synchronizationQuality": "text", "integrity": "text", "modelConfidence": "nullable-number", "monitorConfidence": "nullable-number", "state": "state", "provenance": "digests", "payloadSha256": "digest"}


class ContractError(ValueError):
    """A typed record or projected endpoint binding was refused."""


def canonical(value: Any) -> bytes:
    """Finite JSON only; malformed/cyclic/deep values produce a contract error."""
    stack, seen = [value], set()
    while stack:
        item = stack.pop()
        if type(item) in (int, float):
            try:
                finite = math.isfinite(item)
            except OverflowError:
                finite = False
            if not finite:
                raise ContractError("non-finite or unrepresentable number")
        elif isinstance(item, (dict, list)):
            if id(item) in seen:
                continue
            seen.add(id(item))
            if isinstance(item, dict):
                if not all(isinstance(k, str) for k in item):
                    raise ContractError("JSON object keys must be strings")
                stack.extend(item.values())
            else:
                stack.extend(item)
        elif item is not None and type(item) not in (str, bool):
            raise ContractError("non-JSON value")
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError) as error:
        raise ContractError("record is not finite bounded JSON") from error


def _matches(kind: str, value: Any) -> bool:
    if kind.startswith("nullable-"):
        return value is None or _matches(kind[9:], value)
    if kind == "text":
        return isinstance(value, str) and bool(value)
    if kind == "bool":
        return type(value) is bool
    if kind in ("int", "uint"):
        return type(value) is int and (kind == "int" or value >= 0)
    if kind == "number":
        return type(value) in (int, float)  # canonical already enforces finite representation
    if kind == "digest":
        return isinstance(value, str) and DIGEST.fullmatch(value) is not None
    if kind == "refs":
        return isinstance(value, list) and all(_matches("text", item) for item in value)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "digests":
        return isinstance(value, dict) and all(_matches("text", k) and _matches("digest", v) for k, v in value.items())
    if kind == "evidence-items":
        return isinstance(value, list) and all(_shape(item, EVIDENCE_ITEM) for item in value)
    choices = {"state": STATES, "configuration": CONFIGURATIONS, "gate-state": ("open", "closed"), "command-class": ("degradation", "terminal", "comparator-recovery"), "transition-phase": ("pre", "during", "post"), "availability": ("available", "degraded", "unavailable")}
    return value in choices[kind] if kind in choices else False


def _shape(record: Any, fields: dict[str, str]) -> bool:
    return isinstance(record, dict) and set(record) == set(fields) and all(_matches(kind, record[name]) for name, kind in fields.items())


def validate_record(interface: str, record: Any) -> dict[str, Any]:
    """Validate one new role record; return a detached canonical copy."""
    if interface not in BODIES:
        raise ContractError("interface is owned by its existing productive validator")
    raw = canonical(record)
    fields = BASE | BODIES[interface]
    if not _shape(record, fields) or record["schema"] != WIRE_SCHEMAS[interface] or record["source"] != SOURCES[interface]:
        raise ContractError("wrong schema/source, members or field types for " + interface)
    return json.loads(raw)


def make_record(interface: str, *, source: str, sequence: int, origin_ns: int, **body: Any) -> dict[str, Any]:
    return validate_record(interface, dict(schema=WIRE_SCHEMAS[interface], source=source, sequence=sequence, originNs=origin_ns, **body))


@dataclass(frozen=True)
class EndpointBinding:
    """One admitted projected endpoint pair, never inferred from payload source."""
    interface: str
    producer: str
    consumer: str

    def __post_init__(self):
        if not all(isinstance(value, str) and value for value in (self.interface, self.producer, self.consumer)) or interface_urn(self.interface) not in URN_TO_SCHEMAS:
            raise ContractError("a known interface and explicit endpoint identities are required")

    @classmethod
    def from_record(cls, record):
        if not isinstance(record, dict) or set(record) != {"interface", "producer", "consumer"}:
            raise ContractError("projected endpoint binding must contain exactly interface, producer and consumer")
        return cls(**record)

    def consume(self, record: Any, *, received_producer: str) -> dict[str, Any]:
        if received_producer != self.producer:
            raise ContractError("received producer differs from projected expected producer")
        interface = "gate-state" if self.interface == "authorization" and isinstance(record, dict) and record.get("schema") == WIRE_SCHEMAS["gate-state"] else self.interface
        if interface in BODIES:
            if self.producer != SOURCES[interface] or self.consumer not in CONSUMERS[interface]:
                raise ContractError("producer/consumer pair is outside the role contract")
            return validate_record(interface, record)
        return _legacy(self, record)


def _legacy(binding: EndpointBinding, record: Any) -> dict[str, Any]:
    """Preserve existing productive bytes and owner validation; no role envelope."""
    raw = canonical(record)
    interface = binding.interface
    if interface not in LEGACY_SCHEMAS or not isinstance(record, dict) or record.get("schema") != LEGACY_SCHEMAS[interface]:
        raise ContractError("unknown productive schema")
    if interface in ("adas-cycle", "proposal-basis"):
        allowed = {("proposal-basis", "fusion-risk-aeb", "proposer"),
                   ("adas-cycle", "fusion-risk-aeb", "vc-ingress"),
                   ("adas-cycle", "vc-ingress", "functional-arbiter"),
                   ("adas-cycle", "vc-ingress", "evidence-validator")}
        if (interface, binding.producer, binding.consumer) not in allowed:
            raise ContractError("undeclared productive F11 endpoint pair")
        try:
            return AC.validate(record)
        except ValueError as error:
            raise ContractError("invalid active F11 /2 owner vocabulary") from error
    if interface in ("brake-request", "brake-command", "brake-status"):
        from . import brake_esc as B
        if interface == "brake-request":
            routed = binding.producer == B.CHASSIS and binding.consumer == B.NODE
            direct = binding.producer == B.ARBITER and binding.consumer == B.CHASSIS
            members = B.ROUTED_REQUEST_MEMBERS if routed else B.ARBITER_REQUEST_MEMBERS
            payload_source = B.CHASSIS if routed else B.ARBITER
            if not (direct or routed) or set(record) != members or record.get("source") != payload_source:
                raise ContractError("brake request violates the existing command chain")
            if routed and record.get("route") != B.ROUTE:
                raise ContractError("wrong chassis route")
            if type(record["sequence"]) is not int or type(record["originNs"]) is not int or type(record["value"]) not in (int, float) or not 0 <= record["value"] <= 1 or (routed and type(record["receivedNs"]) is not int):
                raise ContractError("malformed brake request")
        else:
            consumer = "loop-gateway" if interface == "brake-command" else B.CHASSIS
            if B.check_vocabulary(record) or record.get("node") != B.NODE or binding.producer != B.NODE or binding.consumer != consumer:
                raise ContractError("invalid brake node vocabulary/source/consumer")
            if interface == "brake-command" and (any(type(record[k]) is not int for k in ("sequence", "requestSequence", "requestOriginNs", "originNs")) or type(record["value"]) not in (int, float) or not 0 <= record["value"] <= 1):
                raise ContractError("malformed forwarded brake command")
            if interface == "brake-status" and (type(record["atNs"]) is not int or (record["requestSequence"] is not None and type(record["requestSequence"]) is not int)):
                raise ContractError("malformed brake software status")
    elif interface == "perception-output":
        members = {"schema", "source", "frame", "frameSha256", "originNs", "occupancyProbability", "binProbabilities", "predictedBin", "oodScore", "oodFlag", "inputQuality", "provenance", "state", "reason"}
        if binding.producer != "perception" or binding.consumer != "fusion-risk-aeb" or set(record) != members or record.get("source") != "perception" or not _shape(record.get("provenance"), {key: "digest" for key in PROVENANCE}):
            raise ContractError("perception vocabulary/provenance changed")
    else:
        # Other productive formats remain their owner's responsibility, and cannot
        # be used as a generic way to inject a new role/command interface.
        raise ContractError("productive interface requires its existing owner validator")
    return json.loads(raw)


def schema_document(interface: str) -> dict[str, Any]:
    """Machine-readable closed schema for the new role/binding record(s)."""
    if interface in ("adas-cycle", "proposal-basis"):
        return AC.schema_document(interface)
    def field(kind):
        if kind.startswith("nullable-"):
            return {"anyOf": [field(kind[9:]), {"type": "null"}]}
        if kind == "text": return {"type": "string", "minLength": 1}
        if kind == "bool": return {"type": "boolean"}
        if kind == "uint": return {"type": "integer", "minimum": 0}
        if kind == "int": return {"type": "integer"}
        if kind == "number": return {"type": "number"}
        if kind == "digest": return {"type": "string", "pattern": "^[0-9a-f]{64}$"}
        if kind == "refs": return {"type": "array", "items": field("text")}
        if kind == "object": return {"type": "object"}
        if kind == "digests": return {"type": "object", "propertyNames": field("text"), "additionalProperties": field("digest")}
        if kind == "evidence-items": return {"type": "array", "items": shape(EVIDENCE_ITEM)}
        return {"enum": list({"state": STATES, "configuration": CONFIGURATIONS, "gate-state": ("open", "closed"), "command-class": ("degradation", "terminal", "comparator-recovery"), "transition-phase": ("pre", "during", "post"), "availability": ("available", "degraded", "unavailable")}[kind])}
    def shape(fields):
        return {"type": "object", "additionalProperties": False, "required": sorted(fields), "properties": {name: field(kind) for name, kind in fields.items()}}
    def record(name):
        spec = shape(BASE | BODIES[name]);spec["properties"]["schema"] = {"const": WIRE_SCHEMAS[name]};spec["properties"]["source"] = {"const": SOURCES[name]};return spec
    names = ("authorization", "gate-state") if interface == "authorization" else (interface,)
    spec = record(names[0]) if len(names) == 1 else {"oneOf": [record(name) for name in names]}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:xverse:assured-aeb:"+interface+":v1", **spec}
