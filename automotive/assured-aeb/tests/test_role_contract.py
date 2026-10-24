"""WP-14a structural/identity cases. All values below are TEST-ONLY records.

These tests do not instantiate monitor, gate, supervisor or transition policy.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from assured_aeb import brake_esc as B
from assured_aeb import role_contract as C

HERE = Path(__file__).resolve().parents[1]
NOMINAL, DEGRADED = "C_NOMINAL", "C_DEGRADED_RADAR"
BODIES = {
    "proposal": dict(proposalId="p1", target=NOMINAL, fromConfiguration=DEGRADED, basisRefs=["q1"], validUntilNs=200),
    "objective": dict(objectiveId="o1", objective="test-objective", validUntilNs=200),
    "goal-model": dict(goalId="g1", objectiveId="o1", constraints={"test.constraint": True}, basisRefs=["o1"]),
    "qualified-evidence": dict(evidenceId="q1", configuration=NOMINAL, state="NOMINAL", items=[]),
    "vehicle-state-record": dict(speedMps=1.0, accelerationMps2=0.0, state="NOMINAL", evidenceRefs=["motion1"]),
    "diagnostic-verdict": dict(diagnosticId="d1", state="NOMINAL", reasons=[], evidenceRefs=["q1"]),
    "assessment": dict(assessmentId="a1", configuration=NOMINAL, state="NOMINAL", admissible=True, evidenceRefs=["q1"], deadlineMarginNs=None, recurrence=0),
    "authorization": dict(authorizationId="auth1", proposalId="p1", fromConfiguration=DEGRADED, toConfiguration=NOMINAL, assessmentRef="a1", issuedAtNs=100, validUntilNs=200, gateSequence=1),
    "gate-state": dict(gateSequence=1, state="closed", monitorAssessmentAgeNs=None),
    "forced-command": dict(commandId="c1", **{"class": "degradation"}, target=DEGRADED, trigger=["d1"]),
    "transition-request": dict(transitionId="t1", phase="pre", outcome=None, evidenceRefs=["auth1"], deadlineId="transition.confirmation"),
    "transition-verdict": dict(transitionId="t1", phase="post", outcome="confirmed", evidenceRefs=["selector1"], deadlineId="transition.confirmation"),
    "configuration-state": dict(configuration=NOMINAL, transitionId="t1", phase="confirmed", committedAtNs=100),
    "selector-command": dict(configuration=NOMINAL),
    "aeb-status": dict(status="unavailable", reason="test-no-path", requestId="m1"),
    "mrc-request": dict(requestId="m1", reason="test-no-path", evidenceRefs=["q1"]),
}


def record(name):
    return C.make_record(name, source=C.SOURCES[name], sequence=1, origin_ns=100, **copy.deepcopy(BODIES[name]))


@pytest.mark.parametrize("name", BODIES)
def test_each_role_binding_record_has_a_closed_schema_and_projected_source(name):
    value = record(name)
    interface = "authorization" if name == "gate-state" else name
    binding = C.EndpointBinding.from_record(dict(interface=interface, producer=C.SOURCES[name], consumer=C.CONSUMERS[name][0]))
    assert binding.consume(value, received_producer=C.SOURCES[name]) == value
    assert value["schema"] in C.URN_TO_SCHEMAS["urn:xverse:assured-aeb:" + interface + ":v1"]
    assert binding.consume(value, received_producer=C.SOURCES[name]) is not value


@pytest.mark.parametrize("name", BODIES)
@pytest.mark.parametrize("mutation", ["missing", "extra", "nan"])
def test_each_role_schema_refuses_missing_extra_and_nonfinite_fields(name, mutation):
    value = record(name)
    if mutation == "missing":
        value.pop(next(iter(BODIES[name])))
    elif mutation == "extra":
        value["undeclared"] = "test"
    else:
        value["originNs"] = float("nan")
    with pytest.raises(C.ContractError):
        C.validate_record(name, value)


@pytest.mark.parametrize("producer", ["front-zone", "proposer", "ivi"])
def test_self_claimed_gate_identity_never_overrides_the_projected_or_received_source(producer):
    value = record("authorization")
    expected_gate = C.EndpointBinding("authorization", "safety-gate", "configuration-manager")
    with pytest.raises(C.ContractError, match="received producer"):
        expected_gate.consume(value, received_producer=producer)
    wrong_projection = C.EndpointBinding("authorization", producer, "configuration-manager")
    with pytest.raises(C.ContractError, match="outside the role contract"):
        wrong_projection.consume(value, received_producer=producer)


def test_payload_source_and_consumer_are_checked_separately():
    binding = C.EndpointBinding("authorization", "safety-gate", "configuration-manager")
    value = record("authorization");value["source"] = "proposer"
    with pytest.raises(C.ContractError):
        binding.consume(value, received_producer="safety-gate")
    with pytest.raises(C.ContractError):
        C.EndpointBinding("authorization", "safety-gate", "ivi").consume(record("authorization"), received_producer="safety-gate")


def test_endpoint_projection_is_closed_and_has_no_arm_or_fault_input():
    for value in ({"interface": "proposal", "producer": "proposer"},
                  {"interface": "proposal", "producer": "proposer", "consumer": "safety-gate", "arm": "test"},
                  {"interface": [], "producer": "proposer", "consumer": "safety-gate"},
                  {"interface": "gate-state", "producer": "safety-gate", "consumer": "configuration-manager"}):
        with pytest.raises(C.ContractError):
            C.EndpointBinding.from_record(value)


def test_f14_explicitly_maps_both_authorization_and_gate_state_without_a_new_interface():
    schema = json.loads((HERE / "schemas/roles/authorization.schema.json").read_text())
    assert schema["$id"] == "urn:xverse:assured-aeb:authorization:v1"
    assert {s["properties"]["schema"]["const"] for s in schema["oneOf"]} == {"assured-aeb.authorization/1", "assured-aeb.gate-state/1"}


def test_wp04_five_member_request_and_routed_variant_are_preserved():
    value = B.brake_request(1, 100, 0.5)
    direct = C.EndpointBinding("brake-request", "functional-arbiter", "chassis-zone")
    assert direct.consume(value, received_producer="functional-arbiter") == value
    assert set(value) == {"schema", "source", "sequence", "originNs", "value"}
    routed = B.ChassisZone().step(100, [("brake-request", value)])[0][1]
    assert C.EndpointBinding("brake-request", "chassis-zone", "brake-esc-node").consume(routed, received_producer="chassis-zone") == routed
    value["state"] = "NOMINAL"
    with pytest.raises(C.ContractError):
        direct.consume(value, received_producer="functional-arbiter")


def test_wp13_three_member_perception_provenance_is_preserved():
    value = dict(schema="assured-aeb.perception-output/1", source="perception", frame=1, frameSha256="a"*64, originNs=100,
                 occupancyProbability=0.8, binProbabilities=[0.8, 0.2], predictedBin="bin-0", oodScore=0.2, oodFlag=False,
                 inputQuality={}, provenance={"modelDigest":"b"*64, "preprocessParamsSha256":"c"*64, "postprocessSha256":"d"*64}, state="NOMINAL", reason=None)
    binding = C.EndpointBinding("perception-output", "perception", "fusion-risk-aeb")
    assert binding.consume(value, received_producer="perception")["provenance"] == value["provenance"]
    value["provenance"]["newRuntimeField"] = "e"*64
    with pytest.raises(C.ContractError):
        binding.consume(value, received_producer="perception")


def test_generated_role_schema_descriptions_match_the_runtime_definitions():
    for name in BODIES:
        if name != "gate-state":
            assert json.loads((HERE / "schemas/roles" / (name+".schema.json")).read_text()) == C.schema_document(name)
    assert json.loads((HERE / "schemas/roles/wire-aliases.json").read_text()) == {k:list(v) for k,v in C.URN_TO_SCHEMAS.items()}


def test_runtime_contract_and_writer_import_no_offline_or_evaluation_source():
    forbidden = ("topology", "protocol", "oracle", "perception", "fault", "role_event_join")
    for name in ("role_contract", "role_events"):
        tree = ast.parse((HERE / "assured_aeb" / (name+".py")).read_text())
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not any(part in module for part in forbidden for module in imports)
