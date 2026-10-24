"""Offline tests of the WP-12 topology documents and checker (no unit, simulator or Maestro run)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile

import pytest

import check_topology as C
import topology as T


def test_committed_documents_equal_the_generator():
    pins = T.read_pins()
    for arm in T.ARMS:
        for form in T.FORMS:
            expected = json.loads(json.dumps(T.documents(arm, pins, form=form)))
            assert C.load(arm, form) == expected, (arm, form)


def test_no_protocol_number_in_the_extension_todo_fields():
    for arm in T.ARMS:
        system = C.load(arm, "topology")["system.json"]
        for flow in system["spec"]["flows"]:
            payload = flow["extensions"][T.EXT]
            assert payload["freshness"].startswith("TODO: ") and payload["deadline"].startswith("TODO: ")
            assert "quality" not in flow
        for inst in system["spec"]["componentInstances"]:
            payload = inst["extensions"][T.EXT]
            if payload["kind"] == "element-placement":
                assert payload["computeLatency"].startswith("TODO: ")


@pytest.mark.parametrize("arm", T.ARMS)
@pytest.mark.parametrize("form", T.FORMS)
def test_every_arm_and_form_compiles_deterministically(schema_paths, arm, form):
    validation, result = C.compile_docs(C.load(arm, form), schema_paths)
    assert validation.is_valid, C._diag(validation.diagnostics)
    assert result.is_valid, C._diag(result.diagnostics)
    _, again = C.compile_docs(C.load(arm, form), schema_paths)
    assert again.plan["digest"] == result.plan["digest"]


@pytest.mark.parametrize("arm", T.ARMS)
def test_authority_contract_holds(arm):
    assert C.check_authority(C.load(arm, "topology"), arm) == []


def _add_flow(docs, flow_id, producer, interface, consumer, arm="mloc"):
    spec = docs["system.json"]["spec"]
    for element, direction in ((producer, "output"), (consumer, "input")):
        ident = T._endpoint_id(element, interface, direction)
        if ident not in {e["id"] for e in spec["endpoints"]}:
            spec["endpoints"].append({"id": ident, "ownerId": element, "interfaceId": interface, "direction": direction})
    spec["flows"].append({"id": flow_id, "sourceEndpointId": T._endpoint_id(producer, interface, "output"),
                          "destinationEndpointIds": [T._endpoint_id(consumer, interface, "input")], "interfaceId": interface,
                          "deliveryIntent": "ordered", "networkId": "net-u5", "timeDomainId": "carla-simulation"})
    return docs


@pytest.mark.parametrize("case, producer, interface, consumer, rules", [
    ("proposer-authorizes", "proposer", "authorization", "configuration-manager", {"A-1", "A-2", "A-5"}),
    ("front-zone-commands", "front-zone", "forced-command", "configuration-manager", {"A-1", "A-3", "A-5"}),
    ("runtime-reads-raw-camera", "carla-client", "camera-raw", "perception", {"A-7"}),
    ("relay-feeds-manager-outside-ablation", "fault-relay", "proposal", "configuration-manager", {"A-3", "A-7"}),
    ("gate-brakes", "safety-gate", "brake-request", "chassis-zone", {"A-1", "A-4"}),
])
def test_authority_negatives_are_rejected(case, producer, interface, consumer, rules):
    docs = _add_flow(copy.deepcopy(C.load("mloc", "topology")), f"neg-{case}", producer, interface, consumer)
    violations = C.check_authority(docs, "mloc")
    assert {v.split()[0] for v in violations} >= rules, violations


def test_intra_unit_message_across_units_is_rejected():
    docs = copy.deepcopy(C.load("mloc", "topology"))
    ext = docs["system.json"]["extensions"][T.EXT]
    ext["intraUnitMessages"].append({"source": T._endpoint_id("evidence-validator", "qualified-evidence", "output"),
                                     "destination": T._endpoint_id("safety-monitor", "qualified-evidence", "input"),
                                     "interfaceId": "qualified-evidence"})
    assert any(v.startswith("A-6") for v in C.check_authority(docs, "mloc"))


def test_ivi_instance_and_evaluation_instance_are_rejected():
    docs = copy.deepcopy(C.load("mloc", "topology"))
    spec = docs["system.json"]["spec"]
    spec["componentInstances"].append({"id": "ivi-app", "componentRef": T._ref("Component", "aeb-mrc-sink"), "nodeId": "ivi-hpc",
                                       "extensions": {T.EXT: T._payload("element-placement", hostUnit="vehicle-loop-unit",
                                                                        arms=["mloc"], computeLatency="TODO: design (x)")}})
    spec["componentInstances"].append({"id": "ground-truth-reader", "componentRef": T._ref("Component", "aeb-mrc-sink"),
                                       "nodeId": "simulation-environment",
                                       "extensions": {T.EXT: T._payload("element-placement", hostUnit="vehicle-loop-unit",
                                                                        arms=["mloc"], computeLatency="TODO: design (x)")}})
    violations = C.check_authority(docs, "mloc")
    assert any("IVI" in v for v in violations) and any("ground-truth-reader" in v for v in violations)


def test_bypass_exception_is_honoured_only_in_its_arm():
    docs = copy.deepcopy(C.load("authorization-bypass", "topology"))
    assert C.check_authority(docs, "authorization-bypass") == []
    assert any(v.startswith("A-3") for v in C.check_authority(docs, "mloc"))


@pytest.mark.parametrize("kind, element, refused", [
    ("freeze", "carla-adapter-unit", True), ("freeze", "vehicle-loop-unit", True), ("freeze", "safety-gate", True),
    ("crash", "adas-hpc-unit", True), ("loss", "f07-camera-adas", True),
    ("freeze", "front-zone-unit", False), ("freeze", "adas-hpc-unit", False), ("freeze", "vc-assurance-unit", False),
    ("stale", "f09-radar-vc", False), ("assurance.evidence-loss", "f13-qualified-evidence", False),
])
def test_fault_admission_rule(kind, element, refused):
    entry = C.fault("mloc", "probe", kind, element, 100, 10)
    assert bool(C.check_fault_admission(C.load("mloc", "topology"), [entry])) is refused


def test_cc1_pair_is_admitted_by_rule_and_platform(schema_paths):
    pair = [C.fault("mloc", "a", "freeze", "vc-functional-unit", 100, 10), C.fault("mloc", "b", "freeze", "vc-assurance-unit", 100, 10)]
    assert C.check_fault_admission(C.load("mloc", "topology"), pair) == []
    _, prepared, error = C._prepare_with_faults("mloc", pair, schema_paths)
    assert prepared is not None, error
    assert len(prepared.faults) == 2


@pytest.mark.parametrize("arm", T.ARMS)
def test_unbound_element_instances_are_accepted_and_only_units_execute(schema_paths, arm):
    _, validation, result = (None, *C.compile_docs(C.load(arm, "maestro"), schema_paths))
    prepared = C.prepare(validation, result)
    assert sorted(u.unit_id.rsplit("/", 1)[-1] for u in prepared.units) == sorted(T.uid(u) for u in T.units_of(arm))


def test_topology_form_is_not_maestro_preparable(schema_paths):
    validation, result = C.compile_docs(C.load("mloc", "topology"), schema_paths)
    with pytest.raises(Exception, match="ML-TIME"):
        C.prepare(validation, result)


def test_routes_respect_the_loopback_cap_and_f19_is_the_recorded_residual(schema_paths):
    report = C.Report()
    compiled = {(arm, "topology"): (C.load(arm, "topology"), *C.compile_docs(C.load(arm, "topology"), schema_paths)) for arm in T.ARMS}
    C.check_routes(report, compiled)
    by_arm = {c["arm"]: c for c in report.checks}
    assert all(c["ok"] for c in report.checks)
    assert max(len(v) for v in by_arm["mloc"]["routesPerProvider"].values()) <= 4
    assert [r["flowId"] for r in by_arm["authorization-bypass"]["expectedResiduals"]] == ["f19-bypass-proposal"]
    assert by_arm["authorization-bypass"]["expectedResiduals"][0]["detail"]["xcomOutcome"] == "route_capacity_exhausted"


@pytest.mark.parametrize("n, arm", sorted(C.UNIT_COUNTS.items()))
@pytest.mark.parametrize("op", C.OPERATION_BUDGETS)
def test_admission_agrees_with_the_capacity_rule(schema_paths, n, arm, op):
    validation, result = C.compile_docs(T.documents(arm, T.read_pins(), form="maestro"), schema_paths)
    prepared = C.prepare(validation, result)
    assert len(prepared.units) == n
    rule = (2 * n + 4 + 1) * op < 5
    try:
        C.admit(prepared, op)
        admitted = True
    except Exception as error:
        assert "ML-SCHEDULE-HEALTH-CAPACITY" in str(error)
        admitted = False
    assert admitted is rule


def test_configuration_size_is_measured(schema_paths):
    validation, result = C.compile_docs(T.documents("mloc", T.read_pins(), form="maestro"), schema_paths)
    prepared = C.prepare(validation, result)
    schedule = C.admit(prepared, 0.29)
    with tempfile.TemporaryDirectory() as work:
        size = C.configuration_bytes(prepared, result, validation.resources, schedule, Path(work))
    assert size > 0


# ---- finding 4 repairs ------------------------------------------------------------------------------------------

def _pair(onset_b=100, duration_b=10):
    return [C.fault("mloc", "a", "freeze", "vc-functional-unit", 100, 10),
            C.fault("mloc", "b", "freeze", "vc-assurance-unit", onset_b, duration_b)]


def test_lone_vc_functional_freeze_is_refused():  # HIGH-1
    refusals = C.check_fault_admission(C.load("mloc", "topology"), [C.fault("mloc", "a", "freeze", "vc-functional-unit", 100, 10)])
    assert refusals and "every member" in refusals[0]


@pytest.mark.parametrize("onset_b, duration_b", [(300, 10), (100, 20)])
def test_non_concurrent_cc1_pair_is_refused(onset_b, duration_b):  # HIGH-1: same onset and same duration required
    refusals = C.check_fault_admission(C.load("mloc", "topology"), _pair(onset_b, duration_b))
    assert any("vc-functional-unit" in r for r in refusals)


def test_concurrent_cc1_pair_is_admitted():  # HIGH-1 positive
    assert C.check_fault_admission(C.load("mloc", "topology"), _pair()) == []


def test_cc1_pair_is_refused_in_the_comparator_where_vc_assurance_does_not_exist():
    docs = C.load("comparator", "topology")
    assert C.check_fault_admission(docs, [C.fault("comparator", "a", "freeze", "vc-functional-unit", 100, 10)])


def test_freeze_duration_is_bounded_by_a_supplied_thaw_bound(schema_paths):  # MEDIUM-2
    validation, result = C.compile_docs(T.documents("mloc", T.read_pins(), form="maestro"), schema_paths)
    schedule = C.admit(C.prepare(validation, result), 0.29)
    thaw = C.LIVE["cadence"] - schedule.health_scan_seconds  # from the admitted schedule, not hard-coded
    bound = C.FreezeBound(thaw_bound_s=thaw, max_cycle_s=0.1)  # 0.1 s: a test value standing in for the D-4c maximum
    docs = C.load("mloc", "topology")
    ok = C.fault("mloc", "ok", "freeze", "adas-hpc-unit", 100, bound.max_ticks)
    long = C.fault("mloc", "long", "freeze", "adas-hpc-unit", 100, bound.max_ticks + 1)
    assert C.check_fault_admission(docs, [ok], bound) == []
    assert any("thaw bound" in r for r in C.check_fault_admission(docs, [long], bound))
    assert C.check_fault_admission(docs, [long]) == []  # without a bound the duration is not checked


@pytest.mark.parametrize("arm", T.ARMS)
def test_every_cross_unit_cycle_crosses_a_hub_delay_point(arm):  # MEDIUM-1
    result = C.check_cycles(C.load(arm, "topology"))
    assert result["crossUnitCycles"] == []
    assert {"f04-actuation-command", "f17-brake-command"} <= set(result["delayPoints"])


def _without_delay(docs, flow_id):
    docs = copy.deepcopy(docs)
    for flow in docs["system.json"]["spec"].get("flows", []):
        if flow["id"] == flow_id:
            del flow["extensions"][T.EXT]["hubDelay"]
    for flow in docs["system.json"]["extensions"][T.EXT]["returnFlows"]:
        if flow["id"] == flow_id:
            del flow["declaration"]["hubDelay"]
    return docs


@pytest.mark.parametrize("flow_id, loop", [
    ("f17-brake-command", {"loop-gateway", "brake-esc-node"}),  # brake loop U2 -> U3 -> U4 -> U5 -> U2
    ("f14-authorization", {"safety-gate", "configuration-manager"}),  # authorization loop U5 -> U6 -> U5
    ("f04-actuation-command", {"carla-client", "loop-gateway"}),  # adapter link U1 <-> U2
])
def test_each_delay_point_is_necessary(flow_id, loop):
    cycles = C.check_cycles(_without_delay(C.load("mloc", "topology"), flow_id))["crossUnitCycles"]
    assert any(loop <= set(component) for component in cycles), cycles


def test_f15b_return_flow_is_needed_for_xdl_acyclicity(schema_paths):  # F15b breaks the XDL-visible cycle
    docs = copy.deepcopy(C.load("mloc", "topology"))
    system = docs["system.json"]
    row = next(f for f in system["extensions"][T.EXT]["returnFlows"] if f["id"] == "f15b-configuration-state-proposer")
    system["spec"]["flows"].append({"id": row["id"], "sourceEndpointId": row["source"], "destinationEndpointIds": [row["destination"]],
                                    "interfaceId": row["interfaceId"], "deliveryIntent": "ordered", "networkId": row["networkId"],
                                    "timeDomainId": "carla-simulation"})
    _, result = C.compile_docs(docs, schema_paths)
    assert any(d.code == "XDL1-PLAN-DEPENDENCY-CYCLE" for d in result.diagnostics)


def test_degraded_path_takes_radar_directly_not_through_the_validator():  # MEDIUM-3
    msgs = C.messages(C.load("mloc", "topology"))
    into_fallback = {(m["producer"], m["interface"]) for m in msgs if m["consumer"] == "radar-fallback"}
    assert ("vc-ingress", "radar-evidence") in into_fallback
    f09 = next(m for m in msgs if m["id"] == "f09-radar-vc")
    assert (f09["producer"], f09["consumer"]) == ("front-zone", "vc-ingress")
    into_arbiter = {(m["producer"], m["interface"]) for m in msgs if m["consumer"] == "functional-arbiter"}
    assert ("vc-ingress", "adas-cycle") in into_arbiter


@pytest.mark.parametrize("arm", T.ARMS)
def test_forms_are_equal_apart_from_the_declared_projection(arm):  # LOW-1
    assert C.forms_difference(arm) == []


def test_forms_difference_can_fail():  # LOW-1: the assertion is real
    maestro = copy.deepcopy(C.load("mloc", "maestro"))
    maestro["system.json"]["spec"]["componentInstances"][0]["nodeId"] = "ivi-hpc"
    maestro["deployment.json"]["spec"]["bindings"][0]["targetId"] = "mutated-target"
    difference = C.forms_difference("mloc", maestro_docs=maestro)
    assert {"system.componentInstances", "deployment.bindings"} <= set(difference)


def test_a4_right_producer_wrong_consumer_is_rejected():  # LOW-4
    docs = _add_flow(copy.deepcopy(C.load("mloc", "topology")), "neg-arbiter-to-brake-node", "functional-arbiter",
                     "brake-request", "brake-esc-node")
    assert any(v.startswith("A-4") and "to brake-esc-node" in v for v in C.check_authority(docs, "mloc"))


def test_proposal_contract_is_carried_by_the_proposer_not_the_relay():  # LOW-3
    assert T.contract_owner("proposal", "mloc") == "proposer"
