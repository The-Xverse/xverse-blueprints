"""Offline tests of the WP-04 brake/ESC software-status node, chassis zone and gateway reader (no run, no CARLA).

The window and latency values below are TEST VALUES chosen for the tests only; the protocol values are TODO
(AD-06, AD-07, AD-30) and have no default.
"""

from __future__ import annotations

import pytest

from assured_aeb import brake_esc as B
import topology as T

MS = 1_000_000
TEST_WINDOW_NS = 100 * MS  # test value, not a protocol value
TEST_LATENCY_NS = 0  # test value


def node(window=TEST_WINDOW_NS, latency=TEST_LATENCY_NS):
    return B.BrakeEscNode(B.BrakeNodeParams.from_record({"schema": B.NODE_PARAMS, "stalenessWindowNs": window,
                                                         "computeLatencyNs": latency}))


def reader(window=TEST_WINDOW_NS, origin_ns=0):
    r = B.BrakeCommandReader(B.ReaderParams.from_record({"schema": B.READER_PARAMS, "stalenessWindowNs": window}))
    if origin_ns is not None:
        r.bind_origin(origin_ns)
    return r


def routed(sequence, origin_ns, value, now_ns=None):
    """An arbiter request routed by the chassis zone."""

    out = B.ChassisZone().step(now_ns if now_ns is not None else origin_ns, [("brake-request", B.brake_request(sequence, origin_ns, value))])
    assert len(out) == 1 and out[0][0] == B.NODE
    return out[0][1]


def statuses(result):
    return [(s["status"], s["reason"]) for s in result["status"]]


# ---- parameters: no defaults ------------------------------------------------------------------------------------

@pytest.mark.parametrize("record", [
    None, {}, {"schema": B.NODE_PARAMS}, {"schema": B.NODE_PARAMS, "stalenessWindowNs": 1},
    {"schema": B.NODE_PARAMS, "stalenessWindowNs": 0, "computeLatencyNs": 0},
    {"schema": B.NODE_PARAMS, "stalenessWindowNs": 1.5, "computeLatencyNs": 0},
    {"schema": B.NODE_PARAMS, "stalenessWindowNs": 1, "computeLatencyNs": -1},
    {"schema": B.NODE_PARAMS, "stalenessWindowNs": 1, "computeLatencyNs": 0, "extra": 1},
    {"schema": "other", "stalenessWindowNs": 1, "computeLatencyNs": 0},
])
def test_node_parameters_have_no_default(record):
    with pytest.raises(ValueError):
        B.BrakeNodeParams.from_record(record)


def test_node_and_reader_refuse_construction_without_a_record():
    with pytest.raises(TypeError):
        B.BrakeEscNode(None)
    with pytest.raises(TypeError):
        B.BrakeCommandReader(None)
    with pytest.raises(ValueError):
        B.ReaderParams.from_record({"schema": B.READER_PARAMS})


# ---- state machine ----------------------------------------------------------------------------------------------

def test_valid_request_is_received_accepted_and_forwarded_at_its_simulation_time():
    n = node(latency=5 * MS)
    result = n.step(1_000 * MS, [routed(1, 990 * MS, 0.8)])
    assert statuses(result) == [("received", None), ("accepted", None), ("forwarded", None)]
    assert all(s["atNs"] == 1_000 * MS for s in result["status"])  # the AD-14 acceptance time, in simulation time
    (command,) = result["commands"]
    assert command["value"] == 0.8 and command["requestSequence"] == 1 and command["requestOriginNs"] == 990 * MS
    assert command["originNs"] == 1_005 * MS  # forwarding time plus the declared compute latency


def test_zero_request_is_accepted_and_forwarded_as_a_release():
    result = node().step(10 * MS, [routed(1, 10 * MS, 0.0)])
    assert statuses(result)[-1] == ("forwarded", None) and result["commands"][0]["value"] == 0.0


@pytest.mark.parametrize("value", [-0.01, 1.01, 2.0])
def test_out_of_range_is_rejected_not_clamped(value):
    result = node().step(10 * MS, [routed(1, 10 * MS, value)])
    assert statuses(result) == [("received", None), ("rejected", "out-of-range")] and result["commands"] == []


@pytest.mark.parametrize("origin_ns, now_ns, rejected", [
    (0, TEST_WINDOW_NS, False),  # exactly the window: fresh
    (0, TEST_WINDOW_NS + 1, True),  # older than the window: stale
    (20 * MS, 10 * MS, True),  # a future origin: stale
])
def test_staleness_in_simulation_time(origin_ns, now_ns, rejected):
    result = node().step(now_ns, [routed(1, origin_ns, 1.0, now_ns=now_ns)])
    assert (("rejected", "stale") in statuses(result)) is rejected


def test_wrong_source_is_rejected():
    request = routed(1, 10 * MS, 1.0)
    for bad in (dict(request, source="proposer"), dict(request, route=["safety-gate", B.CHASSIS])):
        assert ("rejected", "wrong-source") in statuses(node().step(10 * MS, [bad]))


def test_replayed_and_out_of_order_sequences_are_rejected():
    n = node()
    n.step(10 * MS, [routed(5, 10 * MS, 1.0)])
    assert ("rejected", "replayed") in statuses(n.step(20 * MS, [routed(5, 20 * MS, 1.0)]))
    assert ("rejected", "replayed") in statuses(n.step(30 * MS, [routed(4, 30 * MS, 1.0)]))
    assert statuses(n.step(40 * MS, [routed(6, 40 * MS, 1.0)]))[-1] == ("forwarded", None)


@pytest.mark.parametrize("bad", [None, 3, {}, {"schema": B.REQUEST}, "brake"])
def test_malformed_requests_are_rejected(bad):
    result = node().step(10 * MS, [bad])
    assert statuses(result) == [("received", None), ("rejected", "malformed")]


def test_non_number_value_is_malformed():
    request = routed(1, 10 * MS, 1.0)
    for value in (float("nan"), True, "1", None):
        assert ("rejected", "malformed") in statuses(node().step(10 * MS, [dict(request, value=value)]))


def test_requests_of_one_step_are_processed_in_sequence_order():
    result = node().step(10 * MS, [routed(2, 10 * MS, 0.5), routed(1, 10 * MS, 1.0)])
    assert [c["requestSequence"] for c in result["commands"]] == [1, 2]


def test_simulation_time_must_be_integer_nanoseconds():
    with pytest.raises(ValueError):
        node().step(0.5, [])


# ---- V26: only the node's own software status --------------------------------------------------------------------

def test_every_published_message_is_in_the_declared_vocabulary():
    n = node()
    n.step(10 * MS, [routed(1, 10 * MS, 1.0), routed(2, 10 * MS, 7.0), None])
    assert n.evidence and all(B.check_vocabulary(m) == [] for m in n.evidence)
    published = {key for m in n.evidence for key in m}
    for forbidden in ("wheelSpeed", "wheelSpeedMps", "applied", "brakeApplied", "pressure", "deceleration"):
        assert forbidden not in published


@pytest.mark.parametrize("mutation", [{"wheelSpeedMps": 3.0}, {"applied": True}, {"status": "applied"}, {"node": "other"}])
def test_vocabulary_check_rejects_undeclared_content(mutation):
    status = node().step(10 * MS, [routed(1, 10 * MS, 1.0)])["status"][0]
    assert B.check_vocabulary(dict(status, **mutation))


def test_injected_fault_is_reserved_and_never_emitted():
    n = node()
    n.step(10 * MS, [routed(1, 10 * MS, 1.0), routed(2, 10 * MS, -1.0)])
    assert "injected-fault" in B.STATUSES
    assert all(m.get("status") != "injected-fault" for m in n.evidence)


# ---- chassis zone ---------------------------------------------------------------------------------------------

def test_chassis_zone_routes_only_the_arbiters_request_and_forwards_motion():
    zone = B.ChassisZone()
    motion = {"flowId": "motion-evidence", "originNs": 5}
    out = zone.step(10 * MS, [("brake-request", B.brake_request(1, 10 * MS, 1.0)),
                              ("brake-request", dict(B.brake_request(2, 10 * MS, 1.0), source="proposer")),
                              ("motion-evidence", motion), ("aeb-status", {"degraded": True}), ("brake-status", {"x": 1})])
    assert [d for d, _ in out] == [B.NODE, "vehicle-state"]
    assert out[0][1]["source"] == B.CHASSIS and out[0][1]["route"] == B.ROUTE and out[0][1]["receivedNs"] == 10 * MS
    assert out[0][1]["value"] == 1.0 and out[0][1]["sequence"] == 1 and out[1][1] is motion
    assert [e["kind"] for e in zone.evidence] == ["route-refused", "aeb-status", "brake-status"]


def test_chassis_zone_does_not_validate_value_or_staleness():
    out = B.ChassisZone().step(10 * MS, [("brake-request", B.brake_request(1, 0, 9.0))])
    assert out and out[0][1]["value"] == 9.0  # the node is the single check


def test_interfaces_match_the_wp12_topology():
    chassis = T.ELEMENTS["chassis-zone"]
    brake = T.ELEMENTS["brake-esc-node"]
    assert set(chassis[4]) == {"brake-request", "motion-evidence"} and set(brake[4]) == {"brake-command", "brake-status"}
    assert T.FLOWS["f17-brake-command"][:3] == ("brake-esc-node", "brake-command", "loop-gateway")
    assert "f17-brake-command" in T.HUB_DELAYED
    intra = {(p, i, c) for p, i, c, _ in T.INTRA}
    assert {("functional-arbiter", "brake-request", "chassis-zone"), ("chassis-zone", "brake-request", "brake-esc-node"),
            ("brake-esc-node", "brake-status", "chassis-zone")} <= intra


# ---- WP-03 reader (B-3) --------------------------------------------------------------------------------------

def test_reader_returns_zero_before_the_first_command():
    assert reader()(0.0) == 0.0


def test_reader_returns_the_fresh_value_and_zero_for_a_release():
    r, n = reader(), node()
    r.deliver(n.step(10 * MS, [routed(1, 10 * MS, 0.6)])["commands"][0])
    assert r(0.05) == 0.6  # 50 ms after the command: fresh under the test window
    r.deliver(n.step(60 * MS, [routed(2, 60 * MS, 0.0)])["commands"][0])
    assert r(0.07) == 0.0


def test_reader_returns_none_when_stale_or_lost():
    r, n = reader(), node()
    r.deliver(n.step(10 * MS, [routed(1, 10 * MS, 1.0)])["commands"][0])
    assert r((10 * MS + TEST_WINDOW_NS + 1) / 1e9) is None
    r2 = reader()
    r2.deliver(node().step(10 * MS, [routed(1, 10 * MS, 1.0)])["commands"][0])
    r2.mark_lost()
    assert r2(0.02) is None


def test_reader_refuses_older_or_nonconforming_commands():
    r, n = reader(), node()
    first = n.step(10 * MS, [routed(1, 10 * MS, 1.0)])["commands"][0]
    second = n.step(20 * MS, [routed(2, 20 * MS, 0.3)])["commands"][0]
    r.deliver(second)
    r.deliver(first)
    r.deliver(dict(second, sequence=99, wheelSpeedMps=1.0))
    assert r(0.03) == 0.3 and r.refused == 2


def test_offline_chain_arbiter_to_reader_matches_the_wp03_contract():
    """Arbiter request -> chassis zone -> node -> F17 (one hub step later) -> reader -> WP-03 brake_request."""

    zone, n, r = B.ChassisZone(), node(), reader()
    step_ns = 50 * MS  # test step
    hub = []  # F17 commands awaiting the one-step hub delay
    seen = []
    for k, value in enumerate([0.0, 0.0, 1.0, 1.0, 0.0]):
        now = k * step_ns
        for command in hub:
            r.deliver(command)
        hub = []
        seen.append(r(now / 1e9))
        routed_requests = [m for d, m in zone.step(now, [("brake-request", B.brake_request(k + 1, now, value))]) if d == B.NODE]
        hub.extend(n.step(now, routed_requests)["commands"])
    assert seen == [0.0, 0.0, 0.0, 1.0, 1.0]  # each request reaches the driver one hub step later
    assert all(isinstance(v, float) for v in seen)  # never None while the chain is fresh


# ---- finding 4: time base (HIGH-1) -------------------------------------------------------------------------

WORLD_NS = 1_000 * 1_000 * MS  # a world clock at 1000 s at the episode's first frame (test value)


def test_origin_binds_once_and_refuses_a_different_value():  # finding 7, MEDIUM-A
    r = reader(origin_ns=None)
    for bad in (None, 1.5, -1, True):
        with pytest.raises(ValueError):
            r.bind_origin(bad)
    r.bind_origin(WORLD_NS)
    r.bind_origin(WORLD_NS)  # idempotent
    with pytest.raises(ValueError):
        r.bind_origin(WORLD_NS + 1)


def test_unbound_origin_serves_zero_without_a_command_and_none_with_one():
    r, n = reader(origin_ns=None), node()
    assert r(0.0) == 0.0
    r.deliver(n.step(WORLD_NS, [routed(1, WORLD_NS, 1.0)])["commands"][0])
    assert r(0.0) is None  # a command is held, the time base is unknown
    r.bind_origin(WORLD_NS)
    assert r(0.0) == 1.0


def test_lite_vehicle_loop_order_driver_before_first_frame():
    """compat LiteVehicleLoop.run (855878a, live/loop.py 83-115): the driver is called at tick 0 with sim_s 0.0 before the
    first frame; the first frame then sets episode_ns, and the U2 loop binds the reader's origin from it."""

    zone, n, r = B.ChassisZone(), node(), reader(origin_ns=None)
    step_ns = 50 * MS  # test step
    frames = [WORLD_NS + k * step_ns for k in range(6)]
    requests = [0.0, 0.0, 1.0, 1.0, 1.0, 0.0]
    sim_s, episode_ns, hub, seen = 0.0, None, [], []
    for tick, frame_ns in enumerate(frames):
        for command in hub:
            r.deliver(command)
        hub = []
        seen.append(r(sim_s))  # command_source(sim_s, last_motion) comes first in each tick
        if episode_ns is None:
            episode_ns = frame_ns
            r.bind_origin(frame_ns)  # the first frame of the episode
        sim_s = (frame_ns - episode_ns) / 1e9
        routed_requests = [m for d, m in zone.step(frame_ns, [("brake-request", B.brake_request(tick + 1, frame_ns, requests[tick]))])
                           if d == B.NODE]
        hub.extend(n.step(frame_ns, routed_requests)["commands"])
    assert seen[0] == 0.0  # tick 0: no command, origin unbound
    assert seen == [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]  # the frame-k request reaches the driver at tick k+1 (one hub step)


def test_stale_command_is_refused_with_a_non_zero_world_epoch():
    """Before the repair this returned 1.0: the absolute origin was compared with the episode-relative time."""

    r, n = reader(origin_ns=WORLD_NS), node()
    r.deliver(n.step(WORLD_NS + 50 * MS, [routed(1, WORLD_NS + 50 * MS, 1.0)])["commands"][0])
    assert r(0.1) == 1.0  # 50 ms old: fresh
    assert r(10.1) is None  # 10 s old: stale


def test_future_origin_is_not_deliverable():
    r, n = reader(origin_ns=WORLD_NS), node()
    r.deliver(n.step(WORLD_NS + 500 * MS, [routed(1, WORLD_NS + 500 * MS, 1.0)])["commands"][0])
    assert r(0.1) is None  # the command's origin is 400 ms in the reader's future


def test_offline_chain_with_a_non_zero_world_epoch():
    zone, n, r = B.ChassisZone(), node(), reader(origin_ns=WORLD_NS)
    step_ns = 50 * MS  # test step
    hub, seen = [], []
    for k, value in enumerate([0.0, 0.0, 1.0, 1.0, 0.0]):
        world = WORLD_NS + k * step_ns
        for command in hub:
            r.deliver(command)
        hub = []
        seen.append(r(k * step_ns / 1e9))  # WP-03 passes episode-relative seconds
        routed_requests = [m for d, m in zone.step(world, [("brake-request", B.brake_request(k + 1, world, value))]) if d == B.NODE]
        hub.extend(n.step(world, routed_requests)["commands"])
    assert seen == [0.0, 0.0, 0.0, 1.0, 1.0]
    # the U5 side goes silent (for example the CC-1 freeze): after one window the source is invalid, not a stale 0.0
    assert r((4 * step_ns + TEST_WINDOW_NS + 1) / 1e9) is None
