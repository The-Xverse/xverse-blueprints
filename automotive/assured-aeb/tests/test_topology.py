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
