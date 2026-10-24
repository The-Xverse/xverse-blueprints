"""Offline topology check of the assured AEB blueprint (Phase 8, WP-12; thesis design record wp12-xdl-topology.md).

It never starts a unit, a simulator or a Maestro run. It runs these checks, through the platform XDL and Maestro APIs
of the installed X-Verse Lite wheel:

- **drift**: the committed documents under ``xdl/<arm>/<form>/`` equal the generator output of ``topology.py``;
- **V01**: each arm and form validates and compiles; the plan digest is deterministic; the declared elements are
  present (units, element instances, both radar flows, IVI without instance or endpoint, the exclusions);
- **V02**: the authority rules A-1 to A-7 of the design record (§3.3) over every declared message;
- **D-4a**:
  - unbound element instances are accepted next to the bound unit instances (``prepare_lifecycle``);
  - provider route assignment (``xverse.flows.binding.bind``: at most 4 routes per provider);
  - two concurrent ``freeze`` entries for CC-1 are admitted, and the blueprint freeze-target rule refuses the rest;
  - the admission dry run (``admit_schedule``) at 5, 6 and 7 units, with the encoded persistence-configuration size
    against the 65 536-byte limit (C1 dependency).

Usage::

    python check_topology.py --platform-profiles <rc.1 export>/xdl/profiles [--report report.json]

Exit status 0 when every check passes, where a recorded *expected residual* also counts as passing; 1 otherwise.
Synthetic inputs (the provider helper pin, the permits, the host session) are owned-harness values, as in the
platform persistence bench. They are not approvals and are evidence of nothing else.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import glob
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import topology as T  # noqa: E402

PERSISTENCE_LIMIT = 65536  # bootstrap.py 1116-1118 (ML-BOOT-PERSISTENCE); raised by the separate C1 increment
OPERATION_BUDGETS = (0.38, 0.29, 0.25, 0.20)
UNIT_COUNTS = {5: "comparator", 6: "mloc", 7: T.VARIANT_7}
LIVE = {"cadence": 5, "freshness": 5, "readiness": 1.7, "active": 55, "service": 4, "perUnit": 2, "poll": 0.05,
        "requestLimit": 8192, "eventLimit": 8192, "horizon": T.HORIZON}
COMMANDS = {"authorization", "forced-command", "selector-command", "transition-request", "brake-request", "brake-command",
            "actuation-command", "mrc-request", "fallback-request"}
ENV_RAW = {"camera-raw", "radar-raw", "motion-raw", "actuation-command", "throttle-command"}
MANAGER_INPUTS = {("authorization", "gate"), ("forced-command", "fallback-supervisor"), ("transition-verdict", "verifier")}
CHAINS = {  # A-4: (interface, producer element) -> permitted consumer elements
    ("brake-request", "functional-arbiter"): {"chassis-zone"},
    ("brake-request", "chassis-zone"): {"brake-esc-node"},
    ("brake-command", "brake-esc-node"): {"loop-gateway"},
    ("actuation-command", "loop-gateway"): {"carla-client"},
    ("selector-command", "configuration-manager"): {"functional-arbiter"},
    ("fallback-request", "radar-fallback"): {"functional-arbiter"},
}
UNTRUSTED = {"proposer", "goal-interpreter", "evidence-router", "evidence-source"}
#: Known residuals, not failures (decisions.md §J and §K): (check, arm, detail)
EXPECTED_RESIDUALS = {
    ("routes", "authorization-bypass", "f19-bypass-proposal"): "F19 is U5's fifth inbound route; resolved in WP-16 (§K)",
}


@dataclass
class Report:
    checks: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, ok: bool, **detail: Any) -> None:
        self.checks.append({"check": name, "ok": bool(ok), **detail})

    @property
    def ok(self) -> bool:
        return all(c["ok"] for c in self.checks)


# --------------------------------------------------------------------------------------------------
# Compilation
# --------------------------------------------------------------------------------------------------

def schemas(profile_dir: Path) -> tuple[str, ...]:
    found = tuple(sorted(glob.glob(str(profile_dir / "*.schema.json"))))
    if not found:
        raise SystemExit(f"no platform profile schema in {profile_dir}")
    return found + (str(HERE / "xdl" / "profiles" / "assured-aeb-v0.1.schema.json"),)


def load(arm: str, form: str) -> dict[str, dict[str, Any]]:
    folder = T.XDL / arm / form
    return {p.name: json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))}


def compile_docs(docs: dict[str, dict[str, Any]], schema_paths: tuple[str, ...]):
    from xverse_xdl.experiment_plan import compile_experiment_plan
    from xverse_xdl.validate import validate_sources

    validation = validate_sources([(n, json.dumps(d).encode()) for n, d in sorted(docs.items())], profile_schema_paths=schema_paths)
    if not validation.is_valid:
        return validation, None
    return validation, compile_experiment_plan(validation.resources)


def _diag(items) -> list[dict[str, str]]:
    return [{"code": d.code, "pointer": d.pointer, "message": d.message[:200]} for d in items][:20]


def plain_plan(result) -> dict[str, Any]:
    return json.loads(json.dumps(result.plan, default=lambda v: dict(v) if hasattr(v, "items") else list(v)))


# --------------------------------------------------------------------------------------------------
# Message model (forward flows, return flows, intra-unit messages)
# --------------------------------------------------------------------------------------------------

def messages(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every declared message as producer/consumer elements, interface and kind."""

    system = docs["system.json"]
    spec, ext = system["spec"], system["extensions"][T.EXT]
    owner = {e["id"]: e["ownerId"] for e in spec["endpoints"]}
    rows = []
    for flow in spec.get("flows", []):
        rows.append({"id": flow["id"], "kind": "forward", "producer": owner[flow["sourceEndpointId"]],
                     "consumer": owner[flow["destinationEndpointIds"][0]], "interface": flow["interfaceId"],
                     "exception": flow.get("extensions", {}).get(T.EXT, {}).get("ablationException")})
    for flow in ext["returnFlows"]:
        rows.append({"id": flow["id"], "kind": "return", "producer": owner[flow["source"]], "consumer": owner[flow["destination"]],
                     "interface": flow["interfaceId"], "exception": flow["declaration"].get("ablationException")})
    for index, msg in enumerate(ext["intraUnitMessages"]):
        rows.append({"id": f"intra-{index}", "kind": "intra", "producer": owner[msg["source"]], "consumer": owner[msg["destination"]],
                     "interface": msg["interfaceId"], "exception": None})
    return rows


def placement(docs: dict[str, dict[str, Any]]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Return (element -> host unit, element -> authority class, unit -> unit class)."""

    components = {d["metadata"]["name"]: d for d in docs.values() if d["kind"] == "Component"}
    host, authority, unit_class = {}, {}, {}
    for inst in docs["system.json"]["spec"]["componentInstances"]:
        payload = inst.get("extensions", {}).get(T.EXT, {})
        if payload.get("kind") == "unit-host":
            unit_class[inst["id"]] = payload["unitClass"]
        else:
            host[inst["id"]] = payload.get("hostUnit")
            authority[inst["id"]] = components[inst["componentRef"]["name"]]["extensions"][T.EXT]["authorityClass"]
    return host, authority, unit_class


def check_authority(docs: dict[str, dict[str, Any]], arm: str) -> list[str]:
    """Return the A-1 to A-7 violations of ``docs`` (empty when the authority contract holds)."""

    violations: list[str] = []
    spec = docs["system.json"]["spec"]
    components = {d["metadata"]["name"]: d for d in docs.values() if d["kind"] == "Component"}
    instances = {i["id"]: i for i in spec["componentInstances"]}
    host, authority, unit_class = placement(docs)
    # A-1: every output endpoint's interface is permitted for its Component.
    for endpoint in spec["endpoints"]:
        if endpoint["direction"] != "output":
            continue
        inst = instances.get(endpoint["ownerId"])
        if inst is None:
            violations.append(f"A-1 endpoint {endpoint['id']} is owned by a non-instance {endpoint['ownerId']}")
            continue
        permitted = components[inst["componentRef"]["name"]]["extensions"][T.EXT]["permittedOutputs"]
        if endpoint["interfaceId"] not in permitted:
            violations.append(f"A-1 {endpoint['ownerId']} emits {endpoint['interfaceId']} outside its permittedOutputs")
    for msg in messages(docs):
        producer, consumer, interface = msg["producer"], msg["consumer"], msg["interface"]
        excepted = msg["exception"] == arm
        pclass = authority.get(producer)
        # A-2: only the gate authorizes.
        if interface == "authorization" and pclass != "gate":
            violations.append(f"A-2 {msg['id']}: authorization from {producer} ({pclass})")
        # A-3: the configuration manager accepts only the gate, the fixed supervisor and the verifier.
        if consumer == "configuration-manager" and (interface, pclass) not in MANAGER_INPUTS and not excepted:
            violations.append(f"A-3 {msg['id']}: {interface} from {producer} ({pclass}) reaches the configuration manager")
        # A-4: the brake and selector chains.
        for (chain_interface, chain_producer), consumers in CHAINS.items():
            if interface == chain_interface and (producer != chain_producer and (interface, producer) not in CHAINS):
                violations.append(f"A-4 {msg['id']}: {interface} produced by {producer}")
            if interface == chain_interface and producer == chain_producer and consumer not in consumers:
                violations.append(f"A-4 {msg['id']}: {interface} from {producer} to {consumer}")
        # A-5: untrusted classes emit no command.
        if pclass in UNTRUSTED and interface in COMMANDS:
            violations.append(f"A-5 {msg['id']}: untrusted {producer} ({pclass}) emits {interface}")
        # A-6: intra messages stay in one unit; flows cross units.
        same = host.get(producer) == host.get(consumer)
        if msg["kind"] == "intra" and not same:
            violations.append(f"A-6 {msg['id']}: intra-unit message crosses {host.get(producer)} -> {host.get(consumer)}")
        if msg["kind"] != "intra" and same:
            violations.append(f"A-6 {msg['id']}: inter-unit flow inside {host.get(producer)}")
        # A-7: runtime elements take no environment-raw input and nothing from experiment control.
        if unit_class.get(host.get(consumer)) == "runtime":
            if interface in ENV_RAW:
                violations.append(f"A-7 {msg['id']}: runtime {consumer} receives raw environment item {interface}")
            if pclass == "experiment-control" and not excepted:
                violations.append(f"A-7 {msg['id']}: runtime {consumer} receives from experiment control {producer}")
    # A-5 (IVI): no instance and no endpoint on the IVI node.
    for inst in spec["componentInstances"]:
        if inst.get("nodeId") == "ivi-hpc":
            violations.append(f"A-5 IVI hosts instance {inst['id']}")
    # A-7: no evaluation-only interface or instance in the System.
    for item in list(spec.get("interfaces", [])) + list(spec["componentInstances"]):
        if "ground-truth" in item["id"] or "oracle" in item["id"] or "observer" in item["id"]:
            violations.append(f"A-7 evaluation-only element {item['id']} declared in the System")
    return violations


@dataclass(frozen=True)
class FreezeBound:
    """The thaw bound a freeze must respect, known only per admitted schedule and host (never a protocol value).

    ``thaw_bound_s`` is ``cadence - health_scan_seconds`` of the admitted schedule (the WP-11 bound; 3.26 s at 6 units
    and op 0.29 in the D-4a dry run). ``max_cycle_s`` is the measured maximum dispatcher cycle (D-4c), which converts
    the bound into Maestro ticks. Both are supplied by the caller.
    """

    thaw_bound_s: float
    max_cycle_s: float

    @property
    def max_ticks(self) -> int:
        return int(self.thaw_bound_s // self.max_cycle_s)


def _onset_and_duration(fault: dict[str, Any]) -> tuple[Any, Any]:
    intent = fault.get("extensions", {}).get(T.EXPERIMENT, {})
    trigger, duration = intent.get("trigger", {}), intent.get("duration", {})
    return ((trigger.get("kind"), trigger.get("at"), trigger.get("unit"), intent.get("timeDomainId")),
            (duration.get("value"), duration.get("unit")))


def check_fault_admission(docs: dict[str, dict[str, Any]], faults: list[dict[str, Any]],
                          freeze_bound: FreezeBound | None = None) -> list[str]:
    """Blueprint freeze-target and relay-admission rule (design §2.2, §5): return refusals (empty = admitted).

    WP-10 and WP-16 must call this on the exact fault schedule before ``admit_schedule`` and refuse on any
    finding: the platform admits every refused case statically (finding 2, L-7; finding 3, MEDIUM-2).

    - A freeze targets an individually admitted unit, or a member of an admitted set when *every* member of that set
      is frozen with the same onset and the same duration (CC-1); a lone or non-concurrent member is refused
      (finding 3, HIGH-1).
    - When ``freeze_bound`` is given, a freeze longer than its tick bound is refused; without it, durations are not
      bounded here and the report says so.
    """

    ext = docs["system.json"]["extensions"][T.EXT]
    freeze = ext["freezeTargets"]
    single = set(freeze["admitted"])
    sets = [tuple(group) for group in freeze["admittedSets"]]
    flows = {f["id"]: f for f in docs["system.json"]["spec"].get("flows", [])}
    freezes = [f for f in faults if f["faultKind"] == "freeze"]
    refusals = []
    for fault in faults:
        element = fault["targetRef"]["element"]
        kind = fault["faultKind"]
        if kind in freeze["refusedKinds"]:
            refusals.append(f"{fault['id']}: kind {kind} refused (DLG-3: an applied crash ends the run)")
        elif kind == "freeze":
            if element in single:
                pass
            elif any(element in group for group in sets):
                timing = _onset_and_duration(fault)
                complete = any(element in group and all(
                    any(other["targetRef"]["element"] == member and _onset_and_duration(other) == timing for other in freezes)
                    for member in group) for group in sets)
                if not complete:
                    refusals.append(f"{fault['id']}: freeze of {element} refused (member of an admitted set, but not every "
                                    "member is frozen with the same onset and duration)")
            else:
                reason = "never-frozen unit" if element in freeze["refused"] else "not an admitted unit instance"
                refusals.append(f"{fault['id']}: freeze of {element} refused ({reason})")
            if freeze_bound is not None:
                value, unit = _onset_and_duration(fault)[1]
                if unit != "tick" or not isinstance(value, (int, float)) or value > freeze_bound.max_ticks:
                    refusals.append(f"{fault['id']}: freeze duration {value} {unit} exceeds the thaw bound "
                                    f"({freeze_bound.thaw_bound_s} s / {freeze_bound.max_cycle_s} s per tick = "
                                    f"{freeze_bound.max_ticks} ticks)")
        elif element in flows:
            allowed = flows[element].get("extensions", {}).get(T.EXT, {}).get("faultAdmission", [])
            if kind not in allowed:
                refusals.append(f"{fault['id']}: {kind} on {element} not admitted in Phase 8 (decisions.md §K)")
        else:
            refusals.append(f"{fault['id']}: {kind} on {element} has no admitted target")
    return refusals


def check_cycles(docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Strongly connected components of the full element graph (forward, return and intra-unit messages) after removing
    the hub-delayed flows. A component that spans two units is an unbroken cross-unit loop (finding 3, MEDIUM-1).
    Components inside one unit are resolved by that unit's own step order (WP-13/WP-14) and are listed."""

    system = docs["system.json"]
    delayed = {f["id"] for f in system["spec"].get("flows", []) if f.get("extensions", {}).get(T.EXT, {}).get("hubDelay")}
    delayed |= {f["id"] for f in system["extensions"][T.EXT]["returnFlows"] if f["declaration"].get("hubDelay")}
    host, _, _ = placement(docs)
    graph: dict[str, set[str]] = {}
    for msg in messages(docs):
        graph.setdefault(msg["producer"], set())
        graph.setdefault(msg["consumer"], set())
        if msg["id"] not in delayed:
            graph[msg["producer"]].add(msg["consumer"])
    index, low, stack, on, comps, counter = {}, {}, [], set(), [], [0]

    def visit(node: str) -> None:  # Tarjan (iterative enough for this graph size)
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on.add(node)
        for succ in sorted(graph[node]):
            if succ not in index:
                visit(succ)
                low[node] = min(low[node], low[succ])
            elif succ in on:
                low[node] = min(low[node], index[succ])
        if low[node] == index[node]:
            comp = []
            while True:
                item = stack.pop()
                on.discard(item)
                comp.append(item)
                if item == node:
                    break
            if len(comp) > 1:
                comps.append(sorted(comp))

    for node in sorted(graph):
        if node not in index:
            visit(node)
    cross = [c for c in comps if len({host.get(n) for n in c}) > 1]
    intra = [{"unit": host.get(c[0]), "elements": c} for c in comps if len({host.get(n) for n in c}) == 1]
    return {"delayPoints": sorted(delayed), "crossUnitCycles": cross, "intraUnitCycles": intra}


def forms_difference(arm: str, topology_docs: dict[str, dict[str, Any]] | None = None,
                     maestro_docs: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Return how the two forms differ beyond the declared projection (finding 3, LOW-1); empty when they agree.

    Allowed differences: the Maestro form has no flows, networks, provider targets, network bindings or CARLA
    simulator, only the experiment-time domain, and the extension members ``form`` and ``unplannedFlows``."""

    top = topology_docs or load(arm, "topology")
    mae = maestro_docs or load(arm, "maestro")
    diff = []
    for key in ("componentInstances", "endpoints", "interfaces", "nodes"):
        if top["system.json"]["spec"][key] != mae["system.json"]["spec"][key]:
            diff.append(f"system.{key}")
    ext_t = {k: v for k, v in top["system.json"]["extensions"][T.EXT].items() if k not in ("form", "unplannedFlows")}
    ext_m = {k: v for k, v in mae["system.json"]["extensions"][T.EXT].items() if k not in ("form", "unplannedFlows")}
    if ext_t != ext_m:
        diff.append("system.extension")
    if mae["system.json"]["extensions"][T.EXT].get("unplannedFlows") != sorted(T.flows_of(arm)):
        diff.append("system.extension.unplannedFlows")
    if top["deployment.json"]["spec"]["bindings"] != mae["deployment.json"]["spec"]["bindings"]:
        diff.append("deployment.bindings")
    unit_targets = [t for t in top["deployment.json"]["spec"]["targets"] if not t["id"].endswith("-provider")]
    if unit_targets != mae["deployment.json"]["spec"]["targets"]:
        diff.append("deployment.targets")
    if top["scenario.json"]["spec"]["steps"] != mae["scenario.json"]["spec"]["steps"]:
        diff.append("scenario.steps")
    components = sorted(n for n in top if n.startswith("component-"))
    if components != sorted(n for n in mae if n.startswith("component-")) or any(top[n] != mae[n] for n in components):
        diff.append("components")
    return diff


EVERY_ONE = [{"id": "every", "valueType": "integer", "value": 1, "unitSemantics": "count"}]  # structural probe parameter


def fault(arm: str, fault_id: str, kind: str, element: str, at: float, duration: int, *, unit: str = "tick",
          domain: str = "experiment-time", recovery: str = "automatic", parameters: list | None = None) -> dict[str, Any]:
    """Return one Scenario fault with its fault-intent payload (the Phase 5 fixture shape)."""

    name = f"{T._system_name(arm)}-scenario"
    return {"id": fault_id, "targetRef": T._ref("System", T._system_name(arm), element), "faultKind": kind,
            "activation": "scheduled", "recovery": recovery, "maturity": "prototype",
            "extensions": {T.EXPERIMENT: {"schemaVersion": "0.1", "kind": "fault-intent", "target": T._ref("Scenario", name, fault_id),
                                          "trigger": {"kind": "time", "at": at, "unit": unit},
                                          "duration": {"value": duration, "unit": "tick"}, "parameters": parameters or [],
                                          "timeDomainId": domain}}}


# --------------------------------------------------------------------------------------------------
# Maestro (offline) helpers
# --------------------------------------------------------------------------------------------------

def _pin(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


SYNTHETIC_HELPER_PIN = _pin(b"assured-aeb-wp12-synthetic-helper")


def prepare(validation, result, horizon: int = T.HORIZON):
    from xverse.maestro.projection import Limits, ProviderDescriptor, prepare_lifecycle

    return prepare_lifecycle(result, validation.resources,
                             provider_descriptors=(ProviderDescriptor(T.PROVIDER["id"], T.PROVIDER["kind"], SYNTHETIC_HELPER_PIN,
                                                                      T.ENVIRONMENT_ID),),
                             limits=Limits(horizon_ticks=horizon))


def admit(prepared, op: float):
    from xverse.maestro.providers import ProbePolicy
    from xverse.maestro.schedule_plan import admit_schedule

    return admit_schedule(prepared, policies=tuple(ProbePolicy(u.unit_id, LIVE["freshness"], LIVE["cadence"], LIVE["readiness"])
                                                   for u in prepared.units),
                          ticks=tuple(range(LIVE["horizon"] + 1)), active_seconds=LIVE["active"], operation_seconds=op,
                          service_operation_count=LIVE["service"], per_unit_seconds=LIVE["perUnit"], poll_seconds=LIVE["poll"],
                          request_limit=LIVE["requestLimit"], event_limit=LIVE["eventLimit"], use_action_timeouts=True)


def configuration_bytes(prepared, result, resources, schedule, work: Path) -> int:
    """Encode the persistence configuration offline, as the platform bench does, and return its private size."""

    from xverse.maestro.admission import PermitApproval, PermitBinding, permit_digest
    from xverse.maestro.artifacts import ArtifactDeclaration
    from xverse.maestro.collection_plan import admit_collection
    from xverse.maestro.coverage import ArtifactExpectation, admit_coverage
    from xverse.maestro.persistence import encode_configuration
    from xverse.maestro.public_blobs import admit_broker_artifact
    from xverse.maestro.time import HostDeadline
    from xverse_xdl.lifecycle import ExecutionPermit

    run_id, session = "assured-aeb-dry-run", "host-session"
    now = datetime.now(timezone.utc)
    bindings, approvals = [], []
    for index, unit in enumerate(prepared.units):
        plan = unit.plan
        permit = ExecutionPermit(
            permit_id=f"dry-permit-{index}", nonce=f"dry-nonce-{index}-{time.time_ns()}", plan_digest=plan.digest,
            catalog_identity=plan.catalog_identity, environment_identity=plan.environment_identity,
            permitted_actions=tuple(a.action_id for a in plan.actions), approval_evidence_ref="urn:xverse:assured-aeb:wp12:dry-run",
            issuer_label="wp12-offline-dry-run", operation_classes=tuple(sorted({a.operation for a in plan.actions})),
            exclusions=("legacy-execution",), public_safety_classification="public-safe", not_before=now - timedelta(seconds=30),
            expires_at=now + timedelta(seconds=300))
        binding = PermitBinding(unit.unit_id, f"dry-execution-{index}", 1, permit)
        bindings.append(binding)
        approvals.append(PermitApproval(permit.approval_evidence_ref, permit.issuer_label, run_id, unit.unit_id, binding.execution_id, 1,
                                        prepared.lifecycle_digest, plan.digest, unit.provider.provider_id, unit.provider.kind,
                                        SYNTHETIC_HELPER_PIN, plan.environment_identity, plan.artifact_digests, permit_digest(permit),
                                        now - timedelta(seconds=30), now + timedelta(seconds=300)))
    declarations = tuple(ArtifactDeclaration(u.unit_id, 1, u.binding_id + ".marker", "outputs/" + u.binding_id + ".txt")
                         for u in prepared.units)
    start = time.monotonic()
    coverage = admit_coverage(prepared, result, resources, run_id=run_id, host_session=session,
                              contexts=[(b.unit_id, b.generation, b.execution_id) for b in bindings],
                              health_policies={p.unit_id: (p.cadence_seconds, p.freshness_seconds) for p in schedule.policies},
                              active_start=start, active_end=start + schedule.active_seconds,
                              source_digests=(_pin(schedule.canonical_bytes),),
                              artifacts=[*(ArtifactExpectation(d.destination, True, 256, d.unit_id, 1) for d in declarations),
                                         ArtifactExpectation("collection-result.json", maximum_bytes=16384),
                                         ArtifactExpectation("retained-inputs.json", maximum_bytes=4 * 1024 * 1024)])
    st = work.stat()
    collection = admit_collection(coverage, expected_digest=coverage.digest, source_root=str(work), source_identity=(st.st_dev, st.st_ino),
                                  declarations=declarations, metadata_path="collection-result.json", operation_seconds=1,
                                  per_unit_teardown_seconds=2, collection_seconds=3, terminal_seconds=2, drain_seconds=2)
    config = encode_configuration(prepared, result, resources, run_id=run_id, bindings=bindings, approvals=approvals, session=session,
                                  generation_deadline=HostDeadline(session, time.monotonic() + 300), journal_path=work / "m3.jsonl",
                                  evidence_root=work / "argus-maestro", schedule=schedule, coverage=coverage, collection=collection,
                                  broker_artifact=admit_broker_artifact(coverage, expected_digest=coverage.digest))
    return len(config.private_bytes)


# --------------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------------

def check_drift(report: Report) -> None:
    pins = T.read_pins()
    for arm in T.ARMS:
        for form in T.FORMS:
            expected = {n: json.loads(json.dumps(d)) for n, d in T.documents(arm, pins, form=form).items()}
            report.add("drift", load(arm, form) == expected, arm=arm, form=form)
    host = {}
    try:
        host = T.host_pins()
    except OSError as error:  # an interpreter is absent on this host: reported, not a failure
        host = {"error": str(error)}
    report.add("pins", True, recorded=pins, host=host, drift=host != pins,
               note="interpreter digest drift is a host observation, not a topology failure")


def expected_elements(arm: str) -> dict[str, Any]:
    return {"units": sorted(T.uid(u) for u in T.units_of(arm)), "elements": sorted(T.elements_of(arm)),
            "flows": sorted(T.flows_of(arm))}


def check_v01(report: Report, schema_paths: tuple[str, ...]) -> dict[tuple[str, str], Any]:
    compiled = {}
    for arm in T.ARMS:
        for form in T.FORMS:
            docs = load(arm, form)
            validation, result = compile_docs(docs, schema_paths)
            ok = validation.is_valid and result is not None and result.is_valid
            detail: dict[str, Any] = {"arm": arm, "form": form, "valid": validation.is_valid,
                                      "diagnostics": _diag(validation.diagnostics if result is None else result.diagnostics)}
            if ok:
                _, again = compile_docs(docs, schema_paths)
                detail["planDigest"] = result.plan["digest"]["value"]
                detail["deterministic"] = again.plan["digest"]["value"] == detail["planDigest"]
                ok = detail["deterministic"]
                compiled[(arm, form)] = (docs, validation, result)
            report.add("v01-compile", ok, **detail)
        docs = load(arm, "topology")
        spec, ext = docs["system.json"]["spec"], docs["system.json"]["extensions"][T.EXT]
        want = expected_elements(arm)
        instances = {i["id"] for i in spec["componentInstances"]}
        declared_flows = {f["id"] for f in spec.get("flows", [])} | {f["id"] for f in ext["returnFlows"]}
        owner = {e["id"]: e["ownerId"] for e in spec["endpoints"]}
        radar = {f["id"]: (owner[f["sourceEndpointId"]], owner[f["destinationEndpointIds"][0]]) for f in spec["flows"]
                 if f["interfaceId"] == "radar-evidence"}
        ivi_endpoints = [e for e in spec["endpoints"] if e["ownerId"] == "ivi-hpc"]
        problems = []
        if instances != set(want["units"]) | set(want["elements"]):
            problems.append({"instances": sorted(instances ^ (set(want["units"]) | set(want["elements"])))})
        if declared_flows != set(want["flows"]):
            problems.append({"flows": sorted(declared_flows ^ set(want["flows"]))})
        if radar != {"f08-radar-adas": ("front-zone", "fusion-risk-aeb"), "f09-radar-vc": ("front-zone", "vc-ingress")}:
            problems.append({"radar": radar})
        fan = {(m["consumer"], m["interface"]) for m in messages(docs) if m["producer"] == "vc-ingress"}
        if not {("radar-fallback", "radar-evidence"), ("evidence-validator", "radar-evidence"),
                ("functional-arbiter", "adas-cycle"), ("evidence-validator", "adas-cycle")} <= fan:
            problems.append({"vc-ingress-fan-out": sorted(fan)})
        if "ivi-hpc" not in {n["id"] for n in spec["nodes"]} or ivi_endpoints:
            problems.append({"ivi": "missing node or endpoints present"})
        forbidden = [i for i in instances if any(word in i for word in ("legacy", "vcu", "stimulus", "observer", "oracle"))]
        if forbidden:
            problems.append({"excluded-present": forbidden})
        report.add("v01-elements", not problems, arm=arm, units=want["units"], elementCount=len(want["elements"]),
                   forwardFlows=len(spec.get("flows", [])), returnFlows=len(ext["returnFlows"]),
                   intraMessages=len(ext["intraUnitMessages"]), problems=problems)
    return compiled


def check_v02(report: Report) -> None:
    for arm in T.ARMS:
        violations = check_authority(load(arm, "topology"), arm)
        report.add("v02-authority", not violations, arm=arm, violations=violations)


def check_routes(report: Report, compiled) -> None:
    from xverse.flows.binding import bind

    for arm in T.ARMS:
        docs, validation, result = compiled[(arm, "topology")]
        plan = plain_plan(result)
        keys = {(e["kind"], e["name"]) for e in plan["provenance"]["resources"]}
        contributors = tuple(r for r in validation.resources if (r.identity.kind, r.identity.name) in keys)
        record = bind(plan, contributors)
        per_provider: dict[str, list[str]] = {}
        for item in record.bindings:
            per_provider.setdefault(item.provider_id, []).append(item.flow_id)
        unexpected, residuals = [], []
        for refusal in record.refusals:
            key = ("routes", arm, refusal.get("flowId"))
            (residuals if key in EXPECTED_RESIDUALS else unexpected).append(
                dict(refusal, residual=EXPECTED_RESIDUALS.get(key)))
        within_cap = all(len(v) <= 4 for v in per_provider.values())
        returns = {}
        for row in docs["system.json"]["extensions"][T.EXT]["returnFlows"]:
            returns.setdefault(row["networkId"], []).append(row["id"])
        report.add("d4a-routes", within_cap and not unexpected and record.xcom_plan_error is None, arm=arm,
                   xcomPlanStatus=record.xcom_plan_status, xcomDiagnostics=[dict(d) for d in record.xcom_plan_diagnostics],
                   routesPerProvider={k: sorted(v) for k, v in sorted(per_provider.items())},
                   hubBoundReturnFlows=returns, refusals=unexpected, expectedResiduals=residuals)


def check_unbound(report: Report, compiled) -> None:
    for arm in T.ARMS:
        docs, validation, result = compiled[(arm, "maestro")]
        try:
            prepared = prepare(validation, result)
            units = sorted(u.unit_id.rsplit("/", 1)[-1] for u in prepared.units)
            want = sorted(T.uid(u) for u in T.units_of(arm))
            elements = len(T.elements_of(arm))
            report.add("d4a-unbound-instances", units == want, arm=arm, units=units, unboundElementInstances=elements)
        except Exception as error:  # the platform refusal is the finding
            report.add("d4a-unbound-instances", False, arm=arm, error=f"{type(error).__name__}: {error}")
        try:
            prepare(*compiled[(arm, "topology")][1:])
            report.add("d4a-topology-form-maestro", False, arm=arm,
                       note="the topology form became preparable: L-1 no longer holds; revisit the two-form projection")
        except Exception as error:
            text = f"{type(error).__name__}: {error}"
            report.add("d4a-topology-form-maestro", "ML-TIME" in text, arm=arm, expectedRefusal=text,
                       note="expected: Maestro Lite admits exactly one time domain (L-1); any other refusal fails")
        difference = forms_difference(arm)
        report.add("forms-equal", not difference, arm=arm, differences=difference)
        cycles = check_cycles(load(arm, "topology"))
        report.add("cycles-broken", not cycles["crossUnitCycles"], arm=arm, **cycles)


def _prepare_with_faults(arm: str, faults: list[dict[str, Any]], schema_paths, form: str = "maestro"):
    docs = T.documents(arm, T.read_pins(), form=form, faults=faults)
    validation, result = compile_docs(docs, schema_paths)
    if result is None or not result.is_valid:
        return docs, None, _diag(validation.diagnostics if result is None else result.diagnostics)
    try:
        return docs, prepare(validation, result), None
    except Exception as error:
        return docs, None, f"{type(error).__name__}: {error}"


def _static_message_fault(arm: str, entry: dict[str, Any], schema_paths) -> Any:
    """Message faults need the topology form (flows), which Maestro cannot prepare; check them with validate_static."""

    from xverse.faults import FaultError, validate_static

    docs = T.documents(arm, T.read_pins(), form="topology", faults=[entry])
    validation, result = compile_docs(docs, schema_paths)
    if result is None or not result.is_valid:
        return _diag(validation.diagnostics if result is None else result.diagnostics)
    try:
        validate_static(plain_plan(result), T.HORIZON)
        return "admitted by validate_static"
    except FaultError as error:
        return error.code


def check_faults(report: Report, schema_paths) -> None:
    arm = "mloc"
    cc1 = [fault(arm, "cc1-freeze-functional", "freeze", T.uid("vc-functional"), 100, 10),
           fault(arm, "cc1-freeze-assurance", "freeze", T.uid("vc-assurance"), 100, 10)]
    docs, prepared, error = _prepare_with_faults(arm, cc1, schema_paths)
    blueprint = check_fault_admission(load(arm, "topology"), cc1)
    report.add("d4a-cc1-concurrent-freeze", prepared is not None and not blueprint, arm=arm, platform=error or "admitted",
               blueprintRefusals=blueprint, faultEntries=len(prepared.faults) if prepared is not None else None,
               note="probe tick 100 and duration 10 are structural probe values, not protocol values")
    probes = {
        "freeze-adapter": fault(arm, "probe-freeze-adapter", "freeze", T.uid("carla-adapter"), 100, 10),
        "freeze-vehicle-loop": fault(arm, "probe-freeze-loop", "freeze", T.uid("vehicle-loop"), 100, 10),
        "freeze-element": fault(arm, "probe-freeze-element", "freeze", "safety-gate", 100, 10),
        "crash-unit": fault(arm, "probe-crash", "crash", T.uid("adas-hpc"), 100, 10, recovery="manual"),
        "loss-on-f07": fault(arm, "probe-loss-f07", "loss", "f07-camera-adas", 100, 10, parameters=EVERY_ONE),
        "stale-on-f09": fault(arm, "probe-stale-f09", "stale", "f09-radar-vc", 100, 10),
    }
    probes["lone-vc-functional"] = fault(arm, "probe-lone-vcf", "freeze", T.uid("vc-functional"), 100, 10)
    probes["non-concurrent-pair"] = None  # two entries; checked as a pair below
    expected_refused = {"freeze-adapter", "freeze-vehicle-loop", "freeze-element", "crash-unit", "loss-on-f07",
                        "lone-vc-functional", "non-concurrent-pair"}
    rows, ok = {}, True
    for name, entry in probes.items():
        if entry is None:  # the CC-1 pair at different onsets
            pair = [fault(arm, "probe-pair-a", "freeze", T.uid("vc-functional"), 100, 10),
                    fault(arm, "probe-pair-b", "freeze", T.uid("vc-assurance"), 300, 10)]
            refusals = check_fault_admission(load(arm, "topology"), pair)
            rows[name] = {"blueprint": refusals or "admitted", "platform": "not run (a pair)"}
            ok &= bool(refusals)
            continue
        refusals = check_fault_admission(load(arm, "topology"), [entry])
        if entry["faultKind"] in ("loss", "stale"):
            platform = _static_message_fault(arm, entry, schema_paths)
        else:
            _, platform_prepared, platform_error = _prepare_with_faults(arm, [entry], schema_paths)
            platform = "admitted by prepare_lifecycle" if platform_prepared is not None else platform_error
        rows[name] = {"blueprint": refusals or "admitted", "platform": platform}
        ok &= bool(refusals) == (name in expected_refused)
    report.add("d4a-freeze-target-rule", ok, arm=arm, probes=rows,
               durationBound="not applied here: FreezeBound needs the admitted schedule's thaw bound and the measured "
                             "maximum dispatcher cycle (D-4c); WP-10/WP-16 pass it to check_fault_admission",
               note="the blueprint rule must refuse what the platform admits statically (an element instance, a never-frozen unit)")
    # WP-10 feasibility probe: a fault keyed to simulator time (informational).
    sim = fault(arm, "probe-sim-time", "stale", "f09-radar-vc", 1.5, 10, unit="s", domain="carla-simulation")
    sim_docs = T.documents(arm, T.read_pins(), form="topology", faults=[sim])
    validation, result = compile_docs(sim_docs, schema_paths)
    outcome = ("compiled" if result is not None and result.is_valid else
               _diag(validation.diagnostics if result is None else result.diagnostics))
    schedule, static = None, None
    if result is not None and result.is_valid:
        from xverse.faults import FaultError, validate_static

        schedule = [dict(e) for e in plain_plan(result).get("faultSchedule", [])]
        try:
            validate_static(plain_plan(result), T.HORIZON)
            static = "admitted by validate_static"
        except FaultError as error:
            static = error.code
    report.add("wp10-sim-time-fault-probe", True, arm=arm, outcome=outcome, compiledSchedule=schedule, validateStatic=static,
               note="informational for WP-10: only the Maestro form is preparable, and it has one experiment-time domain")


def slim(docs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Sizing alternative only: the Maestro form without element instances, element Components, endpoints and the
    blueprint System extension (the unit allocation would then live outside the Maestro plan)."""

    out = {n: copy.deepcopy(d) for n, d in docs.items() if not (n.startswith("component-") and n != "component-unit-host.json")}
    spec = out["system.json"]["spec"]
    spec["componentInstances"] = [i for i in spec["componentInstances"] if i["extensions"][T.EXT]["kind"] == "unit-host"]
    for inst in spec["componentInstances"]:
        del inst["extensions"]
    spec["endpoints"], spec["interfaces"] = [], []
    del out["system.json"]["extensions"]
    return out


def check_admission(report: Report, schema_paths) -> None:
    rows = []
    for (n, arm), variant in [((n, a), v) for n, a in UNIT_COUNTS.items() for v in ("full", "slim")]:
        docs = T.documents(arm, T.read_pins(), form="maestro")
        if variant == "slim":
            docs = slim(docs)
        validation, result = compile_docs(docs, schema_paths)
        prepared = prepare(validation, result)
        for op in OPERATION_BUDGETS:
            if variant == "slim" and op != 0.29 and not (n == 7 and op == 0.25):
                continue
            row: dict[str, Any] = {"units": n, "arm": arm, "maestroForm": variant, "operationSeconds": op,
                                   "capacityRule": (2 * n + LIVE["service"] + 1) * op < LIVE["cadence"]}
            try:
                schedule = admit(prepared, op)
                row.update(admitted=True, periodS=round(LIVE["cadence"] - schedule.health_scan_seconds - (LIVE["service"] + 1) * op, 4),
                           scanS=round(schedule.health_scan_seconds, 4), reserveS=round(schedule.terminal_reserve_seconds, 4),
                           thawBoundS=round(LIVE["cadence"] - schedule.health_scan_seconds, 4),
                           requiredRequests=schedule.required_requests, requiredEvents=schedule.required_events,
                           healthSlots=schedule.health_slots)
                with tempfile.TemporaryDirectory(prefix="assured-aeb-wp12-") as work:
                    size = configuration_bytes(prepared, result, validation.resources, schedule, Path(work))
                row.update(configurationBytes=size, withinPersistenceLimit=size <= PERSISTENCE_LIMIT)
                if size > PERSISTENCE_LIMIT:
                    row["residual"] = "expected C1 dependency: the 64 KiB persistence-configuration limit refuses this size"
            except Exception as error:
                row.update(admitted=False, refusal=getattr(error, "args", [str(error)])[0])
            rows.append(row)
    agree = all(r["capacityRule"] == r["admitted"] for r in rows)
    report.add("d4a-admission-dry-run", agree, rows=rows, live=LIVE,
               note="pass = admit_schedule agrees with (2n+S+1)*op < cadence; sizes above 65 536 are the C1 dependency; "
                    "'slim' is a sizing alternative only, not a committed form")


def platform_identity() -> dict[str, Any]:
    import xverse
    import xverse_xdl

    identity = {"xverse": str(Path(xverse.__file__).parent), "xverse_xdl": str(Path(xverse_xdl.__file__).parent)}
    for info in Path(xverse_xdl.__file__).parent.parent.glob("xverse_xdl-*.dist-info/direct_url.json"):
        identity["wheel"] = json.loads(info.read_text()).get("archive_info", {}).get("hash")
    return identity


def run(profile_dir: Path) -> Report:
    report = Report()
    schema_paths = schemas(profile_dir)
    report.add("platform", True, **platform_identity(), profiles=str(profile_dir))
    check_drift(report)
    compiled = check_v01(report, schema_paths)
    check_v02(report)
    if all((arm, form) in compiled for arm in T.ARMS for form in T.FORMS):
        check_routes(report, compiled)
        check_unbound(report, compiled)
        check_faults(report, schema_paths)
        check_admission(report, schema_paths)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline WP-12 topology check (no run, no simulator).")
    parser.add_argument("--platform-profiles", type=Path, default=os.environ.get("XVERSE_PLATFORM_PROFILES"),
                        help="directory of the platform profile schemas (xdl/profiles of the rc.1 export)")
    parser.add_argument("--report", type=Path, help="write the JSON report here")
    args = parser.parse_args()
    if args.platform_profiles is None:
        parser.error("--platform-profiles or XVERSE_PLATFORM_PROFILES is required")
    report = run(Path(args.platform_profiles))
    text = json.dumps({"ok": report.ok, "checks": report.checks}, indent=2, sort_keys=True, default=str)
    if args.report:
        args.report.write_text(text + "\n")
    for check in report.checks:
        print(f"{'PASS' if check['ok'] else 'FAIL'} {check['check']} {check.get('arm', '')} {check.get('form', '')}".rstrip())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
