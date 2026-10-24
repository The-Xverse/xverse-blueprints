"""WP-14e deterministic stdlib controls; all tokens/numbers/identities TEST-ONLY.

The recording writer is a test sink for the actual RoleEvents adapter, not a
claim of durable Argus storage. No inference/model/library service is started.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path
import unittest

from assured_aeb import role_contract as C
from assured_aeb import role_events as E
from assured_aeb import u4_untrusted as U
from assured_aeb import parameters as P
from assured_aeb import fusion_aeb as F
from assured_aeb import radar_zone as R


class RecordingWriter:
    run_id = "argus-roles-adas-hpc"
    writer_state = "open"
    declared_domains = ("carla-simulation",)
    def __init__(self):
        self.records, self.fail = [], False
    def append_event(self, **event):
        if self.fail:
            raise OSError("TEST-ONLY append failure")
        self.records.append(event)
        return len(self.records)


def projection(entries=None, **overrides):
    values = {name: 1_000 for name in U.DURATIONS}
    values["proposer.proposalValidityNs"] = 500
    values[U.MAPPINGS] = [{"objective": "test-return", "targetConfiguration": U.NOMINAL}]
    if entries is not None:
        values = entries
    values.update(overrides)
    return P.Projection(dict(schema=P.PROJECTION, protocolRecordSha256="a"*64, unit="adas-hpc", entries=values))


def roles(*, policy=None, capacity=100):
    writer = RecordingWriter()
    events = E.RoleEvents(writer, unit="adas-hpc", roles=["goal-interpreter", "proposer"], clock_domain="carla-simulation",
                          maximum_record_bytes=8_192)  # TEST-ONLY engineering byte cap
    policy = policy or U.U4Policy(projection())
    interpreter = U.GoalInterpreter(policy=policy, binding=C.EndpointBinding("objective", "objective-source", "goal-interpreter"),
                                  events=events, identity_prefix="test-u4", maximum_accepted_messages=capacity)
    proposer = U.DeterministicProposer(policy=policy, goal_binding=C.EndpointBinding("goal-model", "goal-interpreter", "proposer"),
        configuration_binding=C.EndpointBinding("configuration-state", "configuration-manager", "proposer"),
        basis_binding=C.EndpointBinding("proposal-basis", "fusion-risk-aeb", "proposer"), events=events,
        identity_prefix="test-u4", maximum_accepted_messages=capacity)
    return interpreter, proposer, writer


def objective(now=1_000, sequence=1, token="test-return", valid=50_000, identifier=None):
    identifier = identifier or "test-objective-"+str(sequence)
    return C.make_record("objective", source="objective-source", sequence=sequence, origin_ns=now,
                         objectiveId=identifier, objective=token, validUntilNs=valid)


def delivery(record, producer=None, identity=None):
    return U.Delivered(record, producer or record["source"], identity or "test-message-"+record["source"]+"-"+str(record["sequence"]))


def config(now=1_000, sequence=1, configuration=U.DEGRADED, phase="confirmed"):
    return C.make_record("configuration-state", source="configuration-manager", sequence=sequence, origin_ns=now,
                         configuration=configuration, transitionId="test-transition", phase=phase, committedAtNs=now)


def genuine_basis(now=1_000, sequence=1):
    # Actual productive fusion and actual U3 radar/zone, with synthetic TEST-ONLY inputs/parameters.
    values = {"vehicle.egoFrontM": 2.4, "radar.mountM": [2.0,0.0], "radar.closingSpeedSign": -1,
              "fusion.corridor.halfWidthM":1.5, "fusion.corridor.maxRangeM":80.0,
              "fusion.cameraFreshnessNs":1000, "fusion.radarFreshnessNs":1000,
              "fusion.occupancyThreshold":0.5, "fusion.distanceBinEdgesM":[10.0,20.0,40.0], "fusion.associationToleranceM":1.0,
              "aeb.distanceUncertaintyM":0.5, "aeb.speedUncertaintyMps":0.5, "aeb.latencyNs":100,
              "aeb.decelerationMps2":6.0, "aeb.marginM":1.0, "aeb.brakeLevel":1.0,
              "aeb.releaseSpeedMps":0.5, "aeb.releaseAbsentCycles":3}
    fusion = F.FusionRiskAeb(P.Projection(dict(schema=P.PROJECTION,protocolRecordSha256="b"*64,unit="adas-hpc",entries=values)))
    sensor = R.SmartRadar(R.SmartRadarParams.from_record({"schema":R.RADAR_CHECKS,
        "spec":{"rangeM":100.0,"horizontalFovDeg":30.0,"verticalFovDeg":10.0,"maxVelocityMps":100.0,"maxDetections":500},
        "thresholds":{"minCount":1,"maxCount":200}}),"radar-adas")
    zone = R.FrontZone(R.FrontZoneParams.from_record(dict(schema=R.FRONT_ZONE,cameraFreshnessWindowNs=1000,radarFreshnessWindowNs=1000)))
    item = dict(type="item",flowId="radar-adas",sequence=1,originNs=now,frame=1,value={"detections":[[0.0,0.0,40.0,-10.0]],"count":1})
    radar = dict(zone.step(now,[("smart-radar-evidence",sensor.step(now,item))]))["f08-radar-adas"]
    camera = dict(schema=F.PERCEPTION_OUTPUT,source="perception",frame=1,frameSha256="c"*64,originNs=now,
                  occupancyProbability=0.9,binProbabilities=[0.1,0.1,0.1,0.7],predictedBin="bin-2",oodScore=0.1,oodFlag=False,
                  inputQuality={},provenance={"modelDigest":"d"*64,"preprocessParamsSha256":"e"*64,"postprocessSha256":"f"*64},
                  state="NOMINAL",reason=None)
    for _ in range(sequence):
        result = fusion.step(now,radar=radar,perception=camera)
    assert result["state"]=="NOMINAL" and result["reason"] is None
    return result


def chain(interpreter, proposer, now=1_000, obj=None, configuration=None, basis=None):
    goal=interpreter.step(now,step=1,objectives=[delivery(obj or objective(now))])
    assert goal is not None
    proposal=proposer.step(now,step=1,goals=[delivery(goal)],configurations=[delivery(configuration or config(now))],
                           bases=[delivery(basis or genuine_basis(now))])
    return goal,proposal


def role_snapshot(role, writer):
    """Only mutable role/event state, so caller-contract refusal can prove zero effects."""
    result = {key: copy.deepcopy(getattr(role, key)) for key in ("sequence", "last_now", "last_step", "last_decision")}
    if isinstance(role, U.GoalInterpreter):
        result.update(current=copy.deepcopy(role.current), stream=copy.deepcopy(vars(role.stream)))
    else:
        result.update(cached=copy.deepcopy(role.cached), terminal=role.terminal,
                      streams={name: copy.deepcopy(vars(stream)) for name, stream in role.streams.items()})
    result.update(events=copy.deepcopy(writer.records), event_sequence=role.events.sequence,
                  event_ids=list(role.events.event_ids), poisoned=role.events.poisoned)
    return result


class U4UntrustedTests(unittest.TestCase):
    def test_genuine_typed_chain_has_only_nominal_candidate_and_actual_reference_events(self):
        interpreter,proposer,writer=roles()
        goal,proposal=chain(interpreter,proposer)
        self.assertEqual(len(interpreter.policy.targets),1)  # principal TEST-ONLY projection fixes exactly one token
        self.assertEqual(C.validate_record("proposal",proposal),proposal)
        self.assertEqual(proposal["target"],U.NOMINAL)
        self.assertEqual(proposal["fromConfiguration"],U.DEGRADED)
        self.assertEqual(set(proposal),set(C.BASE)|set(C.BODIES["proposal"]))
        event=writer.records[-1]
        self.assertNotIn("causation_id",event)
        payload=event["extensions"][E.EXTENSION]
        self.assertEqual(payload["kind"],"proposal-created")
        self.assertEqual(payload["bindings"],dict(proposalId=proposal["proposalId"],goalId=goal["goalId"],objectiveId=goal["objectiveId"]))
        self.assertEqual(payload["payloadSha256"],E.payload_digest(proposal))
        self.assertEqual({ref["messageId"] for ref in payload["sourceRefs"]},set(proposal["basisRefs"]))
        self.assertEqual(proposer.last_decision["reason"],"independent-authorization-still-required")

    def test_projection_is_own_unit_closed_detached_and_has_no_defaults(self):
        for key in U.IDENTIFIERS:
            p=projection();p.entries.pop(key)
            with self.assertRaises(ValueError): U.U4Policy(p)
        p=projection();p.entries["oracle.futureAnswer"]=1
        with self.assertRaises(ValueError): U.U4Policy(p)
        p=projection();p.record["unit"]="vc-assurance"
        with self.assertRaises(ValueError): U.U4Policy(p)
        p=projection();policy=U.U4Policy(p);p.entries[U.MAPPINGS][0]["targetConfiguration"]=None
        self.assertEqual(policy.targets["test-return"],U.NOMINAL)
        for value in (0,True,1.0,10**1000):
            p=projection();p.entries["proposer.proposalValidityNs"]=value
            with self.assertRaises(ValueError): U.U4Policy(p)

    def test_mappings_refuse_unknown_members_duplicates_natural_language_and_authority_targets(self):
        for mapping in ([],[{"objective":"test-return","targetConfiguration":U.NOMINAL,"authorize":True}],
                        [{"objective":"test-return","targetConfiguration":U.NOMINAL}]*2,
                        [{"objective":"please brake now","targetConfiguration":U.NOMINAL}],
                        [{"objective":"test-return","targetConfiguration":"S_MRC_REQUESTED"}],
                        [{"objective":"test-return","targetConfiguration":U.DEGRADED}]):
            with self.assertRaises(ValueError): U.U4Policy(projection(**{U.MAPPINGS:mapping}))

    def test_separate_intact_chain_hold_mapping_is_valid_and_generates_no_proposal(self):
        mappings=[{"objective":"test-return","targetConfiguration":U.NOMINAL},{"objective":"test-hold","targetConfiguration":None}]
        i,p,w=roles(policy=U.U4Policy(projection(**{U.MAPPINGS:mappings})))
        goal,proposal=chain(i,p,obj=objective(token="test-hold"))
        self.assertEqual(len(i.policy.targets),2)
        self.assertIsNone(goal["constraints"]["targetConfiguration"])
        self.assertIsNone(proposal);self.assertEqual(w.records,[])

    def test_rejected_objective_never_replaces_prior_goal_or_reaches_proposal(self):
        i,p,w=roles();goal,first=chain(i,p)
        bad=objective(1_001,2,token="test-unknown")
        self.assertIsNone(i.step(1_001,step=2,objectives=[delivery(bad)]))
        self.assertEqual(i.current,goal)
        proposal=p.step(1_001,step=2,bases=[delivery(genuine_basis(1_001,2))])
        self.assertIsNotNone(proposal)
        self.assertNotIn(delivery(bad).message_id,proposal["basisRefs"])
        events=[event["extensions"][E.EXTENSION] for event in w.records]
        self.assertEqual([e["kind"] for e in events],["proposal-created","rejection","proposal-created"])
        self.assertEqual(w.records[-1]["causation_id"],w.records[-2]["event_id"])

    def test_unknown_malformed_unauthorized_stale_future_expired_objectives_are_recorded(self):
        cases=[U.Delivered(objective(),"ivi","test-unauthorized"),delivery(objective(token="test-unknown")),
               delivery(objective(now=2_000)),delivery(objective(now=0)),delivery(objective(valid=999)),
               U.Delivered({"schema":"bad"},"objective-source","test-bad"),U.Delivered({"pixels":b"not-json"},"objective-source","test-bytes")]
        for incoming in cases:
            with self.subTest(incoming=incoming.message_id):
                i,p,w=roles();now=1_001 if incoming.payload.get("originNs")==0 else 1_000
                self.assertIsNone(i.step(now,step=1,objectives=[incoming]));self.assertIsNone(i.current)
                e=w.records[-1]["extensions"][E.EXTENSION]
                self.assertEqual((e["role"],e["kind"],e["outcome"]),("goal-interpreter","rejection","rejected"))
                if incoming.message_id=="test-bytes":self.assertEqual(e["sourceRefs"],[])

    def test_ambiguous_objectives_replay_redefinition_and_capacity_are_refused(self):
        i,p,w=roles(capacity=1);goal=i.step(1_000,step=1,objectives=[delivery(objective())])
        for step,(now,items) in enumerate(((1_001,[delivery(objective())]),
                          (1_002,[delivery(objective(1_002,4,identifier=goal["objectiveId"]))]),
                          (1_003,[delivery(objective(1_003,5))])), start=2):
            self.assertIsNone(i.step(now,step=step,objectives=items));self.assertEqual(i.current,goal)
        self.assertEqual(len(w.records),3)

    def test_future_stale_and_regressing_messages_invalidate_cache_without_reproposal(self):
        for stream in ("goal","configuration","basis"):
            for mutation in ("future","stale","regress","extra","producer","large-int"):
                with self.subTest(stream=stream,mutation=mutation):
                    i,p,w=roles();goal,first=chain(i,p)
                    rec={"goal":goal,"configuration":config(),"basis":genuine_basis()}[stream]
                    rec=copy.deepcopy(rec);rec["sequence"]=2
                    if mutation=="future":rec["originNs"]=2_000
                    elif mutation=="stale":rec["originNs"]=0
                    elif mutation=="regress":rec["sequence"]=1
                    elif mutation=="extra":rec["unexpected"]=True
                    elif mutation=="large-int":rec["originNs"]=10**1000
                    incoming=delivery(rec,producer="ivi" if mutation=="producer" else None)
                    args={"goal":"goals","configuration":"configurations","basis":"bases"}
                    kwargs={args[stream]:[incoming]}
                    if stream!="basis":kwargs["bases"]=[delivery(genuine_basis(1_001,2))]
                    self.assertIsNone(p.step(1_001,step=2,**kwargs));self.assertNotIn(stream,p.cached)
                    self.assertEqual(len(w.records),1)

    def test_terminal_nominal_and_provisional_configurations_never_produce_return(self):
        for configuration,phase in (("S_MRC_REQUESTED","confirmed"),(U.NOMINAL,"confirmed"),(U.DEGRADED,"applying")):
            i,p,w=roles();self.assertIsNone(chain(i,p,configuration=config(configuration=configuration,phase=phase))[1])
            self.assertEqual(w.records,[])

    def test_uncertain_and_internally_unqualified_basis_never_produce_candidate(self):
        for mutation in ("state","camera-state","failures","reason","missing-quality"):
            basis=genuine_basis()
            if mutation=="state":basis["state"]="UNCERTAIN"
            elif mutation=="camera-state":basis["sources"]["camera"]["state"]="UNCERTAIN"
            elif mutation=="failures":basis["sources"]["radar"]["failures"]=["test-stale"]
            elif mutation=="reason":basis["reason"]="no-input"
            else:basis["sources"]["camera"].pop("failures")
            i,p,w=roles();self.assertIsNone(chain(i,p,basis=basis)[1]);self.assertEqual(w.records,[])

    def test_freshness_and_objective_expiry_are_intersected_at_inclusive_boundaries(self):
        i,p,w=roles();goal,proposal=chain(i,p,obj=objective(valid=1_100))
        self.assertEqual(proposal["validUntilNs"],1_100)
        self.assertIsNotNone(p.step(1_100,step=2,bases=[delivery(genuine_basis(1_100,2))]))
        self.assertIsNone(p.step(1_101,step=3,bases=[delivery(genuine_basis(1_101,3))]))
        i,p,w=roles();goal,proposal=chain(i,p)
        self.assertEqual(proposal["validUntilNs"],1_500)
        self.assertIsNotNone(p.step(2_000,step=2,bases=[delivery(genuine_basis(2_000,2))]))
        self.assertIsNone(p.step(2_001,step=3,bases=[delivery(genuine_basis(2_001,3))]))

    def test_each_new_candidate_requires_a_new_basis_and_inputs_are_detached(self):
        i,p,w=roles();goal,proposal=chain(i,p)
        with self.assertRaises(C.ContractError):p.step(1_000,step=1)
        changed=config(1_001,2)
        self.assertIsNone(p.step(1_001,step=2,configurations=[delivery(changed)]))
        changed["configuration"]="S_MRC_REQUESTED"
        self.assertIsNotNone(p.step(1_002,step=3,bases=[delivery(genuine_basis(1_002,2))]))
        self.assertEqual(p.cached["configuration"][1]["configuration"],U.DEGRADED)

    def test_interpreting_an_aged_objective_never_renews_its_freshness(self):
        i,p,w=roles()
        goal,proposal=chain(i,p,obj=objective(now=500))
        self.assertEqual(goal["originNs"],1_000)
        self.assertEqual(goal["constraints"]["validUntilNs"],1_500)
        boundary=p.step(1_500,step=2,bases=[delivery(genuine_basis(1_500,2))])
        self.assertEqual(boundary["validUntilNs"],1_500)
        self.assertIsNone(p.step(1_501,step=3,bases=[delivery(genuine_basis(1_501,3))]))

    def test_terminal_receipt_latches_even_if_a_later_manager_record_contradicts_it(self):
        i,p,w=roles()
        self.assertIsNone(chain(i,p,configuration=config(configuration="S_MRC_REQUESTED"))[1])
        self.assertTrue(p.terminal)
        self.assertIsNone(p.step(1_001,step=2,configurations=[delivery(config(1_001,2))],
                                 bases=[delivery(genuine_basis(1_001,2))]))
        self.assertEqual(p.last_decision["reason"],"terminal-lockout")
        self.assertEqual(w.records,[])

    def test_spoofed_terminal_receipt_has_no_terminal_effect_and_capacity_is_explicit(self):
        i,p,w=roles();chain(i,p)
        spoof=delivery(config(1_001,2,configuration="S_MRC_REQUESTED"),producer="ivi")
        self.assertIsNone(p.step(1_001,step=2,configurations=[spoof],bases=[delivery(genuine_basis(1_001,2))]))
        self.assertFalse(p.terminal)
        self.assertIsNotNone(p.step(1_002,step=3,configurations=[delivery(config(1_002,2))],
                                    bases=[delivery(genuine_basis(1_002,3))]))
        i,p,w=roles(capacity=1);chain(i,p)
        self.assertIsNone(p.step(1_001,step=2,bases=[delivery(genuine_basis(1_001,2))]))
        self.assertEqual(len(w.records),1)

    def test_poisoned_evidence_append_returns_no_proposal_and_cannot_replay(self):
        i,p,w=roles();goal=i.step(1_000,step=1,objectives=[delivery(objective())]);w.fail=True
        with self.assertRaises(OSError):
            p.step(1_000,step=1,goals=[delivery(goal)],configurations=[delivery(config())],bases=[delivery(genuine_basis())])
        self.assertEqual(p.sequence,0);self.assertTrue(p.events.poisoned)
        with self.assertRaises(C.ContractError):p.step(1_001,step=2,bases=[delivery(genuine_basis(1_001,2))])
        self.assertEqual(p.sequence,0)

    def test_colliding_actual_message_ids_cannot_make_an_ambiguous_basis_reference(self):
        i,p,w=roles()
        obj=objective()
        goal=i.step(1_000,step=1,objectives=[delivery(obj)])
        collision=delivery(config(),identity=delivery(obj).message_id)
        self.assertIsNone(p.step(1_000,step=1,goals=[delivery(goal)],configurations=[collision],bases=[delivery(genuine_basis())]))
        self.assertEqual(p.last_decision["reason"],"ambiguous-basis-message-identities")
        self.assertEqual(p.last_decision["policySha256"],p.policy.sha256)
        self.assertEqual(w.records,[])

    def test_caller_clock_binding_and_goal_constraint_refusals(self):
        i,p,w=roles();goal,proposal=chain(i,p)
        for now,step in ((999,2),(1_001,0),(True,2),(1_001,False),(-1,2)):
            with self.assertRaises(C.ContractError):p.step(now,step=step)
        for update in ({"targetConfiguration":"S_MRC_REQUESTED"},{"authorize":True},{"validUntilNs":True}):
            i,p,w=roles();goal=i.step(1_000,step=1,objectives=[delivery(objective())]);goal["constraints"].update(update)
            self.assertIsNone(p.step(1_000,step=1,goals=[delivery(goal)],configurations=[delivery(config())],bases=[delivery(genuine_basis())]))
        with self.assertRaises(C.ContractError):
            U.GoalInterpreter(policy=U.U4Policy(projection()),binding=C.EndpointBinding("objective","ivi","goal-interpreter"),
                              events=i.events,identity_prefix="test",maximum_accepted_messages=10)

    def test_goal_duplicate_cycle_with_distinct_fresh_ids_has_no_effect_or_watermark_consumption(self):
        i,p,w=roles();first=i.step(1_000,step=1,objectives=[delivery(objective())])
        before=role_snapshot(i,w)
        for now,step in ((1_000,1),(1_001,1),(1_000,2)):
            incoming=delivery(objective(now,2))
            with self.assertRaisesRegex(C.ContractError,"strictly advancing"):
                i.step(now,step=step,objectives=[incoming])
            self.assertEqual(role_snapshot(i,w),before)
        second=i.step(1_002,step=2,objectives=[delivery(objective(1_002,2))])
        self.assertNotEqual(second["goalId"],first["goalId"])
        self.assertEqual((i.sequence,i.last_now,i.last_step),(2,1_002,2))

    def test_proposer_duplicate_cycle_with_new_genuine_basis_has_no_effect_or_second_event(self):
        i,p,w=roles();goal,first=chain(i,p)
        before=role_snapshot(p,w)
        for now,step in ((1_000,1),(1_001,1),(1_000,2)):
            incoming=delivery(genuine_basis(now,2))
            with self.assertRaisesRegex(C.ContractError,"strictly advancing"):
                p.step(now,step=step,bases=[incoming])
            self.assertEqual(role_snapshot(p,w),before)
        second=p.step(1_002,step=2,bases=[delivery(genuine_basis(1_002,2))])
        self.assertNotEqual(second["proposalId"],first["proposalId"])
        self.assertEqual(len(w.records),2)
        self.assertEqual((p.last_now,p.last_step),(1_002,2))

    def test_initial_empty_role_call_consumes_its_cycle_and_refusal_keeps_next_cycle_available(self):
        i,p,w=roles()
        for role in (i,p):
            self.assertIsNone(role.step(0,step=0))
            before=role_snapshot(role,w)
            with self.assertRaises(C.ContractError):role.step(0,step=0)
            self.assertEqual(role_snapshot(role,w),before)
        self.assertIsNotNone(i.step(1_000,step=1,objectives=[delivery(objective())]))
        self.assertIsNone(p.step(1_000,step=1))

    def test_ambiguous_objectives_at_bound_retain_every_real_id_digest_and_prior_goal(self):
        i,p,w=roles(capacity=2);first=i.step(1_000,step=1,objectives=[delivery(objective())])
        incoming=[delivery(objective(1_001,2)),delivery(objective(1_001,3))]
        stream_before=copy.deepcopy(vars(i.stream))
        self.assertIsNone(i.step(1_001,step=2,objectives=incoming))
        self.assertEqual(i.current,first);self.assertEqual(vars(i.stream),stream_before)
        self.assertEqual(len(w.records),2)
        for event,message in zip(w.records,incoming):
            payload=event["extensions"][E.EXTENSION]
            self.assertEqual((payload["kind"],payload["reason"]),("rejection","objective-batch-ambiguous"))
            self.assertEqual(payload["bindings"],{"objectiveId":message.payload["objectiveId"]})
            self.assertEqual(payload["sourceRefs"],[{"messageId":message.message_id,"sha256":E.payload_digest(message.payload)}])
            self.assertEqual(payload["payloadSha256"],E.payload_digest(message.payload))
        self.assertEqual(w.records[1]["causation_id"],w.records[0]["event_id"])
        # Rejected batch members did not consume accepted-message identities or sequence watermarks.
        self.assertIsNotNone(i.step(1_002,step=3,objectives=[incoming[0]]))

    def test_oversized_objective_batch_is_caller_refusal_before_clock_state_or_events(self):
        i,p,w=roles(capacity=2)
        incoming=[delivery(objective(1_000,n)) for n in (1,2,3)]
        before=role_snapshot(i,w)
        with self.assertRaisesRegex(C.ContractError,"member bound"):
            i.step(1_000,step=1,objectives=incoming)
        self.assertEqual(role_snapshot(i,w),before)
        # Exactly at the bound remains an admitted ambiguous batch with complete actual references.
        self.assertIsNone(i.step(1_000,step=1,objectives=incoming[:2]))
        self.assertEqual(len(w.records),2)

    def test_mixed_ambiguous_batch_never_invents_noncanonical_payload_references(self):
        i,p,w=roles(capacity=3)
        canonical=[delivery(objective(1_000,n)) for n in (1,2)]
        malformed=U.Delivered({"objectiveId":"must-not-be-invented","bytes":b"noncanonical"},"objective-source","test-malformed")
        self.assertIsNone(i.step(1_000,step=1,objectives=[canonical[0],malformed,canonical[1]]))
        payloads=[event["extensions"][E.EXTENSION] for event in w.records]
        self.assertEqual(len(payloads),3)
        self.assertEqual(payloads[1]["sourceRefs"],[]);self.assertEqual(payloads[1]["bindings"],{})
        self.assertEqual(payloads[1]["payloadSha256"],E.payload_digest({"role":"goal-interpreter","reason":"objective-batch-ambiguous"}))
        for payload,message in zip((payloads[0],payloads[2]),canonical):
            self.assertEqual(payload["sourceRefs"],[{"messageId":message.message_id,"sha256":E.payload_digest(message.payload)}])

    def test_ambiguous_batch_rejection_append_failure_propagates_and_poisoning_is_preserved(self):
        i,p,w=roles(capacity=2);w.fail=True
        incoming=[delivery(objective(1_000,n)) for n in (1,2)]
        with self.assertRaises(OSError):i.step(1_000,step=1,objectives=incoming)
        self.assertTrue(i.events.poisoned);self.assertEqual(w.records,[])
        self.assertIsNone(i.current);self.assertEqual(i.sequence,0)
        with self.assertRaises(C.ContractError):i.step(1_001,step=2,objectives=incoming)

    def test_later_ambiguous_rejection_append_failure_preserves_only_acknowledged_real_references(self):
        i,p,w=roles(capacity=2)
        incoming=[delivery(objective(1_000,n)) for n in (1,2)]
        append=w.append_event
        def fail_second(**event):
            if w.records:raise OSError("TEST-ONLY second append failure")
            return append(**event)
        w.append_event=fail_second
        with self.assertRaises(OSError):i.step(1_000,step=1,objectives=incoming)
        self.assertTrue(i.events.poisoned);self.assertEqual(len(w.records),1)
        payload=w.records[0]["extensions"][E.EXTENSION]
        self.assertEqual(payload["sourceRefs"],[{"messageId":incoming[0].message_id,"sha256":E.payload_digest(incoming[0].payload)}])
        self.assertIsNone(i.current);self.assertEqual(i.sequence,0)

    def test_ambiguous_member_references_respect_existing_event_byte_cap_without_fabricated_fallback(self):
        i,p,w=roles(capacity=2)
        incoming=[delivery(objective(identifier="test-"+"x"*9_000)),delivery(objective(sequence=2))]
        with self.assertRaisesRegex(C.ContractError,"engineering byte bound"):
            i.step(1_000,step=1,objectives=incoming)
        self.assertEqual(w.records,[]);self.assertFalse(i.events.poisoned)
        self.assertIsNone(i.current);self.assertEqual(i.sequence,0)

    def test_runtime_import_and_authority_boundary(self):
        source=Path(U.__file__).read_text();tree=ast.parse(source)
        imports=[node.module or "" for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names]
        for forbidden in ("protocol","projection_builder","topology","oracle","fault","torch","onnx","transformers","openai"):
            self.assertFalse(any(forbidden in name for name in imports))
        for forbidden in ("authorization", "selector-command", "brake-request", "forced-command"):
            self.assertNotIn('make_record("'+forbidden+'"',source)
