"""ED-12 adapter for one already-open unit-owned accepted Argus run.

No plan, protocol, arm, fault or oracle is read. The entry point supplies its
admitted writer and local role allow-list. Only small binding/reference records
and digests enter the extension; productive payloads and pixel bytes do not.
"""
from __future__ import annotations

import hashlib
import json
from threading import Lock
from weakref import WeakKeyDictionary

from .role_contract import ContractError, DIGEST, CONFIGURATIONS, canonical

EXTENSION = "io.xverse.assured-aeb.role-events"
VERSION = 1
UNITS = ("vehicle-loop", "adas-hpc", "vc-functional", "vc-assurance")
BINDING_IDS = frozenset({"proposalId", "authorizationId", "assessmentRef", "commandId", "transitionId", "requestId", "goalId", "objectiveId", "preemptedTransitionId", "preemptingCommandId"})
KINDS = {
    "proposal-created": ({"proposer"}, {"proposalId"}),
    "proposal-received": ({"safety-gate", "configuration-manager"}, {"proposalId"}),
    "assessment": ({"safety-monitor"}, {"assessmentRef"}),
    "authorization": ({"safety-gate"}, {"authorizationId", "proposalId", "assessmentRef"}),
    "rejection": ({"safety-gate", "configuration-manager", "goal-interpreter"}, set()),
    "forced-command": ({"fixed-fallback-supervisor"}, {"commandId"}),
    "comparator-recovery-command": ({"fixed-fallback-supervisor"}, {"commandId"}),
    "selector-command": ({"configuration-manager"}, {"transitionId"}),
    "preemption": ({"configuration-manager"}, {"preemptedTransitionId", "preemptingCommandId"}),
    "transition-requested": ({"configuration-manager"}, {"transitionId"}),
    "transition-pre-verified": ({"transition-verifier"}, {"transitionId"}),
    "transition-committed": ({"configuration-manager"}, {"transitionId"}),
    "transition-post-verified": ({"transition-verifier"}, {"transitionId"}),
    "transition-rolled-back": ({"configuration-manager"}, {"transitionId"}),
    "transition-fallen-back": ({"configuration-manager"}, {"transitionId"}),
    "verification-outcome": ({"transition-verifier"}, {"transitionId"}),
    "forced-response": ({"fixed-fallback-supervisor"}, {"commandId"}),
    "mrc-request": ({"fixed-fallback-supervisor"}, {"requestId"}),
    "mrc-request-received": ({"mrc-sink"}, {"requestId"}),
    "gate-state": ({"safety-gate"}, set()),
    "monitor-failure-trigger": ({"fixed-fallback-supervisor"}, {"commandId"}),
    "actuator-acceptance": ({"brake-esc-node"}, set()),
    "arbiter-request": ({"functional-arbiter"}, set()),
}
_CLAIMS = WeakKeyDictionary()
_CLAIM_LOCK = Lock()


def payload_digest(record) -> str:
    """Digest a runtime message without placing its payload in role evidence."""
    return hashlib.sha256(canonical(record)).hexdigest()


def _text(value):
    return isinstance(value, str) and bool(value)


class RoleEvents:
    """One adapter per Argus writer, with local-only acknowledged causation."""
    def __init__(self, writer, *, unit: str, roles, clock_domain: str, maximum_record_bytes: int):
        if unit not in UNITS or not isinstance(roles, (list, tuple)) or not roles or not all(_text(role) for role in roles):
            raise ContractError("selected unit and explicit local role allow-list are required")
        if type(maximum_record_bytes) is not int or maximum_record_bytes <= 0:
            raise ContractError("an admitted positive engineering record-byte bound is required")
        if not callable(getattr(writer, "append_event", None)) or getattr(writer, "writer_state", None) != "open":
            raise ContractError("an open accepted Argus writer is required")
        if getattr(writer, "run_id", None) != "argus-roles-" + unit:
            raise ContractError("role evidence requires its separate argus-roles-<unit> run")
        if not _text(clock_domain) or clock_domain not in writer.declared_domains:
            raise ContractError("the simulator clock must be declared by the admitted Argus run")
        with _CLAIM_LOCK:
            if writer in _CLAIMS:
                raise ContractError("the role-event writer is already claimed")
            _CLAIMS[writer] = unit
        self.writer, self.unit, self.roles = writer, unit, frozenset(roles)
        self.clock_domain, self.maximum_record_bytes = clock_domain, maximum_record_bytes
        self.sequence, self.event_ids, self.poisoned = 0, [], False

    def emit(self, *, role, kind, bindings, sim_ns, step, configuration, outcome, reason,
             payload_sha256, source_refs, causation_id=None):
        if self.poisoned:
            raise ContractError("a failed role-event append cannot be retried")
        if not _text(role) or not _text(kind) or role not in self.roles or kind not in KINDS or role not in KINDS[kind][0]:
            raise ContractError("undeclared local role/event kind")
        if kind == "mrc-request-received" and self.unit != "vehicle-loop":
            raise ContractError("only U2 records the passive MRC receipt")
        if not isinstance(bindings, dict) or not set(bindings) <= BINDING_IDS or not KINDS[kind][1] <= set(bindings) or not all(_text(v) for v in bindings.values()):
            raise ContractError("missing, unknown or malformed binding ids")
        if any(type(v) is not int or v < 0 for v in (sim_ns, step)):
            raise ContractError("simulator origin and step must be non-negative integer values")
        if configuration is not None and configuration not in CONFIGURATIONS:
            raise ContractError("undeclared configuration")
        if not _text(outcome) or (reason is not None and not _text(reason)):
            raise ContractError("outcome/reason must be small typed text records")
        if not isinstance(payload_sha256, str) or DIGEST.fullmatch(payload_sha256) is None:
            raise ContractError("a payload digest, not the payload, is required")
        if not isinstance(source_refs, list) or not all(isinstance(ref, dict) and set(ref) == {"messageId", "sha256"} and _text(ref["messageId"]) and isinstance(ref["sha256"], str) and DIGEST.fullmatch(ref["sha256"]) for ref in source_refs):
            raise ContractError("source references contain only actual message ids and digests")
        if causation_id is not None and causation_id not in self.event_ids:
            raise ContractError("causation must name an acknowledged prior event in this run")
        cause = causation_id if causation_id is not None else (self.event_ids[-1] if self.event_ids else None)
        payload = dict(version=VERSION, role=role, unit=self.unit, kind=kind, bindings=dict(bindings),
                       simNs=sim_ns, step=step, configuration=configuration, outcome=outcome, reason=reason,
                       payloadSha256=payload_sha256, sourceRefs=source_refs)
        raw = canonical(payload)
        if len(raw) > self.maximum_record_bytes:
            raise ContractError("role record exceeds its admitted engineering byte bound")
        payload = json.loads(raw)  # freeze the caller's mutable references before append
        sequence = self.sequence + 1
        event_id = "aeb.role." + str(sequence)
        kwargs = dict(event_id=event_id, producer_id="assured-aeb.roles." + self.unit, event_kind="annotation",
                      producer_sequence=sequence, clocks={"simulation": {"domain": self.clock_domain, "unit": "ns", "value": sim_ns}},
                      annotation={"text": kind}, extensions={EXTENSION: payload})
        if cause is not None:
            kwargs["causation_id"] = cause
        try:
            ordinal = self.writer.append_event(**kwargs)
            if type(ordinal) is not int or ordinal <= 0:
                raise ContractError("Argus did not acknowledge the appended event")
        except BaseException:
            self.poisoned = True
            raise
        self.sequence = sequence
        self.event_ids.append(event_id)
        return event_id
