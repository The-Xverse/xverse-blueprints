"""WP-14e deterministic U4 goals/proposals: no authorization or control authority.

Only a selected own-unit parameter projection and delivered runtime messages enter
these roles. Actual objective tokens, freshness and validity are explicit inputs.
Each role is called once with its whole cycle inbox: both simulator time and step must strictly advance.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from types import MappingProxyType

from . import role_contract as C
from .parameters import Projection
from .role_events import RoleEvents, payload_digest

NOMINAL, DEGRADED = "C_NOMINAL", "C_DEGRADED_RADAR"
MAPPINGS = "goals.objectiveMappings"
DURATIONS = {
    "goals.objectiveFreshnessNs": ("positive-int",),
    "proposer.goalFreshnessNs": ("positive-int",),
    "proposer.configurationFreshnessNs": ("positive-int",),
    "proposer.basisFreshnessNs": ("positive-int",),
    "proposer.proposalValidityNs": ("positive-int",),
}
IDENTIFIERS = frozenset({MAPPINGS, *DURATIONS})
TOKEN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
CONSTRAINTS = {"targetConfiguration", "validUntilNs", "objectiveSha256"}
BASIS_MEMBERS = {"schema", "source", "cycle", "sequence", "originNs", "brakeRequest", "fired", "latched",
                 "reason", "hypothesis", "sources", "state", "paramsSha256"}


def _uint(value):
    return type(value) is int and value >= 0


def _text(value):
    return isinstance(value, str) and bool(value)


class U4Policy:
    """Detached, closed 14e-only parameter slice; does not read a whole protocol."""
    def __init__(self, projection):
        if type(projection) is not Projection or projection.record["unit"] != "adas-hpc":
            raise C.ContractError("an own-U4 Projection is required")
        projection.check_exact(IDENTIFIERS)
        values = projection.take(DURATIONS)
        mapping = projection.entries.get(MAPPINGS)
        C.canonical(mapping)
        if not isinstance(mapping, list) or not mapping:
            raise C.ContractError("an explicit closed objective mapping is required")
        targets = {}
        for item in mapping:
            if (not isinstance(item, dict) or set(item) != {"objective", "targetConfiguration"}
                    or not isinstance(item["objective"], str) or TOKEN.fullmatch(item["objective"]) is None
                    or item["objective"] in targets or item["targetConfiguration"] not in (NOMINAL, None)):
                raise C.ContractError("objective mapping must contain unique tokens and nominal/hold targets only")
            targets[item["objective"]] = item["targetConfiguration"]
        self.values = MappingProxyType(values)
        self.targets = MappingProxyType(targets)
        self.protocol_sha256 = projection.record["protocolRecordSha256"]
        self.sha256 = payload_digest({"protocolRecordSha256": self.protocol_sha256,
                                     "entries": {**values, MAPPINGS: mapping}})


@dataclass(frozen=True)
class Delivered:
    """Payload plus separate transport-attested producer and actual message ID."""
    payload: object
    producer: str
    message_id: str


def _binding(binding, interface, producer, consumer):
    if type(binding) is not C.EndpointBinding or (binding.interface, binding.producer, binding.consumer) != (interface, producer, consumer):
        raise C.ContractError("an exact admitted endpoint binding is required")
    return binding


def _delivery(value):
    if type(value) is not Delivered or not _text(value.producer) or not _text(value.message_id):
        raise C.ContractError("a delivered payload with separate source and message identity is required")


class _Stream:
    def __init__(self, maximum):
        self.sequence, self.origin = None, None
        self.ids, self.logical_ids, self.maximum = set(), set(), maximum

    def accept(self, incoming, record, now_ns, freshness, logical_id=None):
        sequence, origin = record["sequence"], record["originNs"]
        if (self.sequence is not None and sequence <= self.sequence) or (self.origin is not None and origin < self.origin):
            raise C.ContractError("replayed or regressing input")
        if incoming.message_id in self.ids or (logical_id is not None and logical_id in self.logical_ids):
            raise C.ContractError("reused accepted message or binding identity")
        if len(self.ids) >= self.maximum:
            raise C.ContractError("admitted engineering identity capacity exhausted")
        if not 0 <= now_ns-origin <= freshness:
            raise C.ContractError("future or stale input")
        self.sequence, self.origin = sequence, origin
        self.ids.add(incoming.message_id)
        if logical_id is not None:
            self.logical_ids.add(logical_id)


class _Role:
    def __init__(self, policy, events, identity_prefix, maximum_accepted_messages, role):
        if type(policy) is not U4Policy or type(events) is not RoleEvents or events.unit != "adas-hpc" or role not in events.roles:
            raise C.ContractError("own-U4 policy and shared local RoleEvents adapter required")
        if not isinstance(identity_prefix, str) or TOKEN.fullmatch(identity_prefix) is None:
            raise C.ContractError("an admitted unique identity prefix is required")
        if type(maximum_accepted_messages) is not int or maximum_accepted_messages <= 0:
            raise C.ContractError("a positive admitted engineering identity bound is required")
        self.policy, self.events, self.prefix, self.maximum = policy, events, identity_prefix, maximum_accepted_messages
        self.role, self.sequence, self.last_now, self.last_step = role, 0, None, None
        self.last_decision = None

    def _clock(self, now_ns, step):
        if (not _uint(now_ns) or not _uint(step) or (self.last_now is not None and now_ns <= self.last_now)
                or (self.last_step is not None and step <= self.last_step)):
            raise C.ContractError("nonnegative strictly advancing simulator time and step are required; one complete role call per cycle")
        self.last_now, self.last_step = now_ns, step

    def _decision(self, now_ns, step, outcome, reason):
        self.last_decision = dict(schema="assured-aeb.untrusted-role-decision/1", role=self.role,
                                  identityPrefix=self.prefix, policySha256=self.policy.sha256,
                                  simNs=now_ns, step=step, outcome=outcome, reason=reason)


class GoalInterpreter(_Role):
    """Maps one authorized typed objective to nominal-return or hold constraints."""
    def __init__(self, *, policy, binding, events, identity_prefix, maximum_accepted_messages):
        super().__init__(policy, events, identity_prefix, maximum_accepted_messages, "goal-interpreter")
        self.binding = _binding(binding, "objective", "objective-source", "goal-interpreter")
        self.stream = _Stream(self.maximum)
        self.current = None

    def _reject(self, now_ns, step, reason, incoming=None):
        diagnostic = {"role": self.role, "reason": reason}
        digest, refs, bindings = payload_digest(diagnostic), [], {}
        if type(incoming) is Delivered and _text(incoming.message_id):
            try:
                digest = payload_digest(incoming.payload)
            except C.ContractError:
                pass  # explicitly diagnostic digest; no invented source-byte reference
            else:
                refs = [{"messageId": incoming.message_id, "sha256": digest}]
                if isinstance(incoming.payload, dict) and _text(incoming.payload.get("objectiveId")):
                    bindings["objectiveId"] = incoming.payload["objectiveId"]
        self.events.emit(role=self.role, kind="rejection", bindings=bindings, sim_ns=now_ns, step=step,
                         configuration=None, outcome="rejected", reason=reason, payload_sha256=digest, source_refs=refs)
        self._decision(now_ns, step, "rejected", reason)

    def step(self, now_ns, *, step, objectives=()):
        # The existing admitted identity capacity also bounds per-call rejection work. This is a caller error,
        # before the cycle is consumed; it is not a claim that each member was rejected with runtime evidence.
        if isinstance(objectives, (list, tuple)) and len(objectives) > self.maximum:
            raise C.ContractError("objective batch exceeds the admitted engineering member bound")
        self._clock(now_ns, step)
        if not isinstance(objectives, (list, tuple)):
            self._reject(now_ns, step, "objective-batch-malformed")
            return None
        if not objectives:
            self._decision(now_ns, step, "no-output", "no-new-objective")
            return None
        if len(objectives) != 1:
            for incoming in objectives:
                self._reject(now_ns, step, "objective-batch-ambiguous", incoming)
            return None
        incoming = objectives[0]
        try:
            _delivery(incoming)
            record = self.binding.consume(incoming.payload, received_producer=incoming.producer)
            if record["objective"] not in self.policy.targets:
                raise C.ContractError("unknown objective")
            if not record["originNs"] <= now_ns <= record["validUntilNs"]:
                raise C.ContractError("objective is future or expired")
            self.stream.accept(incoming, record, now_ns, self.policy.values["goals.objectiveFreshnessNs"], record["objectiveId"])
        except C.ContractError:
            self._reject(now_ns, step, "objective-refused", incoming)
            return None
        sequence = self.sequence + 1
        goal = C.make_record("goal-model", source="goal-interpreter", sequence=sequence, origin_ns=now_ns,
                             goalId=f"{self.prefix}.goal.{sequence}", objectiveId=record["objectiveId"],
                             constraints={"targetConfiguration": self.policy.targets[record["objective"]],
                                          "validUntilNs": min(record["validUntilNs"], record["originNs"] +
                                                              self.policy.values["goals.objectiveFreshnessNs"]),
                                          "objectiveSha256": payload_digest(record)},
                             basisRefs=[incoming.message_id])
        self.sequence, self.current = sequence, json.loads(C.canonical(goal))
        self._decision(now_ns, step, "goal-created", "declared-objective-mapped")
        return goal


def _goal(record):
    constraints = record["constraints"]
    if (set(constraints) != CONSTRAINTS or constraints["targetConfiguration"] not in (NOMINAL, None)
            or not _uint(constraints["validUntilNs"]) or constraints["validUntilNs"] < record["originNs"]
            or not isinstance(constraints["objectiveSha256"], str) or C.DIGEST.fullmatch(constraints["objectiveSha256"]) is None
            or len(record["basisRefs"]) != 1):
        raise C.ContractError("invalid bounded goal constraints or objective basis")


def _basis(binding, incoming):
    record = incoming.payload
    raw = C.canonical(record)
    if (incoming.producer != binding.producer or not isinstance(record, dict) or set(record) != BASIS_MEMBERS
            or record["schema"] != C.LEGACY_SCHEMAS["proposal-basis"] or record["source"] != binding.producer
            or not all(_uint(record[key]) for key in ("sequence", "originNs", "cycle"))
            or type(record["brakeRequest"]) not in (int, float) or not 0 <= record["brakeRequest"] <= 1
            or type(record["fired"]) is not bool or type(record["latched"]) is not bool
            or record["state"] not in C.STATES or not (record["reason"] is None or _text(record["reason"]))
            or not isinstance(record["hypothesis"], dict) or not isinstance(record["sources"], dict)
            or set(record["sources"]) != {"camera", "radar"}
            or not isinstance(record["paramsSha256"], str) or C.DIGEST.fullmatch(record["paramsSha256"]) is None):
        raise C.ContractError("malformed or foreign productive fusion basis")
    for source in record["sources"].values():
        if (not isinstance(source, dict) or source.get("state") not in C.STATES
                or not isinstance(source.get("failures"), list) or not all(_text(x) for x in source["failures"])):
            raise C.ContractError("missing consumed fusion source state/failures")
    return json.loads(raw)


class DeterministicProposer(_Role):
    """Emits nominal-return candidates; never permissions, selectors or actuation."""
    def __init__(self, *, policy, goal_binding, configuration_binding, basis_binding,
                 events, identity_prefix, maximum_accepted_messages):
        super().__init__(policy, events, identity_prefix, maximum_accepted_messages, "proposer")
        self.bindings = {
            "goal": _binding(goal_binding, "goal-model", "goal-interpreter", "proposer"),
            "configuration": _binding(configuration_binding, "configuration-state", "configuration-manager", "proposer"),
            "basis": _binding(basis_binding, "proposal-basis", "fusion-risk-aeb", "proposer"),
        }
        self.streams = {key: _Stream(self.maximum) for key in self.bindings}
        self.cached = {}
        self.terminal = False

    def _ingest(self, name, messages, now_ns):
        if not isinstance(messages, (list, tuple)) or len(messages) > 1:
            self.cached.pop(name, None)
            raise C.ContractError("ambiguous or malformed delivered batch")
        if not messages:
            return False
        self.cached.pop(name, None)
        incoming = messages[0]
        _delivery(incoming)
        binding = self.bindings[name]
        record = _basis(binding, incoming) if name == "basis" else binding.consume(incoming.payload, received_producer=incoming.producer)
        if name == "goal":
            _goal(record)
            if record["constraints"]["validUntilNs"] < now_ns:
                raise C.ContractError("expired objective constraints")
        if name == "configuration" and record["committedAtNs"] > record["originNs"]:
            raise C.ContractError("configuration commit is later than its record")
        self.streams[name].accept(incoming, record, now_ns, self.policy.values[f"proposer.{name}FreshnessNs"],
                                  record["goalId"] if name == "goal" else None)
        self.cached[name] = (Delivered(record, incoming.producer, incoming.message_id), record)
        if name == "configuration" and record["configuration"] == "S_MRC_REQUESTED":
            self.terminal = True
        return True

    def step(self, now_ns, *, step, goals=(), configurations=(), bases=()):
        self._clock(now_ns, step)
        failed, new_basis = [], False
        for name, messages in (("goal", goals), ("configuration", configurations), ("basis", bases)):
            try:
                updated = self._ingest(name, messages, now_ns)
                if name == "basis":
                    new_basis = updated
            except C.ContractError:
                failed.append(name)
        if failed:
            self._decision(now_ns, step, "no-output", "refused-" + "-".join(failed))
            return None
        if self.terminal:
            self._decision(now_ns, step, "no-output", "terminal-lockout")
            return None
        if not new_basis or set(self.cached) != set(self.bindings):
            self._decision(now_ns, step, "no-output", "no-new-basis-or-missing-input")
            return None
        for name, (_, record) in self.cached.items():
            if not 0 <= now_ns-record["originNs"] <= self.policy.values[f"proposer.{name}FreshnessNs"]:
                self._decision(now_ns, step, "no-output", "expired-" + name)
                return None
        goal, configuration, basis = (self.cached[key][1] for key in ("goal", "configuration", "basis"))
        if (goal["constraints"]["targetConfiguration"] != NOMINAL or configuration["configuration"] != DEGRADED
                or configuration["phase"] != "confirmed" or basis["state"] != "NOMINAL" or basis["reason"] is not None
                or any(source["state"] != "NOMINAL" or source["failures"] for source in basis["sources"].values())):
            self._decision(now_ns, step, "no-output", "nominal-return-not-requested-or-supported")
            return None
        expiry = min(now_ns+self.policy.values["proposer.proposalValidityNs"], goal["constraints"]["validUntilNs"],
                     *(record["originNs"]+self.policy.values[f"proposer.{name}FreshnessNs"]
                       for name, (_, record) in self.cached.items()))
        if expiry < now_ns:
            self._decision(now_ns, step, "no-output", "expired-objective")
            return None
        references = [self.cached[key][0].message_id for key in ("goal", "configuration", "basis")] + goal["basisRefs"]
        if len(set(references)) != len(references):
            self._decision(now_ns, step, "no-output", "ambiguous-basis-message-identities")
            return None
        sequence = self.sequence+1
        proposal = C.make_record("proposal", source="proposer", sequence=sequence, origin_ns=now_ns,
                                 proposalId=f"{self.prefix}.proposal.{sequence}", target=NOMINAL,
                                 fromConfiguration=configuration["configuration"], basisRefs=references, validUntilNs=expiry)
        refs = [{"messageId": self.cached[key][0].message_id, "sha256": payload_digest(self.cached[key][1])}
                for key in ("goal", "configuration", "basis")]
        refs.append({"messageId": goal["basisRefs"][0], "sha256": goal["constraints"]["objectiveSha256"]})
        self.events.emit(role="proposer", kind="proposal-created",
                         bindings={"proposalId": proposal["proposalId"], "goalId": goal["goalId"], "objectiveId": goal["objectiveId"]},
                         sim_ns=now_ns, step=step, configuration=configuration["configuration"], outcome="proposed",
                         reason="untrusted-nominal-return-candidate", payload_sha256=payload_digest(proposal), source_refs=refs)
        self.sequence = sequence
        self._decision(now_ns, step, "proposal-created", "independent-authorization-still-required")
        return proposal
