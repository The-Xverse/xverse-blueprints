"""WP-14a ED-12 with real accepted Argus writers/readers, no simulation.

All message values and event sequences are TEST-ONLY fixtures. The byte cap is
Argus's existing engineering max_payload_bytes, not a scientific threshold.
"""
from __future__ import annotations

import copy

import pytest

import check_topology as T
from assured_aeb import role_contract as C
from assured_aeb import role_events as E
from assured_aeb.role_event_join import join_role_events
from test_role_contract import record

ROLES = {"vehicle-loop": ("mrc-sink",), "adas-hpc": ("proposer", "goal-interpreter"),
         "vc-functional": ("fixed-fallback-supervisor", "configuration-manager", "transition-verifier", "brake-esc-node", "functional-arbiter"),
         "vc-assurance": ("safety-monitor", "safety-gate")}
PLACE = {role: unit for unit, roles in ROLES.items() for role in roles}
BINDINGS = dict(proposalId="p1", authorizationId="auth1", assessmentRef="a1", commandId="c1", transitionId="t1", requestId="m1", goalId="g1", objectiveId="o1", preemptedTransitionId="old-t1", preemptingCommandId="new-c1")


@pytest.fixture(scope="session")
def role_plan(schema_paths):
    validation, result = T.compile_docs(T.load("mloc", "topology"), schema_paths)
    assert validation.is_valid and result.is_valid
    return result.plan


@pytest.fixture
def opened(tmp_path, role_plan):
    from xverse.argus import EvidenceLimits, EvidenceStore
    runs = {}
    def open_unit(unit, *, selected_roles=None, admitted_plan=None):
        root = tmp_path / unit
        writer = EvidenceStore.open_run(root, run_id="argus-roles-"+unit, plan=admitted_plan if admitted_plan is not None else role_plan,
                                        clocks={"simulation": {"domain": "carla-simulation", "unit": "ns", "value": 0}})
        runs[unit] = (root, writer, None)
        adapter = E.RoleEvents(writer, unit=unit, roles=selected_roles if selected_roles is not None else ROLES[unit], clock_domain="carla-simulation",
                               maximum_record_bytes=EvidenceLimits().max_payload_bytes)
        runs[unit] = (root, writer, adapter)
        return adapter
    yield open_unit, runs
    for _, writer, _ in runs.values():
        if writer.writer_state == "open":
            writer.abort(reason="test-fixture cleanup")


def emit(adapter, role, kind, *, body=None, bindings=None, cause=None, refs=None):
    body = body if body is not None else {"test-kind": kind}
    return adapter.emit(role=role, kind=kind, bindings=bindings if bindings is not None else {k:BINDINGS[k] for k in E.KINDS[kind][1]},
                        sim_ns=100, step=1, configuration="C_NOMINAL", outcome="test-recorded", reason=None,
                        payload_sha256=E.payload_digest(body), source_refs=refs if refs is not None else [], causation_id=cause)


def close_and_read(runs):
    from xverse.argus import EvidenceStore
    result = {}
    for unit, (root, writer, _) in runs.items():
        writer.finalize()
        result[unit] = EvidenceStore.read_run(root).records()
    return result


def test_every_declared_event_kind_writes_genuine_argus_records_with_local_chains(opened):
    open_unit, runs = opened
    adapters = {unit:open_unit(unit) for unit in ROLES}
    for kind, (roles, _) in E.KINDS.items():
        role = sorted(roles)[0]
        emit(adapters[PLACE[role]], role, kind)
    records = close_and_read(runs)
    assert {r["extensions"][E.EXTENSION]["kind"] for rs in records.values() for r in rs} == set(E.KINDS)
    for unit, rs in records.items():
        assert "causationId" not in rs[0]
        assert all(b["causationId"] == a["eventId"] for a, b in zip(rs, rs[1:]))
        assert all(r["extensions"][E.EXTENSION]["unit"] == unit for r in rs)
        assert all(set(r["extensions"][E.EXTENSION]) == {"version", "role", "unit", "kind", "bindings", "simNs", "step", "configuration", "outcome", "reason", "payloadSha256", "sourceRefs"} for r in rs)
        assert not any(key in r["extensions"][E.EXTENSION] for r in rs for key in ("pixels", "payload", "rawBytes"))
    join_role_events(records)


def test_actual_proposal_assessment_authorization_transition_records_join_across_three_units(opened):
    open_unit, runs = opened
    u4, u6, u5 = (open_unit(unit) for unit in ("adas-hpc", "vc-assurance", "vc-functional"))
    proposal, assessment, authorization, transition, verdict = (record(name) for name in ("proposal", "assessment", "authorization", "transition-request", "transition-verdict"))
    def ref(identifier, message):
        return {"messageId":identifier, "sha256":E.payload_digest(message)}
    emit(u4, "proposer", "proposal-created", body=proposal, bindings={"proposalId":"p1", "goalId":"g1", "objectiveId":"o1"})
    emit(u6, "safety-gate", "proposal-received", body=proposal, bindings={"proposalId":"p1"}, refs=[ref("p1", proposal)])
    emit(u6, "safety-monitor", "assessment", body=assessment, bindings={"proposalId":"p1", "assessmentRef":"a1"})
    emit(u6, "safety-gate", "authorization", body=authorization, bindings={"proposalId":"p1", "assessmentRef":"a1", "authorizationId":"auth1"}, refs=[ref("p1",proposal), ref("a1",assessment)])
    emit(u5, "configuration-manager", "transition-requested", body=transition, bindings={"proposalId":"p1", "authorizationId":"auth1", "transitionId":"t1"}, refs=[ref("auth1",authorization)])
    emit(u5, "transition-verifier", "verification-outcome", body=verdict, bindings={"transitionId":"t1"}, refs=[ref("t1",transition)])
    joined = join_role_events(close_and_read(runs))
    assert {e["unit"] for e in joined[("proposalId","p1")]} == {"adas-hpc","vc-assurance","vc-functional"}
    assert [e["kind"] for e in joined[("transitionId","t1")]] == ["transition-requested","verification-outcome"]


def test_u2_passive_receipt_joins_u5_by_request_id_and_digest_without_cross_run_causation(opened):
    open_unit, runs = opened
    sink, supervisor = open_unit("vehicle-loop"), open_unit("vc-functional")
    request = record("mrc-request")
    emit(supervisor,"fixed-fallback-supervisor","mrc-request",body=request)
    emit(sink,"mrc-sink","mrc-request-received",body=request,refs=[{"messageId":"m1","sha256":E.payload_digest(request)}])
    joined = join_role_events(close_and_read(runs))
    assert {e["unit"] for e in joined[("mrc-request","m1",E.payload_digest(request))]} == {"vehicle-loop","vc-functional"}


def test_duplicate_writer_claim_and_foreign_or_invented_causal_roots_are_refused(opened):
    open_unit, runs = opened
    events = open_unit("vc-assurance")
    with pytest.raises(C.ContractError, match="already claimed"):
        E.RoleEvents(runs["vc-assurance"][1],unit="vc-assurance",roles=ROLES["vc-assurance"],clock_domain="carla-simulation",maximum_record_bytes=1024)
    for cause in ("foreign-run.event1", "fabricated-root"):
        with pytest.raises(C.ContractError, match="acknowledged prior"):
            emit(events,"safety-gate","gate-state",cause=cause)
    assert events.event_ids == []
    first = emit(events,"safety-gate","gate-state")
    assert emit(events,"safety-gate","gate-state",cause=first)


def test_comparator_role_fixture_never_opens_an_absent_u6(opened, schema_paths):
    open_unit, runs = opened
    validation, result = T.compile_docs(T.load("comparator", "topology"), schema_paths)
    assert validation.is_valid and result.is_valid
    local_roles = {"vehicle-loop": ("mrc-sink",), "adas-hpc": ("perception", "fusion-risk-aeb"),
                   "vc-functional": ROLES["vc-functional"]}
    for unit, roles in local_roles.items():
        open_unit(unit, selected_roles=roles, admitted_plan=result.plan)
    assert "vc-assurance" not in runs and len(runs)==3
    assert not {"proposer", "goal-interpreter"} & runs["adas-hpc"][2].roles


def test_source_reference_shape_and_record_byte_cap_are_enforced_before_append(opened):
    open_unit, runs = opened
    events = open_unit("vehicle-loop")
    with pytest.raises(C.ContractError, match="source references"):
        emit(events,"mrc-sink","mrc-request-received",refs=[{"messageId":"m1","sha256":"a"*64,"pixels":"not-admitted"}])
    events.maximum_record_bytes = 1  # TEST-ONLY denial bound, not a protocol value
    with pytest.raises(C.ContractError, match="engineering byte bound"):
        emit(events,"mrc-sink","mrc-request-received")
    assert events.sequence==0 and events.event_ids==[]


def test_append_boundary_failure_poisoning_prevents_automatic_replay(opened, monkeypatch):
    open_unit, runs = opened
    events = open_unit("vehicle-loop")
    writer = runs["vehicle-loop"][1]
    calls=[]
    def fail(**kwargs):
        calls.append(kwargs)
        raise OSError("test-only append failure")
    monkeypatch.setattr(writer,"append_event",fail)
    with pytest.raises(OSError):
        emit(events,"mrc-sink","mrc-request-received")
    with pytest.raises(C.ContractError,match="cannot be retried"):
        emit(events,"mrc-sink","mrc-request-received")
    assert len(calls)==1 and events.event_ids==[]


def test_offline_join_rejects_foreign_local_causation(opened):
    open_unit, runs = opened
    emit(open_unit("vc-assurance"),"safety-gate","gate-state")
    records = close_and_read(runs)
    records["vc-assurance"][0]["causationId"]="another-run.event1"
    with pytest.raises(C.ContractError,match="foreign"):
        join_role_events(records)


def test_equal_request_ids_with_different_payload_digests_never_form_a_strict_mrc_join(opened):
    open_unit, runs = opened
    request = record("mrc-request")
    emit(open_unit("vc-functional"),"fixed-fallback-supervisor","mrc-request",body=request)
    changed = dict(request, reason="different-test-reason")
    emit(open_unit("vehicle-loop"),"mrc-sink","mrc-request-received",body=changed)
    joined = join_role_events(close_and_read(runs))
    assert len(joined[("mrc-request","m1",E.payload_digest(request))]) == 1
    assert len(joined[("mrc-request","m1",E.payload_digest(changed))]) == 1


def test_writer_requires_explicit_matching_clock_before_adapter_claim(tmp_path, role_plan):
    from xverse.argus import EvidenceLimits, EvidenceStore
    for index, clocks in enumerate((None, {"simulation": {"domain": "test-other-domain", "unit": "ns", "value": 0}})):
        writer = EvidenceStore.open_run(tmp_path / str(index), run_id="argus-roles-vehicle-loop", plan=role_plan, clocks=clocks)
        try:
            for _ in range(2):
                with pytest.raises(C.ContractError, match="simulator clock must be declared"):
                    E.RoleEvents(writer, unit="vehicle-loop", roles=("mrc-sink",), clock_domain="carla-simulation",
                                 maximum_record_bytes=EvidenceLimits().max_payload_bytes)
        finally:
            writer.abort(reason="test-only mismatched clock cleanup")
    root = tmp_path / "matching"
    writer = EvidenceStore.open_run(root, run_id="argus-roles-vehicle-loop", plan=role_plan,
                                   clocks={"simulation": {"domain": "carla-simulation", "unit": "ns", "value": 0}})
    try:
        events = E.RoleEvents(writer, unit="vehicle-loop", roles=("mrc-sink",), clock_domain="carla-simulation",
                              maximum_record_bytes=EvidenceLimits().max_payload_bytes)
        emit(events, "mrc-sink", "mrc-request-received")
        writer.finalize()
        records = list(EvidenceStore.read_run(root).records())
        assert len(records) == 1
        assert records[0]["clocks"]["simulation"] == {"domain": "carla-simulation", "unit": "ns", "value": 100}
    finally:
        if writer.writer_state == "open":
            writer.abort(reason="test-only matching clock cleanup")
