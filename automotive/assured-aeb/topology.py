"""Assured AEB blueprint (Phase 8, WP-12): single-source topology and XDL document generator.

Declares the bounded zonal AEB topology of thesis design record ``wp12-xdl-topology.md`` (decided under
the author's delegation, ``decisions.md`` §J and §K) and emits, per arm, one XDL v1alpha1 document set in each of two forms (``FORMS``):

- ``comparator``: the competent fixed comparator, on units U1 to U5;
- ``mloc``: the MLOC assurance extension, on units U1 to U6;
- ``authorization-bypass`` and ``verification-bypass``: the two targeted ablations, on U1 to U6.

Shape S-A: each Maestro unit is a *bound* instance of ``assured-aeb-unit-host``; each Note 21 element or
role is an *unbound* instance of its own Component, placed by ``hostUnit`` in the blueprint extension
``io.xverse.assured-aeb``. Authority is declared per Component (``authorityClass``, ``permittedOutputs``).

No protocol value is written. XDL v1alpha1 has no placeholder mechanism, so every latency, freshness,
deadline and window value is the string ``"TODO: ..."`` inside the blueprint extension, and flow
``quality`` is omitted. Engineering parameters that the platform needs for compilation come from
accepted sources and are labelled in ``ENGINEERING_SOURCES``.

Usage: ``python topology.py --write`` regenerates ``xdl/<arm>/<form>/`` (forms ``topology`` and ``maestro``) and
``xdl/pins.json``.
Engineering design only: no unit program exists yet (WP-13 to WP-17), and nothing here runs one.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
XDL = HERE / "xdl"
API = "xverse.io/xdl/v1alpha1"
NAMESPACE = "org.xverse.assured-aeb"
EXT = "io.xverse.assured-aeb"
XCOM = "io.xverse.xcom"
EXPERIMENT = "io.xverse.experiment"
RUNTIME = "io.xverse.runtime.compatibility"
SCHEMA_REF = "https://xverse.io/profiles/assured-aeb/v0.1/schema.json"

ARMS = ("comparator", "mloc", "authorization-bypass", "verification-bypass")
#: Two document forms per arm, from one source (finding 2):
#: - ``topology``: the full declaration (both time domains, every forward flow, networks and providers). It compiles
#:   with XDL and binds with the Phase 6 flow layer, but Maestro Lite cannot prepare it: ``prepare_lifecycle`` admits
#:   exactly one time domain (projection.py 274-276), and the plan lists every declared System domain.
#: - ``maestro``: the Maestro projection: one ``experiment-time`` domain, units and element instances, no flows. The
#:   flows and the ``carla-simulation`` domain are bound by the vehicle-loop hub, as the Phase 7 loop binds its runtime
#:   flows (review R-5).
FORMS = ("topology", "maestro")
MLOC_ARMS = ("mloc", "authorization-bypass", "verification-bypass")
ALL = ARMS
VARIANT_7 = "mloc-7unit"  # admission dry-run variant only (WP-11 §4.2); never committed as an arm

#: Engineering parameters required by the platform, with their accepted source. None is a protocol value.
ENGINEERING_SOURCES = {
    "actionTimeoutSeconds": "Phase 7 blueprint test_live_closed_loop.py 184 (5 s is the platform cap)",
    "stopGraceSeconds": "S1b, Phase 7 blueprint test_live_closed_loop.py 97",
    "stderrMaximumBytes": "S1b, Phase 7 blueprint test_live_closed_loop.py 98",
    "flowPolicy": "Phase 6 fixture FLOW_POLICY (tests/thesis_lite/flows/support.py 30-31)",
    "horizonTicks": "S1 accepted engineering long-run capacity S-D1 (600 Maestro ticks); protocol horizon TODO (AD-25)",
    "observeTick": "Phase 7 blueprint OBSERVE_TICK (test_live_closed_loop.py 79)",
    "scenarioSeed": "structural placeholder 0: the experiment profile requires an integer; seed lists TODO (P-4)",
}
ACTION_TIMEOUTS = {"prepare": 2, "start": 5, "observe": 4, "stop": 5, "cleanup": 5}
STOP_GRACE_S = 0.6
STDERR = {"capture": "run-scoped-private", "maximumBytes": 256 * 1024}
FLOW_POLICY = {"ordering": "fifo", "reliability": "best-effort", "deadlineMs": 0, "retry": 0, "queueDepth": 4,
               "overflow": "reject", "observationPoints": []}
HORIZON = 600
OBSERVE_TICK = 24
PY310 = "/usr/bin/python3.10"
PY313 = "/home/jefferson/.pyenv/versions/3.13.13/bin/python3.13"
ENVIRONMENT_ID = "assured-aeb-owned"
UNMAPPED = "unmapped:frames-per-tick-measured-per-run"
PROVIDER = {"id": "maestro-process-v1", "kind": "process"}


def uid(unit: str) -> str:
    """System element id of a unit instance (ids are unique across all System collections)."""

    return f"{unit}-unit"


def todo(kind: str, ref: str) -> str:
    """Return the declared TODO string (the only representation of an undecided value)."""

    return f"TODO: {kind} ({ref})"


# --------------------------------------------------------------------------------------------------
# Units (WP-11 §4.1; decisions.md §J)
# --------------------------------------------------------------------------------------------------

#: unit id -> (node, interpreter artifact, unit class, arms)
UNITS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "carla-adapter": ("simulation-environment", "python310", "environment", ALL),
    "vehicle-loop": ("simulation-environment", "python313", "experiment-control", ALL),
    "front-zone": ("front-zone-ecu", "python313", "runtime", ALL),
    "adas-hpc": ("adas-hpc", "python313", "runtime", ALL),
    "vc-functional": ("vehicle-control-hpc", "python313", "runtime", ALL),
    "vc-assurance": ("vehicle-control-hpc", "python313", "runtime", MLOC_ARMS),
}
UNIT_7 = ("chassis-brake", ("chassis-zone-ecu", "python313", "runtime", (VARIANT_7,)))
#: Start order (design §9): U2 listens first, then U1, then the runtime units.
START_ORDER = ("vehicle-loop", "carla-adapter", "front-zone", "vc-functional", "chassis-brake", "vc-assurance", "adas-hpc")

NODES = {
    "forward-camera": ["smart-sensor"], "forward-radar": ["smart-sensor"], "front-zone-ecu": ["zonal-ecu"],
    "adas-hpc": ["hpc"], "vehicle-control-hpc": ["hpc"], "chassis-zone-ecu": ["zonal-ecu"],
    "brake-esc-ecu": ["legacy-ecu-model"], "ivi-hpc": ["context"], "simulation-environment": ["environment"],
}

# --------------------------------------------------------------------------------------------------
# Elements: id -> (authority class, host unit, node, arms, output interfaces)
# --------------------------------------------------------------------------------------------------

ELEMENTS: dict[str, tuple[str, str, str, tuple[str, ...], tuple[str, ...]]] = {
    # U1 environment
    "carla-client": ("environment", "carla-adapter", "simulation-environment", ALL, ("camera-raw", "radar-raw", "motion-raw")),
    # U2 environment and experiment control
    "loop-gateway": ("environment", "vehicle-loop", "simulation-environment", ALL,
                     ("actuation-command", "radar-sensor-out", "motion-raw")),
    "fault-relay": ("experiment-control", "vehicle-loop", "simulation-environment", ALL, ("proposal",)),
    "camera-imaging-stage": ("environment", "vehicle-loop", "forward-camera", ALL, ("camera-sensor-out",)),
    "motion-sensor-model": ("environment", "vehicle-loop", "chassis-zone-ecu", ALL, ("motion-evidence",)),
    "driver-profile": ("environment", "vehicle-loop", "simulation-environment", ALL, ("throttle-command",)),
    "objective-source": ("environment", "vehicle-loop", "simulation-environment", MLOC_ARMS, ("objective",)),
    "mrc-sink": ("sink", "vehicle-loop", "simulation-environment", ALL, ()),
    # U3 front zone
    "front-zone": ("evidence-router", "front-zone", "front-zone-ecu", ALL, ("camera-evidence", "radar-evidence")),
    "smart-camera": ("evidence-source", "front-zone", "forward-camera", ALL, ("smart-camera-evidence",)),
    "smart-radar": ("evidence-source", "front-zone", "forward-radar", ALL, ("smart-radar-evidence",)),
    # U4 ADAS/AD HPC
    "perception": ("productive", "adas-hpc", "adas-hpc", ALL, ("perception-output",)),
    "fusion-risk-aeb": ("productive", "adas-hpc", "adas-hpc", ALL, ("adas-cycle", "proposal-basis")),
    "proposer": ("proposer", "adas-hpc", "adas-hpc", MLOC_ARMS, ("proposal",)),
    "goal-interpreter": ("goal-interpreter", "adas-hpc", "adas-hpc", MLOC_ARMS, ("goal-model",)),
    # U5 Vehicle Control functional (with the chassis zone and brake node, CC-2c)
    "evidence-validator": ("productive", "vc-functional", "vehicle-control-hpc", ALL, ("qualified-evidence",)),
    "functional-arbiter": ("productive", "vc-functional", "vehicle-control-hpc", ALL, ("brake-request",)),
    "radar-fallback": ("productive", "vc-functional", "vehicle-control-hpc", ALL, ("fallback-request",)),
    "vehicle-state": ("productive", "vc-functional", "vehicle-control-hpc", ALL, ("vehicle-state-record",)),
    "diagnostics-supervision": ("productive", "vc-functional", "vehicle-control-hpc", ALL, ("diagnostic-verdict",)),
    "fixed-fallback-supervisor": ("fallback-supervisor", "vc-functional", "vehicle-control-hpc", ALL,
                                  ("forced-command", "aeb-status", "mrc-request")),
    "configuration-manager": ("executor", "vc-functional", "vehicle-control-hpc", ALL,
                              ("selector-command", "transition-request", "configuration-state")),
    "transition-verifier": ("verifier", "vc-functional", "vehicle-control-hpc", ALL, ("transition-verdict",)),
    "chassis-zone": ("actuation-path", "vc-functional", "chassis-zone-ecu", ALL, ("brake-request", "motion-evidence")),
    "brake-esc-node": ("actuation-path", "vc-functional", "brake-esc-ecu", ALL, ("brake-command", "brake-status")),
    # U6 Vehicle Control assurance (MLOC configuration and ablations only)
    "safety-monitor": ("assessor", "vc-assurance", "vehicle-control-hpc", MLOC_ARMS, ("assessment",)),
    "safety-gate": ("gate", "vc-assurance", "vehicle-control-hpc", MLOC_ARMS, ("authorization",)),
}

#: Interfaces: id -> unit semantics. payloadSchema is urn:xverse:assured-aeb:<id>:v1 (contract in WP-13/WP-14).
INTERFACES = {
    "camera-raw": "camera-frame-metadata", "radar-raw": "radar-detections", "motion-raw": "vehicle-motion",
    "actuation-command": "pedal-command", "throttle-command": "pedal-command",
    "camera-sensor-out": "camera-frame-metadata", "radar-sensor-out": "radar-detections",
    "smart-camera-evidence": "evidence-item", "smart-radar-evidence": "evidence-item",
    "camera-evidence": "evidence-item", "radar-evidence": "evidence-item", "motion-evidence": "evidence-item",
    "perception-output": "evidence-item", "adas-cycle": "evidence-item", "proposal-basis": "evidence-item",
    "proposal": "typed-proposal", "goal-model": "typed-objective", "objective": "typed-objective",
    "qualified-evidence": "evidence-item", "diagnostic-verdict": "verdict",
    "fallback-request": "brake-request", "brake-request": "brake-request", "brake-command": "brake-request",
    "brake-status": "node-status", "forced-command": "configuration-command", "selector-command": "configuration-command",
    "transition-request": "configuration-command", "transition-verdict": "verdict", "configuration-state": "configuration-state",
    "aeb-status": "node-status", "vehicle-state-record": "evidence-item", "mrc-request": "mrc-request", "assessment": "verdict", "authorization": "authorization",
}

#: Inter-unit flows (design §4): id -> (producer element, interface, consumer element, network, AD-30 latency kind, arms)
FLOWS: dict[str, tuple[str, str, str, str, str, tuple[str, ...]]] = {
    "f01-camera-raw": ("carla-client", "camera-raw", "camera-imaging-stage", "net-adapter-link", "none", ALL),
    "f02-radar-raw": ("carla-client", "radar-raw", "loop-gateway", "net-adapter-link", "none", ALL),
    "f03-motion-raw": ("carla-client", "motion-raw", "loop-gateway", "net-adapter-link", "none", ALL),
    "f04-actuation-command": ("loop-gateway", "actuation-command", "carla-client", "net-adapter-link", "actuation", ALL),
    "f05-camera-sensor-out": ("camera-imaging-stage", "camera-sensor-out", "smart-camera", "net-u3", "sensor-sampling", ALL),
    "f06-radar-sensor-out": ("loop-gateway", "radar-sensor-out", "smart-radar", "net-u3", "sensor-sampling", ALL),
    "f07-camera-adas": ("front-zone", "camera-evidence", "perception", "net-u4", "network", ALL),
    "f08-radar-adas": ("front-zone", "radar-evidence", "fusion-risk-aeb", "net-u4", "network", ALL),
    "f09-radar-vc": ("front-zone", "radar-evidence", "evidence-validator", "net-u5", "network", ALL),
    "f10-motion-chassis": ("motion-sensor-model", "motion-evidence", "chassis-zone", "net-u5", "sensor-sampling", ALL),
    "f11-adas-cycle": ("fusion-risk-aeb", "adas-cycle", "evidence-validator", "net-u5", "compute-and-network", ALL),
    "f12-proposal": ("proposer", "proposal", "safety-gate", "net-u6", "compute-and-network", MLOC_ARMS),
    "f13-qualified-evidence": ("evidence-validator", "qualified-evidence", "safety-monitor", "net-u6", "network", MLOC_ARMS),
    "f14-authorization": ("safety-gate", "authorization", "configuration-manager", "net-u5", "network", MLOC_ARMS),
    "f15a-configuration-state-assurance": ("configuration-manager", "configuration-state", "safety-monitor", "net-u6", "network",
                                           MLOC_ARMS),
    "f15b-configuration-state-proposer": ("configuration-manager", "configuration-state", "proposer", "net-u4", "network",
                                          MLOC_ARMS),
    "f16-objective": ("objective-source", "objective", "goal-interpreter", "net-u4", "network", MLOC_ARMS),
    "f17-brake-command": ("brake-esc-node", "brake-command", "loop-gateway", "net-u2-returns", "actuation", ALL),
    "f18-mrc-request": ("fixed-fallback-supervisor", "mrc-request", "mrc-sink", "net-u2-returns", "network", ALL),
    # The one inadmissible proposal of the authorization-bypass ablation (FR-020, AD-11). Fifth inbound route of U5:
    # the 4-route cap is resolved in WP-16 (decisions.md §K); left on net-u5 so that the check shows it.
    "f19-bypass-proposal": ("fault-relay", "proposal", "configuration-manager", "net-u5", "network", ("authorization-bypass",)),
}
#: Phase 8 relay admission (decisions.md §K): only these flows may carry scheduled message or assurance faults.
RELAY_ADMITTED = {
    "f09-radar-vc": ["loss", "stale", "delay"],
    "f12-proposal": ["assurance.proposal-unsafe", "assurance.proposal-mistimed"],
    "f13-qualified-evidence": ["assurance.evidence-loss"],
}
ABLATION_EXCEPTIONS = {"f19-bypass-proposal": "authorization-bypass"}
#: XDL Lite orders component instances by their flows and refuses a cycle (XDL1-PLAN-DEPENDENCY-CYCLE,
#: experiment_plan.py 1340-1404). A closed loop therefore cannot be planned as flows only. The minimal set of feedback
#: flows that breaks every cycle is declared as *return flows* in the System extension and bound by the hub directly,
#: as the Phase 7 loop binds its runtime flows (review R-5). Finding 2 records this platform limit.
RETURN_FLOWS = ("f04-actuation-command", "f15b-configuration-state-proposer")

#: Intra-unit messages (design §4), declared in the System extension; never routed through U2.
INTRA: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("loop-gateway", "motion-raw", "motion-sensor-model", ALL),
    ("loop-gateway", "motion-raw", "driver-profile", ALL),
    ("driver-profile", "throttle-command", "loop-gateway", ALL),
    ("smart-camera", "smart-camera-evidence", "front-zone", ALL),
    ("smart-radar", "smart-radar-evidence", "front-zone", ALL),
    ("perception", "perception-output", "fusion-risk-aeb", ALL),
    ("fusion-risk-aeb", "proposal-basis", "proposer", MLOC_ARMS),
    ("goal-interpreter", "goal-model", "proposer", MLOC_ARMS),
    ("chassis-zone", "motion-evidence", "vehicle-state", ALL),
    ("vehicle-state", "vehicle-state-record", "evidence-validator", ALL),
    ("evidence-validator", "qualified-evidence", "functional-arbiter", ALL),
    ("evidence-validator", "qualified-evidence", "radar-fallback", ALL),
    ("evidence-validator", "qualified-evidence", "diagnostics-supervision", ALL),
    ("evidence-validator", "qualified-evidence", "fixed-fallback-supervisor", ALL),
    ("diagnostics-supervision", "diagnostic-verdict", "fixed-fallback-supervisor", ALL),
    ("radar-fallback", "fallback-request", "functional-arbiter", ALL),
    ("fixed-fallback-supervisor", "forced-command", "configuration-manager", ALL),
    ("fixed-fallback-supervisor", "aeb-status", "functional-arbiter", ALL),
    ("fixed-fallback-supervisor", "aeb-status", "chassis-zone", ALL),
    ("configuration-manager", "selector-command", "functional-arbiter", ALL),
    ("configuration-manager", "transition-request", "transition-verifier", ALL),
    ("transition-verifier", "transition-verdict", "configuration-manager", ALL),
    ("configuration-manager", "configuration-state", "fixed-fallback-supervisor", ALL),
    ("functional-arbiter", "brake-request", "chassis-zone", ALL),
    ("chassis-zone", "brake-request", "brake-esc-node", ALL),
    ("brake-esc-node", "brake-status", "chassis-zone", ALL),
    ("safety-monitor", "assessment", "safety-gate", MLOC_ARMS),
)

COMMON_CAUSE = [
    {"id": "cc-1", "kind": "shared-host-node", "members": ["vc-functional", "vc-assurance"],
     "exercise": "declared limit; one characterisation run freezes both units at once (AD-13, AD-20)"},
    {"id": "cc-2a", "kind": "shared-process", "members": ["front-zone"], "exercise": "through CC-3"},
    {"id": "cc-2b", "kind": "shared-process", "members": ["adas-hpc"], "exercise": "freeze of adas-hpc (M-07, AD-12, H4-04)"},
    {"id": "cc-2c", "kind": "shared-process", "members": ["vc-functional"],
     "exercise": "no freeze alone; owned hooks H4-03 and H4-05 (ED-04)"},
    {"id": "cc-2d", "kind": "shared-process", "members": ["vc-assurance"], "exercise": "freeze of vc-assurance (H4-01, H4-08)"},
    {"id": "cc-3", "kind": "shared-zonal-ecu", "members": ["front-zone"], "exercise": "freeze of front-zone (H4-07)"},
]
FREEZE_TARGETS = {"admitted": ["front-zone", "adas-hpc", "vc-assurance"], "admittedSets": [["vc-functional", "vc-assurance"]],
                  "refused": ["carla-adapter", "vehicle-loop"], "refusedKinds": ["crash"],
                  "rule": "process faults target unit instances only; element instances are not units"}
DEGRADED_PATH = {
    "configuration": "C_DEGRADED_RADAR",
    "dependencies": [
        {"dependency": "radar", "elements": ["smart-radar"], "flows": ["f02-radar-raw", "f06-radar-sensor-out"]},
        {"dependency": "front-zone", "elements": ["front-zone"], "flows": ["f09-radar-vc"]},
        {"dependency": "network", "elements": ["loop-gateway"], "flows": ["f09-radar-vc", "f10-motion-chassis", "f17-brake-command"]},
        {"dependency": "vehicle-control-hpc", "elements": ["evidence-validator", "radar-fallback", "vehicle-state", "functional-arbiter",
                                                           "configuration-manager", "transition-verifier",
                                                           "fixed-fallback-supervisor"], "flows": []},
        {"dependency": "vehicle-motion", "elements": ["motion-sensor-model"], "flows": ["f03-motion-raw", "f10-motion-chassis"]},
        {"dependency": "chassis-zone-and-brake-path", "elements": ["chassis-zone", "brake-esc-node", "carla-client"],
         "flows": ["f17-brake-command", "f04-actuation-command"]},
    ],
    "notDependencies": ["adas-hpc", "vc-assurance"],
}


# --------------------------------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------------------------------

def _ref(kind: str, name: str, element: str | None = None) -> dict[str, str]:
    ref = {"apiVersion": API, "kind": kind, "namespace": NAMESPACE, "name": name}
    if element is not None:
        ref["element"] = element
    return ref


def _metadata(name: str, description: str, limitations: list[str] | None = None) -> dict[str, Any]:
    provenance: dict[str, Any] = {"source": "xverse-blueprints/automotive/assured-aeb/topology.py", "revision": "wp12-v0.1",
                                  "maturity": "architectural-target"}
    if limitations:
        provenance["limitations"] = limitations
    return {"namespace": NAMESPACE, "name": name, "version": "0.1.0", "description": description, "provenance": provenance}


def _payload(kind: str, **members: Any) -> dict[str, Any]:
    return {"schemaVersion": "0.1", "kind": kind, **members}


def _xcom(kind: str, target: dict[str, str], policy: dict[str, Any]) -> dict[str, Any]:
    return {"schemaVersion": "0.1", "kind": kind, "target": target, "policy": policy}


def _endpoint_id(element: str, interface: str, direction: str) -> str:
    text = f"{element}-{interface}-{'out' if direction == 'output' else 'in'}"
    if len(text) > 63:
        raise ValueError(f"identifier too long: {text}")
    return text


def units_of(arm: str) -> dict[str, tuple[str, str, str, tuple[str, ...]]]:
    """Return the units of ``arm`` (the 7-unit variant adds ``chassis-brake`` to the MLOC units)."""

    if arm == VARIANT_7:
        units = {u: v for u, v in UNITS.items() if "mloc" in v[3]}
        units[UNIT_7[0]] = UNIT_7[1]
        return units
    return {u: v for u, v in UNITS.items() if arm in v[3]}


def elements_of(arm: str) -> dict[str, tuple[str, str, str, tuple[str, ...], tuple[str, ...]]]:
    """Return the element instances of ``arm`` (the 7-unit variant re-hosts the chassis zone and brake node)."""

    base = "mloc" if arm == VARIANT_7 else arm
    result = {e: v for e, v in ELEMENTS.items() if base in v[3]}
    if arm == VARIANT_7:
        for element in ("chassis-zone", "brake-esc-node"):
            cls, _, node, arms, outputs = result[element]
            result[element] = (cls, UNIT_7[0], node, arms, outputs)
    return result


def flows_of(arm: str) -> dict[str, tuple[str, str, str, str, str, tuple[str, ...]]]:
    base = "mloc" if arm == VARIANT_7 else arm
    return {f: v for f, v in FLOWS.items() if base in v[5]}


def intra_of(arm: str) -> list[tuple[str, str, str]]:
    base = "mloc" if arm == VARIANT_7 else arm
    elements = elements_of(arm)
    rows = []
    for producer, interface, consumer, arms in INTRA:
        if base not in arms:
            continue
        if arm == VARIANT_7 and elements[producer][1] != elements[consumer][1]:
            continue  # re-hosted pair: carried as an inter-unit message in the dry-run variant (not modelled)
        rows.append((producer, interface, consumer))
    return rows


def _inputs(arm: str) -> dict[str, set[str]]:
    inputs: dict[str, set[str]] = {}
    for producer, interface, consumer, *_ in flows_of(arm).values():
        inputs.setdefault(consumer, set()).add(interface)
    for producer, interface, consumer in intra_of(arm):
        inputs.setdefault(consumer, set()).add(interface)
    return inputs


def contract_owner(interface: str, arm: str) -> str | None:
    """Return the element whose Component carries the X-COM contract of ``interface`` in ``arm``."""

    producers = sorted(e for e, v in elements_of(arm).items() if interface in v[4])
    return producers[0] if producers else None


def component(element: str, arm: str) -> dict[str, Any]:
    """Return the Component of ``element``: interfaces, endpoints and the authority payload."""

    authority, _, _, _, outputs = ELEMENTS[element]
    name = f"aeb-{element}"
    inputs = sorted(_inputs(arm).get(element, set()) | _inputs("mloc").get(element, set()))
    interfaces, endpoints = [], []
    for interface in sorted(outputs):
        row = {"id": interface, "direction": "output", "payloadSchema": f"urn:xverse:assured-aeb:{interface}:v1",
               "unitSemantics": INTERFACES[interface], "compatibility": "exact"}
        if contract_owner(interface, arm) == element:
            # One X-COM contract per message type: a contract id is the interface id, so only one Component (the first
            # producer in name order) carries the interface-policy (xcom_plan XCOM-PLAN-DUPLICATE otherwise); the
            # X-COM profile admits no System attachment.
            row["extensions"] = {XCOM: _xcom("interface-policy", _ref("Component", name), {
                "interactionKind": "message", "schemaId": f"{interface}-schema", "schemaVersion": "1.0.0",
                "encoding": "json", "semanticCompatibility": "exact"})}
        interfaces.append(row)
        endpoints.append({"id": f"{interface}-out", "ownerId": name, "interfaceId": interface, "direction": "output"})
    for interface in inputs:
        if interface in outputs:
            continue
        interfaces.append({"id": interface, "direction": "input", "payloadSchema": f"urn:xverse:assured-aeb:{interface}:v1",
                           "unitSemantics": INTERFACES[interface], "compatibility": "exact"})
        endpoints.append({"id": f"{interface}-in", "ownerId": name, "interfaceId": interface, "direction": "input"})
    doc = {
        "apiVersion": API, "kind": "Component",
        "metadata": _metadata(name, f"Assured AEB element {element} ({authority}); module of its host unit, not a Maestro unit."),
        "extensions": {
            EXT: _payload("component-authority", authorityClass=authority, permittedOutputs=sorted(outputs)),
            XCOM: _xcom("flow-policy", _ref("Component", name), dict(FLOW_POLICY)),
        },
        "spec": {"capabilities": [f"assured-aeb-{authority}"], "interfaces": interfaces, "endpoints": endpoints},
    }
    return doc


def unit_host_component() -> dict[str, Any]:
    return {
        "apiVersion": API, "kind": "Component",
        "metadata": _metadata("assured-aeb-unit-host", "Process host of one Maestro unit (shape S-A); no AEB endpoint."),
        "extensions": {EXT: _payload("component-authority", authorityClass="unit-host", permittedOutputs=[])},
        "spec": {"capabilities": ["host-process"], "interfaces": [], "endpoints": []},
    }


def _system_name(arm: str) -> str:
    return f"assured-aeb-{arm}"


def system(arm: str, form: str = "topology") -> dict[str, Any]:
    units = units_of(arm)
    elements = elements_of(arm)
    flows = flows_of(arm)
    instances = []
    for unit, (node, _, unit_class, _) in units.items():
        instances.append({"id": uid(unit), "componentRef": _ref("Component", "assured-aeb-unit-host"), "nodeId": node,
                          "extensions": {EXT: _payload("unit-host", unitClass=unit_class,
                                                       hostedElements=sorted(e for e, v in elements.items() if v[1] == unit))}})
    for element, (authority, host, node, _, _) in elements.items():
        instances.append({"id": element, "componentRef": _ref("Component", f"aeb-{element}"), "nodeId": node,
                          "extensions": {EXT: _payload("element-placement", hostUnit=uid(host),
                                                       arms=[a for a in ARMS if a in ELEMENTS[element][3]],
                                                       computeLatency=todo("author decision", "AD-30"))}})
    endpoints: dict[str, dict[str, Any]] = {}

    def endpoint(element: str, interface: str, direction: str) -> str:
        ident = _endpoint_id(element, interface, direction)
        endpoints.setdefault(ident, {"id": ident, "ownerId": element, "interfaceId": interface, "direction": direction})
        return ident

    for element, (_, _, _, _, outputs) in elements.items():
        for interface in outputs:
            endpoint(element, interface, "output")
    system_flows, returns = [], []
    for flow_id, (producer, interface, consumer, network, latency, _) in flows.items():
        payload = _payload("flow-declaration", intraUnit=False, latencyKind=latency,
                           modelledLatency=todo("author decision", "AD-30") if latency != "none" else "none",
                           freshness=todo("author decision", "AD-06"), deadline=todo("author decision", "AD-07"),
                           faultAdmission=RELAY_ADMITTED.get(flow_id, []))
        if flow_id in ABLATION_EXCEPTIONS:
            payload["ablationException"] = ABLATION_EXCEPTIONS[flow_id]
        row = {"id": flow_id, "sourceEndpointId": endpoint(producer, interface, "output"),
               "destinationEndpointIds": [endpoint(consumer, interface, "input")], "interfaceId": interface,
               "deliveryIntent": "ordered", "networkId": network, "timeDomainId": "carla-simulation",
               "extensions": {EXT: payload}}
        if flow_id in RETURN_FLOWS:
            returns.append({"id": flow_id, "source": row["sourceEndpointId"], "destination": row["destinationEndpointIds"][0],
                            "interfaceId": interface, "networkId": network, "declaration": payload})
        else:
            system_flows.append(row)
    intra = []
    for producer, interface, consumer in intra_of(arm):
        intra.append({"source": endpoint(producer, interface, "output"), "destination": endpoint(consumer, interface, "input"),
                      "interfaceId": interface})
    networks = sorted({v[3] for f, v in flows.items() if f not in RETURN_FLOWS} | {v[3] for v in flows.values()})
    nodes = [{"id": node, "roles": roles} for node, roles in NODES.items()]
    domains = [
        {"id": "carla-simulation", "clockClass": "simulation", "epoch": "first-ticked-frame", "rate": "1", "monotonic": True},
        {"id": "experiment-time", "clockClass": "simulation", "epoch": "0", "rate": "1", "monotonic": True},
        {"id": "host-monotonic", "clockClass": "monotonic", "epoch": "host-boot", "rate": "wall-rate", "monotonic": True},
    ]
    if form == "maestro":
        system_flows, networks, domains = [], [], [domains[1]]
    doc = {
        "apiVersion": API, "kind": "System",
        "metadata": _metadata(_system_name(arm), f"Bounded zonal AEB research topology, arm {arm} (Note 21; WP-11; WP-12).",
                              ["Topology declaration only: no unit program exists yet (WP-13 to WP-17).",
                               "All units run on one host: no hardware or network independence (ED-14)."]),
        "extensions": {EXT: _payload("system-architecture", arm=arm, commonCause=_cc_of(arm), freezeTargets=_freeze_of(arm),
                                     returnFlows=returns, degradedPath=dict(DEGRADED_PATH, notDependencies=[uid(u) for u in DEGRADED_PATH["notDependencies"]]), intraUnitMessages=intra,
                                     excluded=["legacy-vcu", "driver-stimulus", "other-zonal-and-legacy-ecus",
                                               "ground-truth-observer-instance", "oracle-instance", "zenoh-router"])},
        "spec": {
            "nodes": nodes,
            "componentInstances": instances,
            "interfaces": [{"id": i, "direction": "bidirectional", "payloadSchema": f"urn:xverse:assured-aeb:{i}:v1",
                            "unitSemantics": s, "compatibility": "exact"} for i, s in sorted(INTERFACES.items())],
            "endpoints": [endpoints[k] for k in sorted(endpoints)],
            "flows": system_flows,
            "networks": [{"id": n, "scope": "in-vehicle-simulated",
                          "capabilities": ["xcom.delivery.best-effort", "xcom.ordering.per-route-fifo"]} for n in networks],
            "timeDomains": domains,
            "defaultTimeDomainId": "experiment-time" if form == "maestro" else "carla-simulation",
        },
    }
    if not doc["spec"]["networks"]:
        del doc["spec"]["networks"]
    if not doc["spec"]["flows"]:
        del doc["spec"]["flows"]
    if form == "maestro":
        doc["extensions"][EXT]["form"] = "maestro"
        doc["extensions"][EXT]["unplannedFlows"] = sorted(flows)
    return doc


def _cc_of(arm: str) -> list[dict[str, Any]]:
    units = units_of(arm)
    rows = []
    for row in COMMON_CAUSE:
        if all(member in units for member in row["members"]):
            rows.append(dict(copy.deepcopy(row), members=[uid(m) for m in row["members"]]))
    if arm == VARIANT_7:
        rows.append({"id": "cc-2e", "kind": "shared-process", "members": [uid("chassis-brake")], "exercise": "no decided case"})
    return rows


def _freeze_of(arm: str) -> dict[str, Any]:
    units = units_of(arm)
    result = copy.deepcopy(FREEZE_TARGETS)
    result["admitted"] = [uid(u) for u in result["admitted"] if u in units]
    result["admittedSets"] = [[uid(u) for u in s] for s in result["admittedSets"] if all(u in units for u in s)]
    result["refused"] = [uid(u) for u in result["refused"]]
    return result


def deployment(arm: str, pins: dict[str, str], form: str = "topology") -> dict[str, Any]:
    units = units_of(arm)
    name = f"{_system_name(arm)}-deployment"
    flows = flows_of(arm)
    networks = sorted({v[3] for v in flows.values()}) if form == "topology" else []
    targets = [{"id": f"{unit}-target", "targetClass": "process",
                "capabilities": ["execute-process"],
                "lifecycle": {"prepare": "prepare", "ready": "ready", "start": "start", "stop": "stop", "failure": "failure"}}
               for unit in units]
    artifacts = [
        {"id": "python310", "artifactKind": "executable", "version": "3.10", "digest": pins["python310"],
         "sourceRef": "file://" + PY310, "maturity": "prototype"},
        {"id": "python313", "artifactKind": "executable", "version": "3.13.13", "digest": pins["python313"],
         "sourceRef": "file://" + PY313, "maturity": "prototype"},
        {"id": "aeb-perception-model", "artifactKind": "model", "version": "0.0.0", "sourceRef": "urn:xverse:assured-aeb:model:perception",
         "maturity": "architectural-target",
         "limitations": ["Not yet trained or frozen: digest TODO: measurement (WP-09, AD-02); not bound to a unit yet."]},
        {"id": "carla-server", "artifactKind": "simulator", "version": "0.9.15", "sourceRef": "urn:xverse:assured-aeb:external:carla-0.9.15",
         "maturity": "prototype", "limitations": ["External dependency; identity recorded by the harness (ED-11 open)."]},
    ]
    bindings = []
    for unit, (_, interpreter, unit_class, _) in units.items():
        executable = PY310 if interpreter == "python310" else PY313
        actions = [{"id": phase, "phase": phase, "operation": "validate" if phase == "prepare" else phase,
                    "timeoutSeconds": ACTION_TIMEOUTS[phase], **({"condition": "nonce-marker"} if phase == "observe" else {})}
                   for phase in ("prepare", "start", "observe", "stop", "cleanup")]
        bindings.append({
            "id": f"{unit}-binding",
            "logicalRef": _ref("System", _system_name(arm), uid(unit)),
            "realizationClass": "simulated",
            "targetId": f"{unit}-target",
            "artifactIds": [interpreter],
            "lifecycle": {"prepare": "prepare", "ready": "ready", "start": "start", "stop": "stop", "failure": "failure"},
            "extensions": {
                EXPERIMENT: {"schemaVersion": "0.1", "kind": "realization-intent", "delivery": "none",
                             "target": _ref("Deployment", name, f"{unit}-binding"),
                             "fidelityLimitations": ["Declared unit realization; the unit program is implemented in WP-13 to WP-17."]},
                RUNTIME: {
                    "schemaVersion": "0.2.0", "environmentId": ENVIRONMENT_ID, "provider": dict(PROVIDER), "actions": actions,
                    "process": {"executable": executable, "arguments": ["-B", "-m", f"assured_aeb.units.{unit.replace('-', '_')}"],
                                "workingDirectory": f"/xverse-run/assured-aeb/work/{unit}",
                                "environmentNames": ["HOME", "PATH", "PYTHONPATH"], "inheritedHandles": "closed", "implicitShell": False,
                                "stop": {"graceSeconds": STOP_GRACE_S}, "stderr": dict(STDERR)},
                    "evidence": {"maturity": "architectural-target",
                                 "limitations": [f"{unit_class} unit; module path and working directory are declared, substituted "
                                                 "by the run harness as in the Phase 7 blueprint; no live execution is authorized."]},
                },
            },
        })
    # One loopback provider per consuming segment (design §4). The networkBinding schema admits no extension, so the
    # provider is a dedicated Deployment target carrying the X-COM network-provider payload, selected for a flow through
    # its network: the flow's networkBinding names a per-network Profile that only that target references
    # (xverse.flows.binding._select_provider). Finding 2 records this.
    for network in networks:
        targets.append({"id": f"{network}-provider", "targetClass": "process",
                        "capabilities": ["provide-network", "xcom.delivery.best-effort", "xcom.ordering.per-route-fifo"],
                        "profileRefs": [_ref("Profile", f"{network}-profile")],
                        "lifecycle": {"prepare": "prepare", "ready": "ready", "start": "start", "stop": "stop", "failure": "failure"},
                        "extensions": {XCOM: _xcom("network-provider", _ref("Deployment", name), {
                            "requiredCapabilities": ["provide-network"], "fidelity": "declared",
                            "limitations": [f"loopback provider of segment {network}; realized by the vehicle-loop hub"]})}})
    network_bindings = [{"id": f"{network}-binding", "logicalNetworkRef": _ref("System", _system_name(arm), network),
                         "profileRef": _ref("Profile", f"{network}-profile"),
                         "limitations": ["Realized by the owned Unix-socket hub in the vehicle-loop unit (decisions.md §K)",
                                         "Loopback provider mirror: at most 4 routes and best-effort per-route FIFO (Phase 6)",
                                         "AD-30 modelled latency only; no network timing claim"]}
                        for network in networks]
    doc = {
        "apiVersion": API, "kind": "Deployment",
        "metadata": _metadata(name, f"Single-host Lite realization of the assured AEB, arm {arm}.",
                              ["Declared process units; not M1 (AD-21); no live run is authorized by this document."]),
        "spec": {
            "systemRef": _ref("System", _system_name(arm)),
            "targets": targets,
            "artifacts": artifacts,
            "simulators": [{"id": "carla", "standardRef": "urn:xverse:assured-aeb:external:carla-0.9.15", "artifactId": "carla-server",
                            "timeDomainId": "carla-simulation", "limitations": ["External server outside Maestro (ED-11)."]}],
            "bindings": bindings,
            "networkBindings": network_bindings,
            "readiness": {"requiredConditions": ["artifacts-pinned"], "failurePolicy": "fail-fast"},
        },
    }
    if form == "maestro":
        del doc["spec"]["simulators"]
        del doc["spec"]["networkBindings"]
        doc["spec"]["artifacts"] = [a for a in artifacts if a["id"] != "carla-server"]
    return doc


def scenario(arm: str, horizon: int = HORIZON, faults: list[dict[str, Any]] | None = None, form: str = "topology") -> dict[str, Any]:
    units = units_of(arm)
    name = f"{_system_name(arm)}-scenario"
    order = [u for u in START_ORDER if u in units]
    plan = []
    for index, unit in enumerate(order):
        before = [f"start-{order[index - 1]}"] if index else []
        plan += [(f"prepare-{unit}", unit, "prepare", 0, []), (f"start-{unit}", unit, "start", 0, [f"prepare-{unit}"] + before),
                 (f"observe-{unit}", unit, "observe", OBSERVE_TICK, [f"start-{unit}"])]
    for offset, unit in enumerate(reversed(order)):
        tick = horizon - len(order) + 1 + offset
        plan += [(f"stop-{unit}", unit, "stop", tick, [f"observe-{unit}"]), (f"cleanup-{unit}", unit, "cleanup", tick, [f"stop-{unit}"])]
    steps = []
    for step_id, unit, phase, tick, deps in plan:
        operation = "validate" if phase == "prepare" else phase
        steps.append({"id": step_id, "actionKind": operation, "targetRef": _ref("System", _system_name(arm), uid(unit)),
                      "timeDomainId": "experiment-time", "schedule": {"at": tick, "unit": "tick", "tolerance": {"value": 0, "unit": "tick"}},
                      "action": {"operation": operation},
                      "extensions": {EXPERIMENT: {"schemaVersion": "0.1", "kind": "step-intent", "target": _ref("Scenario", name, step_id),
                                                  "phase": phase, "dependsOn": deps}}})
    forward = [f for f in flows_of(arm) if f not in RETURN_FLOWS]
    if form == "topology":
        # Scenario observers are X-COM observation taps and must target routes (xcom_plan). They are the hub's flow
        # evidence (FR-022), never the evaluation-only ground truth, which is declared in the extension below.
        observers = [{"id": f"tap-{f}", "targetRef": _ref("System", _system_name(arm), f), "timeDomainId": "carla-simulation",
                      "samplingIntent": "every delivered item; flow verdicts at the vehicle-loop hub",
                      "payloadSchema": "urn:xverse:assured-aeb:flow-evidence:v1", "unitSemantics": "count",
                      "evidenceSinkRef": "urn:xverse:assured-aeb:argus-flow-evidence"} for f in forward]
        metrics = [{"id": "flow-verdicts", "observerIds": [o["id"] for o in observers],
                    "calculationRef": "urn:xverse:assured-aeb:metric:flow-verdicts", "unitSemantics": "count",
                    "acceptance": "engineering evidence only; no scientific acceptance"}]
    else:
        observers = [{"id": "unit-completion-markers", "targetRef": _ref("System", _system_name(arm), uid("vehicle-loop")),
                      "timeDomainId": "experiment-time", "samplingIntent": "one completion marker per owned unit",
                      "payloadSchema": "urn:xverse:assured-aeb:completion-marker:v1", "unitSemantics": "count",
                      "evidenceSinkRef": "urn:xverse:assured-aeb:collection-result"}]
        metrics = [{"id": "completion-markers", "observerIds": ["unit-completion-markers"],
                    "calculationRef": "urn:xverse:assured-aeb:metric:completion-markers", "unitSemantics": "count",
                    "acceptance": "engineering evidence only; no scientific acceptance"}]
    doc = {
        "apiVersion": API, "kind": "Scenario",
        "metadata": _metadata(name, f"Lifecycle skeleton of the assured AEB, arm {arm}; scenario family and fault model TODO.",
                              [f"Horizon {horizon} Maestro ticks is the S1 engineering capacity, not the protocol horizon (AD-25)."]),
        "extensions": {EXPERIMENT: {"schemaVersion": "0.1", "kind": "scenario-intent", "target": _ref("Scenario", name),
                                    "seed": {"value": 0, "unitSemantics": "experiment-seed"}, "parameters": [],
                                    "fidelityLimitations": ["Seed 0 is a structural placeholder; seed lists TODO (P-4).",
                                                            "Fault model TODO (AD-31, AD-13); faults keyed to simulator time (WP-10)."]}},
        "spec": {
            "systemRef": _ref("System", _system_name(arm)),
            "deploymentRef": _ref("Deployment", f"{_system_name(arm)}-deployment"),
            "initialConditions": {"scenarioFamily": todo("author decision", "AD-04")},
            "steps": steps,
            "faults": faults or [],
            # XDL requires a declared mapping between the step domain and the observer domain. Maestro ticks and CARLA
            # frames have no fixed relation (frames per tick are measured, GA-34; D6-4 admits only identity or offset),
            # so the pair is declared explicitly unmapped. Tolerance 0 is a schema-required number, not a protocol value.
            "timeMappings": [{"sourceTimeDomainId": "experiment-time", "targetTimeDomainId": "carla-simulation",
                              "mapping": UNMAPPED, "tolerance": {"value": 0, "unit": "tick"}}] if form == "topology" else [],
            "observers": observers,
            "metrics": metrics,
        },
    }
    if not doc["spec"]["timeMappings"]:
        del doc["spec"]["timeMappings"]
    doc["extensions"][EXT] = _payload(
        "scenario-evaluation", form=form,
        evaluationObservers=[{"id": "ground-truth-observer", "realization": "separate process outside Maestro (WP-01; FR-021)",
                              "timeDomainId": "carla-simulation", "samplingIntent": "every CARLA frame; evaluation-only",
                              "outputRoot": "separate evaluation output root"}],
        offlineMetrics=[{"id": "a-dq", "calculationRef": "urn:xverse:assured-aeb:metric:a-dq", "acceptance": todo("author decision", "AD-14")},
                        {"id": "minimum-gap", "calculationRef": "urn:xverse:assured-aeb:metric:minimum-gap",
                         "acceptance": todo("author decision", "AD-15")}])
    return doc


def _profile(name: str, namespace: str, schema_ref: str, doc_ref: str) -> dict[str, Any]:
    return {"apiVersion": API, "kind": "Profile",
            "metadata": {"namespace": NAMESPACE, "name": name, "version": "0.1.0",
                         "provenance": {"source": "xverse-blueprints/automotive/assured-aeb/topology.py", "revision": "wp12-v0.1",
                                        "maturity": "prototype"}},
            "spec": {"extensionNamespace": namespace, "compatibleApiVersions": [API], "schemaRef": schema_ref,
                     "documentationRef": doc_ref, "conflictPolicy": "reject"}}


def network_profiles(arm: str) -> dict[str, dict[str, Any]]:
    """One selector Profile per network segment (no payload uses its namespace; it only keys provider selection)."""

    return {f"profile-{n}.json": _profile(f"{n}-profile", f"{EXT}.{n}", f"urn:xverse:assured-aeb:network-selector:{n}",
                                          "urn:xverse:assured-aeb:docs:review-wp12")
            for n in sorted({v[3] for v in flows_of(arm).values()})}


def profiles() -> dict[str, dict[str, Any]]:
    return {
        "profile-experiment.json": _profile("experiment-lite", EXPERIMENT, "https://xverse.io/profiles/experiment-lite/v0.1/schema.json",
                                            "https://xverse.io/profiles/experiment-lite/v0.1/README.md"),
        "profile-runtime.json": _profile("compatibility-runtime", RUNTIME, "https://xverse.io/profiles/runtime-compatibility/v0.2/schema.json",
                                         "https://xverse.io/docs/profiles/runtime-compatibility/v0.2/"),
        "profile-xcom.json": _profile("xcom-lite", XCOM, "https://xverse.io/profiles/xcom/v0.1/schema.json",
                                      "https://xverse.io/profiles/xcom/v0.1/README.md"),
        "profile-assured-aeb.json": _profile("assured-aeb", EXT, SCHEMA_REF, "urn:xverse:assured-aeb:docs:review-wp12"),
    }


def read_pins() -> dict[str, str]:
    return json.loads((XDL / "pins.json").read_text())["artifacts"]


def host_pins() -> dict[str, str]:
    """Digest the declared interpreters on this host (recorded in xdl/pins.json; drift is reported by the check)."""

    return {key: "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest() for key, path in (("python310", PY310), ("python313", PY313))}


def documents(arm: str, pins: dict[str, str] | None = None, *, form: str = "topology", horizon: int = HORIZON,
              faults: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """Return the XDL documents of ``arm`` in ``form`` keyed by file name."""

    pins = pins or read_pins()
    docs = {"system.json": system(arm, form), "deployment.json": deployment(arm, pins, form),
            "scenario.json": scenario(arm, horizon, faults, form)}
    docs["component-unit-host.json"] = unit_host_component()
    for element in elements_of(arm):
        docs[f"component-{element}.json"] = component(element, arm)
    docs.update(profiles())
    if form == "topology":
        docs.update(network_profiles(arm))
    return docs


def write(pins: dict[str, str]) -> None:
    XDL.mkdir(exist_ok=True)
    (XDL / "pins.json").write_text(json.dumps({"artifacts": pins, "note": "host interpreter digests at generation time"},
                                              indent=2, sort_keys=True) + "\n")
    for arm in ARMS:
        for form in FORMS:
            folder = XDL / arm / form
            folder.mkdir(parents=True, exist_ok=True)
            for old in folder.glob("*.json"):
                old.unlink()
            for name, doc in sorted(documents(arm, pins, form=form).items()):
                (folder / name).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="regenerate xdl/<arm>/ and xdl/pins.json")
    args = parser.parse_args()
    if args.write:
        write(host_pins())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
