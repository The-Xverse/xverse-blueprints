"""Brake/ESC software-status node and chassis zone (Phase 8 WP-04; FR-033, AD-17 option B; review-wp04 finding 1).

Both are modules of the U5 ``vc-functional`` unit (decisions.md §J). They exchange only the typed messages of the WP-12
topology: the arbiter's ``brake-request`` → chassis zone → node; the node's ``brake-status`` → chassis zone; the node's
``brake-command`` (flow F17) → the vehicle-loop hub in U2, which hands it to the WP-03 driver arbitration through
``BrakeCommandReader``. The adapter remains the single actuator writer; nothing here writes to CARLA.

The node publishes only its own software status (received, accepted or rejected, forwarded; ``injected-fault`` is a
reserved vocabulary member that nothing emits in Phase 8). It publishes no wheel speed and makes no claim that the
brake was applied (V26). Its "accepted" status is the AD-14 actuator-facing acceptance point.

Only simulation time is used. Every ``*Ns`` stamp (``originNs``, ``atNs``, ``receivedNs``) is the absolute CARLA world
simulation clock in integer nanoseconds, as the compat items carry it; WP-03's ``sim_s`` is episode-relative, so the
reader converts it with the episode origin (review-wp04 finding 4, HIGH-1). The staleness window and the compute latency
are protocol values with no default: the parameter records are refused unless every member is supplied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

REQUEST = "assured-aeb.brake-request/1"
STATUS = "assured-aeb.brake-status/1"
COMMAND = "assured-aeb.brake-command/1"
NODE_PARAMS = "assured-aeb.brake-esc-node/1"
READER_PARAMS = "assured-aeb.brake-command-reader/1"

NODE = "brake-esc-node"
CHASSIS = "chassis-zone"
ARBITER = "functional-arbiter"
ROUTE = [ARBITER, CHASSIS]

STATUSES = ("received", "accepted", "rejected", "forwarded", "injected-fault")
REASONS = ("malformed", "wrong-source", "out-of-range", "stale", "replayed")
#: Actuator domain of the brake command: the CARLA adapter refuses a brake outside [0, 1] (xverse-compat
#: src/xverse_compat_carla/actuation.py 37-38). An engineering domain, not a protocol value.
BRAKE_MIN, BRAKE_MAX = 0.0, 1.0

ARBITER_REQUEST_MEMBERS = frozenset({"schema", "source", "sequence", "originNs", "value"})
ROUTED_REQUEST_MEMBERS = ARBITER_REQUEST_MEMBERS | {"route", "receivedNs"}
STATUS_MEMBERS = frozenset({"schema", "node", "status", "requestSequence", "reason", "atNs"})
COMMAND_MEMBERS = frozenset({"schema", "node", "sequence", "requestSequence", "requestOriginNs", "originNs", "value", "status"})


def _int(value: Any) -> bool:
    return type(value) is int


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def brake_request(sequence: int, origin_ns: int, value: float) -> dict[str, Any]:
    """The functional arbiter's per-cycle brake request (FR-041: one per decision cycle, possibly 0)."""

    return {"schema": REQUEST, "source": ARBITER, "sequence": sequence, "originNs": origin_ns, "value": value}


def check_vocabulary(message: dict[str, Any]) -> list[str]:
    """V26: return the violations of the closed status and command vocabulary (empty when the message conforms)."""

    problems = []
    schema = message.get("schema")
    members = {STATUS: STATUS_MEMBERS, COMMAND: COMMAND_MEMBERS}.get(schema)
    if members is None:
        return [f"undeclared schema {schema!r}"]
    if set(message) != members:
        problems.append(f"members {sorted(set(message) ^ members)} outside the declared vocabulary")
    if message.get("node") != NODE:
        problems.append("node identity")
    if schema == STATUS:
        if message.get("status") not in STATUSES:
            problems.append(f"status {message.get('status')!r}")
        if (message.get("status") == "rejected") != (message.get("reason") in REASONS):
            problems.append(f"reason {message.get('reason')!r} for status {message.get('status')!r}")
    elif message.get("status") != "forwarded":
        problems.append("a brake command carries only the forwarded status")
    return problems


# --------------------------------------------------------------------------------------------------
# Parameters (no defaults)
# --------------------------------------------------------------------------------------------------

def _record(record: Any, schema: str, members: frozenset[str]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError(f"the {schema} record must be an object")
    if set(record) != members:
        raise ValueError(f"{schema} members must be exactly {sorted(members)}; got {sorted(record)}")
    if record["schema"] != schema:
        raise ValueError(f"schema must be {schema}")
    return record


@dataclass(frozen=True)
class BrakeNodeParams:
    """``stalenessWindowNs`` (AD-06/AD-07) and ``computeLatencyNs`` (AD-30), from the frozen AD-27 record."""

    staleness_window_ns: int
    compute_latency_ns: int

    @classmethod
    def from_record(cls, record: Any) -> "BrakeNodeParams":
        record = _record(record, NODE_PARAMS, frozenset({"schema", "stalenessWindowNs", "computeLatencyNs"}))
        window, latency = record["stalenessWindowNs"], record["computeLatencyNs"]
        if not _int(window) or window <= 0:
            raise ValueError("stalenessWindowNs must be a positive integer (no default; AD-06/AD-07)")
        if not _int(latency) or latency < 0:
            raise ValueError("computeLatencyNs must be a non-negative integer (no default; AD-30)")
        return cls(window, latency)


@dataclass(frozen=True)
class ReaderParams:
    """``stalenessWindowNs`` of the gateway-side reader (AD-06/AD-07), from the frozen AD-27 record."""

    staleness_window_ns: int

    @classmethod
    def from_record(cls, record: Any) -> "ReaderParams":
        record = _record(record, READER_PARAMS, frozenset({"schema", "stalenessWindowNs"}))
        if not _int(record["stalenessWindowNs"]) or record["stalenessWindowNs"] <= 0:
            raise ValueError("stalenessWindowNs must be a positive integer (no default; AD-06/AD-07)")
        return cls(record["stalenessWindowNs"])


# --------------------------------------------------------------------------------------------------
# Chassis zone
# --------------------------------------------------------------------------------------------------

@dataclass
class ChassisZone:
    """Routes the arbiter's brake requests to the node, forwards motion evidence, records status (no authority)."""

    evidence: list[dict[str, Any]] = field(default_factory=list)

    def step(self, sim_ns: int, inbox: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
        """Process ``(interface, message)`` pairs delivered at ``sim_ns``; return ``(destination, message)`` pairs."""

        if not _int(sim_ns):
            raise ValueError("simulation time must be integer nanoseconds")
        out = []
        for interface, message in inbox:
            if interface == "brake-request":
                if (isinstance(message, dict) and set(message) == ARBITER_REQUEST_MEMBERS and message.get("schema") == REQUEST
                        and message.get("source") == ARBITER):
                    out.append((NODE, dict(message, source=CHASSIS, route=list(ROUTE), receivedNs=sim_ns)))
                else:
                    self.evidence.append({"kind": "route-refused", "atNs": sim_ns,
                                          "source": message.get("source") if isinstance(message, dict) else None})
            elif interface == "motion-evidence":
                out.append(("vehicle-state", message))
            elif interface in ("brake-status", "aeb-status"):
                self.evidence.append({"kind": interface, "atNs": sim_ns, "message": message})
            else:
                self.evidence.append({"kind": "undeclared-input", "atNs": sim_ns, "interface": interface})
        return out


# --------------------------------------------------------------------------------------------------
# Brake/ESC node
# --------------------------------------------------------------------------------------------------

class BrakeEscNode:
    """The FR-033 software-status node: received → accepted | rejected → forwarded (one F17 command per acceptance)."""

    def __init__(self, params: BrakeNodeParams) -> None:
        if type(params) is not BrakeNodeParams:
            raise TypeError("BrakeNodeParams.from_record is required (no default parameters)")
        self.params = params
        self.last_accepted_sequence: int | None = None
        self.command_sequence = 0
        self.evidence: list[dict[str, Any]] = []

    def _reject_reason(self, sim_ns: int, request: Any) -> str | None:
        if not isinstance(request, dict) or request.get("schema") != REQUEST or set(request) != ROUTED_REQUEST_MEMBERS:
            return "malformed"
        if not _int(request["sequence"]) or not _int(request["originNs"]) or not _int(request["receivedNs"]):
            return "malformed"
        if not _number(request["value"]):
            return "malformed"
        if request["source"] != CHASSIS or request["route"] != ROUTE:
            return "wrong-source"
        if not BRAKE_MIN <= request["value"] <= BRAKE_MAX:
            return "out-of-range"
        age = sim_ns - request["originNs"]
        if age < 0 or age > self.params.staleness_window_ns:
            return "stale"
        if self.last_accepted_sequence is not None and request["sequence"] <= self.last_accepted_sequence:
            return "replayed"
        return None

    def _status(self, status: str, sequence: Any, sim_ns: int, reason: str | None = None) -> dict[str, Any]:
        return {"schema": STATUS, "node": NODE, "status": status, "requestSequence": sequence if _int(sequence) else None,
                "reason": reason, "atNs": sim_ns}

    def step(self, sim_ns: int, requests: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Process the routed requests delivered at ``sim_ns``.

        @return ``{"status": [...], "commands": [...]}``: status messages to the chassis zone and F17 commands to
            the hub, in emission order. Every message is also appended to ``evidence`` (V34 inputs).
        """

        if not _int(sim_ns):
            raise ValueError("simulation time must be integer nanoseconds")
        ordered = sorted(requests, key=lambda r: (r.get("sequence") if isinstance(r, dict) and _int(r.get("sequence")) else -1))
        statuses, commands = [], []
        for request in ordered:
            sequence = request.get("sequence") if isinstance(request, dict) else None
            statuses.append(self._status("received", sequence, sim_ns))
            reason = self._reject_reason(sim_ns, request)
            if reason is not None:
                statuses.append(self._status("rejected", sequence, sim_ns, reason))
                continue
            self.last_accepted_sequence = sequence
            statuses.append(self._status("accepted", sequence, sim_ns))
            self.command_sequence += 1
            commands.append({"schema": COMMAND, "node": NODE, "sequence": self.command_sequence, "requestSequence": sequence,
                             "requestOriginNs": request["originNs"], "originNs": sim_ns + self.params.compute_latency_ns,
                             "value": float(request["value"]), "status": "forwarded"})
            statuses.append(self._status("forwarded", sequence, sim_ns))
        self.evidence.extend(statuses + commands)
        return {"status": statuses, "commands": commands}


# --------------------------------------------------------------------------------------------------
# Gateway-side reader: the WP-03 ``brake_request`` source (review-wp03 B-3)
# --------------------------------------------------------------------------------------------------

class BrakeCommandReader:
    """``brake_request(sim_s)`` for ``ArbitratedDriver``: 0.0 when no request is active, the newest forwarded value
    while fresh, and ``None`` (invalid: WP-03 holds the last brake with throttle 0) when stale, lost or not yet
    deliverable.

    @param params Validated ``ReaderParams``.
    @param episode_origin_ns The absolute world simulation time (integer ns) of the episode's first ticked frame, set
        by the U2 loop. ``sim_s`` is relative to it (compat ``live/loop.py``), while F17 ``originNs`` is absolute. There
        is no default: the reader refuses to construct without it.
    """

    def __init__(self, params: ReaderParams, *, episode_origin_ns: int) -> None:
        if type(params) is not ReaderParams:
            raise TypeError("ReaderParams.from_record is required (no default parameters)")
        if not _int(episode_origin_ns) or episode_origin_ns < 0:
            raise TypeError("episode_origin_ns must be the integer ns world time of the episode's first frame (no default)")
        self.params = params
        self.episode_origin_ns = episode_origin_ns
        self.newest: dict[str, Any] | None = None
        self.lost = False
        self.refused = 0

    def deliver(self, command: dict[str, Any]) -> None:
        """Store an F17 command delivered by the hub; a non-conforming or older command is refused and counted."""

        if check_vocabulary(command) or command.get("schema") != COMMAND or not _int(command.get("sequence")) \
                or not _int(command.get("originNs")) or not _number(command.get("value")):
            self.refused += 1
            return
        if self.newest is not None and command["sequence"] <= self.newest["sequence"]:
            self.refused += 1
            return
        self.newest = command
        self.lost = False

    def mark_lost(self) -> None:
        """The hub reports the F17 flow lost (its receiver verdict); the source is invalid until a new command."""

        self.lost = True

    def __call__(self, sim_s: float) -> float | None:
        if not _number(sim_s):
            raise ValueError("simulation time must be a finite number of seconds")
        if self.lost:
            return None
        if self.newest is None:
            return 0.0  # B-3: no active request before the node's first command
        age = self.episode_origin_ns + round(sim_s * 1e9) - self.newest["originNs"]
        if age < 0:
            return None  # a future origin is not deliverable: WP-03 cuts throttle and holds the brake
        if age > self.params.staleness_window_ns:
            return None
        return 0.0 if self.newest["value"] == 0.0 else self.newest["value"]
