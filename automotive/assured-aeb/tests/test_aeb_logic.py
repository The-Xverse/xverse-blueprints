"""Offline tests of WP-13 increment #1: projection reader, AEB rule and latch, U4 fusion, U5 radar fallback and
functional arbiter (review-wp13-logic finding 1 §1.8; no CARLA, no run, no ML).

EVERY PARAMETER VALUE BELOW IS TEST-ONLY. The protocol values and identifiers are TODO (AD-05, AD-06, AD-07, AD-27;
D-1, D-2) and have no default. Radar messages are produced by the real U3 ``SmartRadar`` and ``FrontZone``
(``radar_zone.py``), so the consumers are tested on the genuine front-zone form.
"""

from __future__ import annotations

from model_output_fixture import model_binding

import ast
import copy
import hashlib
import json
import math
from pathlib import Path

import pytest

from assured_aeb import aeb_rule as A
from assured_aeb import brake_esc as B
from assured_aeb import fusion_aeb as F
from assured_aeb import parameters as P
from assured_aeb import radar_zone as R
from assured_aeb import vc_functional as V

HERE = Path(__file__).resolve().parents[1]
MS = 1_000_000
WORLD = 1_000_000 * MS  # an absolute world-clock origin (test value)
SHA = hashlib.sha256(b"protocol record (test)").hexdigest()

TEST_ONLY_ENTRIES = {
    "vehicle.egoFrontM": 2.4, "radar.mountM": [2.0, 0.0], "radar.closingSpeedSign": -1,
    "fusion.corridor.halfWidthM": 1.5, "fusion.corridor.maxRangeM": 80.0,
    "fusion.cameraFreshnessNs": 80 * MS, "fusion.radarFreshnessNs": 80 * MS,
    "fusion.occupancyThreshold": 0.5, "fusion.distanceBinEdgesM": [10.0, 20.0, 40.0], "fusion.associationToleranceM": 1.0,
    "aeb.distanceUncertaintyM": 0.5, "aeb.speedUncertaintyMps": 0.5, "aeb.latencyNs": 100 * MS, "aeb.decelerationMps2": 6.0,
    "aeb.marginM": 1.0, "aeb.brakeLevel": 1.0, "aeb.releaseSpeedMps": 0.5, "aeb.releaseAbsentCycles": 3,
    "fallback.corridor.halfWidthM": 1.5, "fallback.corridor.maxRangeM": 80.0, "fallback.radarFreshnessNs": 80 * MS,
    "fallback.vehicleStateFreshnessNs": 80 * MS, "fallback.oddMaxEgoSpeedMps": 15.0,
    "fallback.distanceUncertaintyM": 0.5, "fallback.speedUncertaintyMps": 0.5, "fallback.latencyNs": 100 * MS,
    "fallback.decelerationMps2": 6.0, "fallback.marginM": 1.0, "fallback.brakeLevel": 1.0, "fallback.releaseSpeedMps": 0.5,
    "fallback.releaseAbsentCycles": 3,
    "arbiter.requestFreshnessNs": 80 * MS, "arbiter.holdWindowNs": 100 * MS, "arbiter.mrcSource": "fallback-request",
}
RADAR_RECORD = {"schema": R.RADAR_CHECKS, "spec": {"rangeM": 100.0, "horizontalFovDeg": 30.0, "verticalFovDeg": 10.0,
                                                    "maxVelocityMps": 100.0, "maxDetections": 500},
                "thresholds": {"minCount": 1, "maxCount": 200}}  # configured spec; thresholds TEST-ONLY
ZONE_RECORD = {"schema": R.FRONT_ZONE, "cameraFreshnessWindowNs": 80 * MS, "radarFreshnessWindowNs": 80 * MS}  # TEST-ONLY


def projection(**changes):
    entries = copy.deepcopy(TEST_ONLY_ENTRIES)
    for key, value in changes.items():
        key = key.replace("__", ".")
        if value is None:
            entries.pop(key)
        else:
            entries[key] = value
    return P.Projection({"schema": P.PROJECTION, "protocolRecordSha256": SHA, "unit": "test-unit", "entries": entries})


class Radar:
    """Front-zone radar messages from the real U3 smart radar and front zone."""

    def __init__(self):
        self.radar = R.SmartRadar(R.SmartRadarParams.from_record(copy.deepcopy(RADAR_RECORD)), "radar-adas")
        self.zone = R.FrontZone(R.FrontZoneParams.from_record(dict(ZONE_RECORD)))
        self.sequence = 0

    def at(self, now_ns, detections, stream="f08-radar-adas"):
        self.sequence += 1
        item = {"type": "item", "flowId": "radar-adas", "sequence": self.sequence, "originNs": now_ns, "frame": 100 + self.sequence,
                "value": {"detections": detections, "count": len(detections)}}
        out = dict(self.zone.step(now_ns, [("smart-radar-evidence", self.radar.step(now_ns, item))]))
        return out[stream]


def perception(now_ns, probability=0.9, predicted="bin-0", ood=False, state="NOMINAL"):
    return {"schema": F.PERCEPTION_OUTPUT, "source": "perception", "frame": 7, "frameSha256": "a" * 64, "originNs": now_ns,
            "occupancyProbability": probability, "binProbabilities": [0.7, 0.1, 0.1, 0.1], "predictedBin": predicted,
            "oodScore": 0.1, "oodFlag": ood, "inputQuality": {"logical": "pass"},
            "provenance": {"modelDigest": "b" * 64, "preprocessParamsSha256": "c" * 64,
                           "postprocessSha256": model_binding().postprocess_sha256},
            "state": state, "reason": None}


NEAR = [[0.0, 0.0, 10.0, -12.0]]  # d = 2.0 + 10.0 - 2.4 = 9.6 m, v = 12 m/s: fires (TEST-ONLY geometry)
FAR = [[0.0, 0.0, 40.0, -10.0]]   # d = 39.6 m, v = 10 m/s: does not fire


# ---- projection ----------------------------------------------------------------------------------------------

def test_projection_reads_by_identifier_without_default():
    assert F.FusionRiskAeb(projection(), model_output_binding=model_binding()).values["aeb.marginM"] == 1.0
    with pytest.raises(ValueError, match="aeb.marginM: missing"):
        F.FusionRiskAeb(projection(aeb__marginM=None), model_output_binding=model_binding())


@pytest.mark.parametrize("key, value", [("aeb.brakeLevel", 0.0), ("aeb.brakeLevel", 1.5), ("radar.closingSpeedSign", 0),
                                        ("aeb.releaseAbsentCycles", 2.0), ("fusion.distanceBinEdgesM", [10.0, 10.0]),
                                        ("radar.mountM", [2.0]), ("aeb.decelerationMps2", 0.0), ("aeb.latencyNs", -1)])
def test_projection_refuses_wrong_kinds(key, value):
    with pytest.raises(ValueError, match=key.replace(".", r"\.")):
        F.FusionRiskAeb(projection(**{key.replace(".", "__"): value}), model_output_binding=model_binding())


def test_projection_refuses_non_finite_and_unconsumed_entries():
    with pytest.raises(ValueError):
        projection(aeb__marginM=math.nan)
    with pytest.raises(ValueError):
        V.FunctionalArbiter(projection(arbiter__mrcSource="adas"))
    p = projection()
    consumed = set(F.DECLARATION) | set(V.FALLBACK_DECLARATION) | set(V.ARBITER_DECLARATION)
    p.check_exact(consumed)
    with pytest.raises(ValueError, match="not consumed"):
        p.check_exact(F.DECLARATION)  # a U4-only consumer does not consume the U5 entries
    with pytest.raises(TypeError):
        F.FusionRiskAeb(dict(TEST_ONLY_ENTRIES), model_output_binding=model_binding())


# ---- states, radar qualification, corridor -------------------------------------------------------------------

def test_weakest_link_counts_unknown_as_uncertain():
    assert A.weakest("NOMINAL", "DEGRADED") == "DEGRADED"
    assert A.weakest("NOMINAL", "bogus") == "UNCERTAIN"
    assert A.weakest("UNSAFE", "UNCERTAIN") == "UNSAFE"


def test_radar_qualification_table():
    radar = Radar()
    good = radar.at(WORLD, FAR)
    assert A.qualify_radar(good, "f08-radar-adas", WORLD, 80 * MS).state == "NOMINAL"
    assert A.qualify_radar(good, "f09-radar-vc", WORLD, 80 * MS).failures == ("radar-message",)  # wrong stream
    assert "stale" in A.qualify_radar(good, "f08-radar-adas", WORLD + 81 * MS, 80 * MS).failures
    bad = copy.deepcopy(good)
    bad["checks"]["integrity"]["verdict"] = "fail"
    assert A.qualify_radar(bad, "f08-radar-adas", WORLD, 80 * MS).state == "UNCERTAIN"
    empty = Radar().at(WORLD, [])  # count 0 < minCount 1: a class (iii) failure
    view = A.qualify_radar(empty, "f08-radar-adas", WORLD, 80 * MS)
    assert view.state == "DEGRADED" and view.failures == ("sensor-statistical",)
    spoiled = copy.deepcopy(good)
    spoiled["payload"]["detections"] = [[0.0, 0.0, "x", 1.0]]
    assert "malformed-detections" in A.qualify_radar(spoiled, "f08-radar-adas", WORLD, 80 * MS).failures


def test_corridor_mount_offset_sign_and_ties():
    corridor = A.Corridor(2.4, (2.0, 0.0), 1.5, 80.0, -1)
    assert A.nearest_in_corridor(((0.0, 0.0, 10.0, -12.0),), corridor) == (0, pytest.approx(9.6), 12.0)
    lateral = math.atan2(1.6, 20.0)
    assert A.nearest_in_corridor(((0.0, lateral, math.hypot(20.0, 1.6), -5.0),), corridor) is None  # |y| = 1.6 > 1.5
    assert A.nearest_in_corridor(((0.0, 0.0, 0.3, 0.0),), corridor) is None  # behind the ego front (x - front < 0)
    assert A.nearest_in_corridor(((0.0, 0.0, 30.0, -5.0), (0.0, 0.0, 30.0, -9.0)), corridor)[0] == 0  # tie: lower index
    flipped = A.Corridor(2.4, (2.0, 0.0), 1.5, 80.0, 1)
    assert A.nearest_in_corridor(((0.0, 0.0, 10.0, -12.0),), flipped)[2] == -12.0


# ---- rule and latch ------------------------------------------------------------------------------------------

def rule(**changes):
    values = dict(distance_uncertainty_m=0.5, speed_uncertainty_mps=0.5, latency_ns=100 * MS, deceleration_mps2=6.0,
                  margin_m=1.0, brake_level=1.0, release_speed_mps=0.5, release_absent_cycles=3)
    values.update(changes)
    return A.Rule(**values)


def test_residual_boundary_widening_and_clamp():
    r = rule()
    d, v = 9.6, 12.0
    expected = (d - 0.5) - 12.5 * 0.1 - 12.5 ** 2 / 12.0 - 1.0
    assert r.residual(d, v) == pytest.approx(expected) and expected < 0
    boundary = 0.5 + 12.5 * 0.1 + 12.5 ** 2 / 12.0 + 1.0  # the d at which r == 0
    assert r.residual(boundary, v) == pytest.approx(0.0, abs=1e-12)
    assert rule(distance_uncertainty_m=0.0, speed_uncertainty_mps=0.0).residual(9.6, 12.0) > expected  # widening
    assert r.conservative(5.0, -3.0) == (4.5, 0.0)  # a receding target: v_c clamped at 0
    assert r.residual(5.0, -3.0) == pytest.approx(4.5 - 1.0)


def test_latch_sets_holds_and_releases():
    latch = A.Latch(rule())
    assert latch.decide(True, True, 12.5) == 1.0 and latch.latched
    assert latch.decide(True, False, 5.0) == 1.0  # present, not firing: held, count reset
    assert latch.decide(False, False, None) == 1.0 and latch.absent == 1
    assert latch.hold() == 1.0 and latch.absent == 1  # a no-input step neither counts nor releases
    assert latch.decide(True, False, 0.5) == 0.0 and not latch.latched  # conservative speed at the release speed
    latch.decide(True, True, 10.0)
    assert [latch.decide(False, False, None) for _ in range(3)] == [1.0, 1.0, 0.0]  # absent on 3 cycles


# ---- U4 fusion (R-1, R-6) ------------------------------------------------------------------------------------

def test_fusion_agree_fires_and_records():
    fusion, radar = F.FusionRiskAeb(projection(), model_output_binding=model_binding()), Radar()
    out = fusion.step(WORLD, radar=radar.at(WORLD, NEAR), perception=perception(WORLD))
    assert out["hypothesis"]["present"] and out["hypothesis"]["agreement"] == "agree" and out["fired"]
    assert out["brakeRequest"] == 1.0 and out["latched"] and out["state"] == "NOMINAL" and out["reason"] is None
    assert out["hypothesis"]["distanceM"] == pytest.approx(9.6) and out["hypothesis"]["closingSpeedMps"] == 12.0
    assert out["sources"]["camera"]["provenance"]["modelDigest"] == "b" * 64 and out["sources"]["radar"]["selectedDetection"] == 0
    assert out["paramsSha256"] == P.params_digest(fusion.values) and len(json.dumps(out)) < 65536


@pytest.mark.parametrize("camera, detections, agreement, state", [
    (dict(probability=0.9, predicted="bin-2"), NEAR, "camera-only", "UNCERTAIN"),  # the bin does not associate
    (dict(probability=0.9, predicted="bin-0"), [], "camera-only", "UNCERTAIN"),  # no radar corroboration
    (dict(probability=0.2), NEAR, "radar-only", "DEGRADED"),  # camera not positive
    (dict(probability=0.9, ood=True), NEAR, "radar-only", "DEGRADED"),  # OOD: not positive
    (dict(probability=0.2), [[0.0, 0.2, 30.0, 0.0]], "none", "NOMINAL"),  # in the radar FOV, y = 5.96 m: outside the corridor
])
def test_fusion_outcomes(camera, detections, agreement, state):
    fusion, radar = F.FusionRiskAeb(projection(), model_output_binding=model_binding()), Radar()
    out = fusion.step(WORLD, radar=radar.at(WORLD, detections), perception=perception(WORLD, **camera))
    assert out["hypothesis"]["agreement"] == agreement and not out["hypothesis"]["present"]
    assert out["brakeRequest"] == 0.0
    expected = state if detections else A.weakest(state, "DEGRADED")  # an empty radar frame is itself DEGRADED (count)
    assert out["state"] == expected


def test_association_tolerance_at_the_bin_edge():
    fusion, radar = F.FusionRiskAeb(projection(), model_output_binding=model_binding()), Radar()
    edge = [[0.0, 0.0, 10.0 + 2.4 - 2.0 + 0.99, -1.0]]  # d = 10.99: bin-0 [0, 10) widened by 1.0
    assert fusion.step(WORLD, radar=radar.at(WORLD, edge), perception=perception(WORLD))["hypothesis"]["agreement"] == "agree"
    fusion, radar = F.FusionRiskAeb(projection(), model_output_binding=model_binding()), Radar()
    beyond = [[0.0, 0.0, 10.0 + 2.4 - 2.0 + 1.01, -1.0]]
    assert fusion.step(WORLD, radar=radar.at(WORLD, beyond), perception=perception(WORLD))["hypothesis"]["agreement"] == "camera-only"


def test_fusion_unusable_sources():
    fusion = F.FusionRiskAeb(projection(), model_output_binding=model_binding())
    out = fusion.step(WORLD, radar=Radar().at(WORLD, NEAR))
    assert out["reason"] == "camera-unusable" and out["state"] == "UNCERTAIN" and out["brakeRequest"] == 0.0
    out = F.FusionRiskAeb(projection(), model_output_binding=model_binding()).step(WORLD, perception=perception(WORLD))
    assert out["reason"] == "radar-unusable" and out["state"] == "UNCERTAIN"
    out = F.FusionRiskAeb(projection(), model_output_binding=model_binding()).step(WORLD, radar=Radar().at(WORLD, NEAR), perception=perception(WORLD, state="UNCERTAIN"))
    assert out["reason"] == "camera-unusable"
    bad = perception(WORLD)
    bad["extra"] = 1
    out = F.FusionRiskAeb(projection(), model_output_binding=model_binding()).step(WORLD, radar=Radar().at(WORLD, NEAR), perception=bad)
    assert out["reason"] == "camera-unusable" and out["sources"]["camera"]["failures"] == ["perception-output-malformed"]


def test_fusion_pairs_adjacent_steps_within_freshness_and_not_beyond():
    fusion, radar = F.FusionRiskAeb(projection(), model_output_binding=model_binding()), Radar()
    fusion.step(WORLD, perception=perception(WORLD))
    out = fusion.step(WORLD + 50 * MS, radar=radar.at(WORLD + 50 * MS, NEAR))
    assert out["hypothesis"]["agreement"] == "agree" and out["cycle"] == 2
    out = fusion.step(WORLD + 150 * MS, radar=radar.at(WORLD + 150 * MS, NEAR))  # the camera is 150 ms old
    assert out["reason"] == "camera-unusable" and "stale" in out["sources"]["camera"]["failures"]


def test_no_input_step_keeps_the_brake_and_does_not_count():
    fusion, radar = F.FusionRiskAeb(projection(), model_output_binding=model_binding()), Radar()
    fusion.step(WORLD, radar=radar.at(WORLD, NEAR), perception=perception(WORLD))
    out = fusion.step(WORLD + 50 * MS)
    assert out["reason"] == "no-input" and out["state"] == "UNCERTAIN" and out["brakeRequest"] == 1.0 and out["cycle"] == 1
    assert fusion.latch.absent == 0 and out["sequence"] == 2
    idle = F.FusionRiskAeb(projection(), model_output_binding=model_binding()).step(WORLD)
    assert idle["brakeRequest"] == 0.0 and idle["reason"] == "no-input" and idle["cycle"] == 0


def test_fusion_latch_released_by_absence():
    fusion, radar = F.FusionRiskAeb(projection(), model_output_binding=model_binding()), Radar()
    fusion.step(WORLD, radar=radar.at(WORLD, NEAR), perception=perception(WORLD))
    values = []
    for k in range(1, 4):
        t = WORLD + k * 50 * MS
        values.append(fusion.step(t, radar=radar.at(t, NEAR), perception=perception(t, probability=0.1))["brakeRequest"])
    assert values == [1.0, 1.0, 0.0]  # radar-only is not present (R-1): three absent cycles release


# ---- U5 radar fallback ---------------------------------------------------------------------------------------

def speed(now_ns, mps, state="NOMINAL"):
    return {"speedMps": mps, "originNs": now_ns, "state": state}


def test_fallback_fires_within_the_degraded_odd():
    out = V.RadarFallback(projection()).step(WORLD, radar=Radar().at(WORLD, NEAR, "f09-radar-vc"), ego_speed=speed(WORLD, 12.0))
    assert out["fired"] and out["brakeRequest"] == 1.0 and out["state"] == "NOMINAL" and out["hypothesis"]["agreement"] == "radar-only"


@pytest.mark.parametrize("ego, reason, state", [(lambda t: speed(t, 15.5), "outside-degraded-odd", "UNSAFE"),
                                                (lambda t: None, "ego-speed-unknown", "UNCERTAIN"),
                                                (lambda t: speed(t - 81 * MS, 12.0), "ego-speed-unknown", "UNCERTAIN"),
                                                (lambda t: speed(t, 12.0, "UNCERTAIN"), "ego-speed-unknown", "UNCERTAIN")])
def test_fallback_gate_refuses_to_fire(ego, reason, state):
    out = V.RadarFallback(projection()).step(WORLD, radar=Radar().at(WORLD, NEAR, "f09-radar-vc"), ego_speed=ego(WORLD))
    assert not out["fired"] and out["brakeRequest"] == 0.0 and out["reason"] == reason and out["state"] == state


def test_fallback_latch_held_through_a_gate_failure():
    fallback, radar = V.RadarFallback(projection()), Radar()
    fallback.step(WORLD, radar=radar.at(WORLD, NEAR, "f09-radar-vc"), ego_speed=speed(WORLD, 12.0))
    t = WORLD + 50 * MS
    out = fallback.step(t, radar=radar.at(t, NEAR, "f09-radar-vc"))  # the ego speed is now 50 ms old: still fresh
    assert out["brakeRequest"] == 1.0
    t = WORLD + 150 * MS
    out = fallback.step(t, radar=radar.at(t, NEAR, "f09-radar-vc"))  # speed stale: the gate fails, the latch holds
    assert out["reason"] == "ego-speed-unknown" and not out["fired"] and out["brakeRequest"] == 1.0 and out["latched"]


def test_fallback_refuses_the_adas_stream():
    out = V.RadarFallback(projection()).step(WORLD, radar=Radar().at(WORLD, NEAR, "f08-radar-adas"), ego_speed=speed(WORLD, 12.0))
    assert out["reason"] == "radar-unusable" and out["brakeRequest"] == 0.0


# ---- U5 functional arbiter (R-3 restricted) ------------------------------------------------------------------

def selector(sequence, configuration, now_ns=WORLD, source="configuration-manager"):
    return {"schema": V.SELECTOR, "source": source, "sequence": sequence, "originNs": now_ns, "configuration": configuration}


def adas(sequence, now_ns, value, state="NOMINAL", reason=None):
    # A complete genuine /2 owner envelope; individual tests then alter only their request/state stimulus.
    record = F.FusionRiskAeb(projection(), model_output_binding=model_binding()).step(now_ns, radar=Radar().at(now_ns, FAR), perception=perception(now_ns))
    return dict(record, sequence=sequence, brakeRequest=value, state=state, reason=reason)


def fallback(sequence, now_ns, value, state="NOMINAL"):
    return {"schema": V.FALLBACK_REQUEST, "source": "radar-fallback", "sequence": sequence, "originNs": now_ns,
            "brakeRequest": value, "state": state, "reason": None}


def test_arbiter_emits_the_wp04_request_the_chassis_zone_and_node_accept():
    arbiter = V.FunctionalArbiter(projection())
    request = arbiter.step(WORLD, [("selector-command", selector(1, "C_NOMINAL")), ("adas-cycle", adas(1, WORLD, 0.7))])
    assert set(request) == B.ARBITER_REQUEST_MEMBERS and request["value"] == 0.7
    routed = B.ChassisZone().step(WORLD, [("brake-request", request)])
    node = B.BrakeEscNode(B.BrakeNodeParams.from_record({"schema": B.NODE_PARAMS, "stalenessWindowNs": 80 * MS,
                                                         "computeLatencyNs": 0}))  # TEST-ONLY values
    statuses = [s["status"] for s in node.step(WORLD, [m for _, m in routed])["status"]]
    assert statuses == ["received", "accepted", "forwarded"]


def test_arbiter_one_request_per_step_and_no_selector():
    arbiter = V.FunctionalArbiter(projection())
    first = arbiter.step(WORLD, [("adas-cycle", adas(1, WORLD, 1.0))])
    assert first["value"] == 0.0 and arbiter.evidence[-1]["kind"] == "no-selector"
    second = arbiter.step(WORLD + 50 * MS, [])
    assert [first["sequence"], second["sequence"]] == [1, 2] and len(arbiter.evidence) == 2


def test_arbiter_clamps_at_the_source_with_a_flag():
    arbiter = V.FunctionalArbiter(projection())
    request = arbiter.step(WORLD, [("selector-command", selector(1, "C_NOMINAL")), ("adas-cycle", adas(1, WORLD, 1.4))])
    record = arbiter.evidence[-1]
    assert request["value"] == 1.0 and record["clamped"] and record["rawValue"] == 1.4
    request = arbiter.step(WORLD + MS, [("adas-cycle", adas(2, WORLD + MS, -0.2))])
    assert request["value"] == 0.0 and arbiter.evidence[-1]["clamped"]


def test_arbiter_hold_window_then_no_valid_source_and_never_the_fallback():
    arbiter = V.FunctionalArbiter(projection())
    arbiter.step(WORLD, [("selector-command", selector(1, "C_NOMINAL")), ("adas-cycle", adas(1, WORLD, 1.0))])
    # An ADAS freeze: no adas-cycle arrives, while a fresh fallback request does.
    held = arbiter.step(WORLD + 50 * MS, [("fallback-request", fallback(1, WORLD + 50 * MS, 0.3))])
    assert held["value"] == 1.0 and arbiter.evidence[-1]["kind"] == "held"
    held = arbiter.step(WORLD + 100 * MS, [("fallback-request", fallback(2, WORLD + 100 * MS, 0.3))])
    assert held["value"] == 1.0  # exactly at the hold window
    gone = arbiter.step(WORLD + 101 * MS, [("fallback-request", fallback(3, WORLD + 101 * MS, 0.3))])
    assert gone["value"] == 0.0 and arbiter.evidence[-1]["kind"] == "no-valid-source"
    assert all(r["selectedInterface"] == "adas-cycle" for r in arbiter.evidence)


def test_arbiter_forwards_uncertain_without_acting_on_it():
    arbiter = V.FunctionalArbiter(projection())
    request = arbiter.step(WORLD, [("selector-command", selector(1, "C_NOMINAL")),
                                   ("adas-cycle", adas(1, WORLD, 0.0, "UNCERTAIN", "camera-unusable")),
                                   ("fallback-request", fallback(1, WORLD, 1.0))])
    record = arbiter.evidence[-1]
    assert request["value"] == 0.0 and record["kind"] == "fresh"
    assert record["forwardedState"] == "UNCERTAIN" and record["forwardedReason"] == "camera-unusable"


def test_arbiter_refuses_stale_non_finite_replayed_and_foreign_requests():
    arbiter = V.FunctionalArbiter(projection())
    arbiter.step(WORLD, [("selector-command", selector(1, "C_NOMINAL"))])
    arbiter.step(WORLD + MS, [("adas-cycle", adas(1, WORLD - 80 * MS, 1.0))])
    assert arbiter.evidence[-1]["kind"] == "no-valid-source" and "stale" in arbiter.evidence[-1]["flags"]
    arbiter.step(WORLD + 2 * MS, [("adas-cycle", adas(2, WORLD + 2 * MS, math.inf))])
    assert "non-finite" in arbiter.evidence[-1]["flags"] and arbiter.evidence[-1]["kind"] == "no-valid-source"
    arbiter.step(WORLD + 3 * MS, [("adas-cycle", adas(2, WORLD + 3 * MS, 1.0))])
    assert "request-refused" in arbiter.evidence[-1]["flags"]  # sequence 2 was already used
    foreign = dict(adas(3, WORLD + 4 * MS, 1.0), source="proposer")
    assert arbiter.step(WORLD + 4 * MS, [("adas-cycle", foreign)])["value"] == 0.0


def test_arbiter_selector_authority():
    arbiter = V.FunctionalArbiter(projection())
    arbiter.step(WORLD, [("selector-command", selector(2, "C_NOMINAL"))])
    arbiter.step(WORLD + MS, [("selector-command", selector(3, "C_DEGRADED_RADAR", source="proposer")),
                              ("selector-command", selector(2, "C_DEGRADED_RADAR")),
                              ("selector-command", selector(4, "C_TURBO")),
                              ("selector-command", {"schema": V.SELECTOR})])
    record = arbiter.evidence[-1]
    assert record["configuration"] == "C_NOMINAL" and record["selectorSequence"] == 2
    assert record["refusals"] == ["selector-wrong-source", "selector-replayed", "selector-unknown-configuration",
                                  "selector-malformed"]


def test_arbiter_hold_is_per_source_after_a_switch():
    arbiter = V.FunctionalArbiter(projection())
    arbiter.step(WORLD, [("selector-command", selector(1, "C_NOMINAL")), ("adas-cycle", adas(1, WORLD, 1.0))])
    request = arbiter.step(WORLD + 10 * MS, [("selector-command", selector(2, "C_DEGRADED_RADAR"))])
    assert request["value"] == 0.0 and arbiter.evidence[-1]["kind"] == "no-valid-source"  # the ADAS value is not held
    request = arbiter.step(WORLD + 20 * MS, [("fallback-request", fallback(1, WORLD + 20 * MS, 1.0))])
    assert request["value"] == 1.0 and arbiter.evidence[-1]["selectedInterface"] == "fallback-request"


@pytest.mark.parametrize("mrc, expected", [("fallback-request", 0.6), ("adas-cycle", 0.2), ("none", 0.0)])
def test_arbiter_mrc_follows_the_declared_source(mrc, expected):
    arbiter = V.FunctionalArbiter(projection(arbiter__mrcSource=mrc))
    request = arbiter.step(WORLD, [("selector-command", selector(1, "S_MRC_REQUESTED")),
                                   ("adas-cycle", adas(1, WORLD, 0.2)), ("fallback-request", fallback(1, WORLD, 0.6))])
    assert request["value"] == expected


def test_arbiter_counts_qualified_evidence_and_refuses_undeclared_interfaces():
    arbiter = V.FunctionalArbiter(projection())
    arbiter.step(WORLD, [("qualified-evidence", {"kind": "x"}), ("brake-status", {})])
    assert arbiter.qualified_seen == 1 and arbiter.evidence[-1]["refusals"] == ["undeclared-interface-brake-status"]


# ---- determinism (T-9) and isolation ---------------------------------------------------------------------------

def _stream(world):
    fusion, fb, arbiter, radar_u4, radar_u5 = (F.FusionRiskAeb(projection(), model_output_binding=model_binding()), V.RadarFallback(projection()),
                                               V.FunctionalArbiter(projection()), Radar(), Radar())
    out = []
    for k in range(8):
        t = world + k * 50 * MS
        depth = 40.0 - 5.0 * k
        d = 2.0 + depth - 2.4  # TEST-ONLY mount and front
        detections = [[0.0, 0.0, depth, -10.0]]
        predicted = "bin-0" if d < 10.0 else "bin-1" if d < 20.0 else "bin-2"
        a = fusion.step(t, radar=radar_u4.at(t, detections), perception=perception(t, predicted=predicted))
        f = fb.step(t, radar=radar_u5.at(t, detections, "f09-radar-vc"), ego_speed=speed(t, 10.0))
        inbox = [("adas-cycle", a), ("fallback-request", f)] + ([("selector-command", selector(1, "C_NOMINAL", t))] if k == 0 else [])
        out.append((a, f, arbiter.step(t, inbox), arbiter.evidence[-1]))
    return out


def _relative(value, world):
    if isinstance(value, dict):
        return {k: (v - world if k.endswith("Ns") and k not in ("ageNs",) and isinstance(v, int) else _relative(v, world))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_relative(v, world) for v in value]
    return value


def test_identical_inputs_give_identical_streams_and_epoch_shift_only_moves_stamps():
    stream = _stream(WORLD)
    assert [a["hypothesis"]["agreement"] for a, *_ in stream] == ["agree"] * 8
    assert [r["value"] for _, _, r, _ in stream] == [0.0] * 6 + [1.0, 1.0]  # the rule fires at d = 9.6 m (k = 6)
    assert stream == _stream(WORLD)
    shifted = 7_000 * MS
    assert _relative(_stream(WORLD), WORLD) == _relative(_stream(WORLD + shifted), WORLD + shifted)


def test_logic_modules_import_no_ml_and_u4_u5_stay_apart():
    names = {}
    for module in ("aeb_rule", "fusion_aeb", "vc_functional", "parameters"):
        tree = ast.parse((HERE / "assured_aeb" / f"{module}.py").read_text())
        names[module] = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
            {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    for module, imported in names.items():
        assert not any(x in name for name in imported for x in ("onnxruntime", "numpy", "perception", "labels")), module
    assert "vc_functional" not in names["fusion_aeb"] and "fusion_aeb" not in names["vc_functional"]
    assert "radar_zone" not in names["fusion_aeb"] | names["vc_functional"] | names["aeb_rule"]


# Independent-review regressions R13-1 to R13-4; all values are the existing TEST-ONLY fixture values.

def test_stale_camera_with_positive_radar_cannot_release_a_fired_latch():
    fusion, radar = F.FusionRiskAeb(projection(), model_output_binding=model_binding()), Radar()
    first = fusion.step(WORLD, radar=radar.at(WORLD, NEAR), perception=perception(WORLD))
    assert first["brakeRequest"] == 1.0
    for cycle in range(1, 5):
        now = WORLD + cycle * 100 * MS
        record = fusion.step(now, radar=radar.at(now, NEAR))
        assert record["brakeRequest"] == 1.0
        assert record["state"] == "UNCERTAIN" and record["reason"] == "camera-unusable"
        assert fusion.latch.absent == 0


def test_unknown_radar_cannot_release_the_fallback_latch():
    fallback, radar = V.RadarFallback(projection()), Radar()
    def speed(now):
        return {"speedMps": 12.0, "originNs": now, "state": "NOMINAL"}
    first = fallback.step(WORLD, radar=radar.at(WORLD, NEAR, V.RADAR_STREAM), ego_speed=speed(WORLD))
    assert first["brakeRequest"] == 1.0
    for cycle in range(1, 5):
        now = WORLD + cycle * 50 * MS
        message = radar.at(now, NEAR, V.RADAR_STREAM)
        message["checks"]["integrity"]["verdict"] = "fail"
        record = fallback.step(now, radar=message, ego_speed=speed(now))
        assert record["brakeRequest"] == 1.0 and record["state"] == "UNCERTAIN"
        assert fallback.latch.absent == 0


def test_uncertainty_breaks_consecutive_observed_absence():
    latch = A.Latch(A.rule_from(TEST_ONLY_ENTRIES, "aeb"))
    assert latch.decide(True, True, 12.0) == 1.0
    assert latch.decide(False, False, None) == 1.0
    assert latch.decide(False, False, None) == 1.0
    assert latch.uncertain() == 1.0 and latch.absent == 0
    assert latch.decide(False, False, None) == 1.0
    assert latch.decide(False, False, None) == 1.0
    assert latch.decide(False, False, None) == 0.0


@pytest.mark.parametrize("key,value", [
    ("frame", "invalid"), ("frame", -1), ("frame", True),
    ("oodScore", math.nan), ("oodScore", math.inf), ("oodScore", True),
    ("binProbabilities", "invalid"), ("binProbabilities", []), ("binProbabilities", [math.nan]),
    ("binProbabilities", [-0.1]), ("binProbabilities", [1.1]), ("binProbabilities", [True]),
    ("provenance", None), ("provenance", {}),
    ("inputQuality", None), ("inputQuality", {"value": math.nan}),
    ("predictedBin", "bin-9999"), ("predictedBin", "bin-" + "9" * 5000),
    ("reason", 1), ("state", "unknown"),
])
def test_malformed_perception_fields_are_unusable_without_crashing(key, value):
    record = perception(WORLD)
    record[key] = value
    result = F.FusionRiskAeb(projection(), model_output_binding=model_binding()).step(WORLD, radar=Radar().at(WORLD, NEAR), perception=record)
    assert result["state"] == "UNCERTAIN" and result["reason"] == "camera-unusable"
    assert result["brakeRequest"] == 0.0


@pytest.mark.parametrize("key", ["modelDigest", "preprocessParamsSha256", "postprocessSha256"])
def test_each_perception_provenance_digest_is_checked(key):
    record = perception(WORLD)
    record["provenance"][key] = "not-a-digest"
    result = F.FusionRiskAeb(projection(), model_output_binding=model_binding()).step(WORLD, radar=Radar().at(WORLD, NEAR), perception=record)
    assert result["state"] == "UNCERTAIN" and result["reason"] == "camera-unusable"


@pytest.mark.parametrize("check", [None, {}, {"verdict": "not-evaluated"}, {"verdict": "unknown"}])
def test_unavailable_radar_statistical_check_is_uncertain(check):
    message = Radar().at(WORLD, NEAR)
    if check is None:
        message["checks"]["sensorSelfCheck"].pop("statistical")
    else:
        message["checks"]["sensorSelfCheck"]["statistical"] = check
    view = A.qualify_radar(message, F.RADAR_STREAM, WORLD, 80 * MS)
    assert view.state == "UNCERTAIN" and "sensor-statistical-unknown" in view.failures


def test_negative_ego_speed_cannot_satisfy_the_degraded_odd():
    result = V.RadarFallback(projection()).step(
        WORLD, radar=Radar().at(WORLD, NEAR, V.RADAR_STREAM),
        ego_speed={"speedMps": -100.0, "originNs": WORLD, "state": "NOMINAL"})
    assert result["state"] == "UNCERTAIN" and result["reason"] == "ego-speed-unknown"
    assert result["fired"] is False and result["brakeRequest"] == 0.0


# R13-6: oversized JSON integers are rejected at public consumer boundaries.
# The 1001-digit fixture is below the existing wire limit; it is not a protocol value.
LARGE_JSON_INTS = (json.loads("1" + "0" * 1000), json.loads("-1" + "0" * 1000))


@pytest.mark.parametrize("value", LARGE_JSON_INTS, ids=("large-positive", "large-negative"))
@pytest.mark.parametrize("field", ("occupancyProbability", "binProbabilities", "oodScore"))
def test_oversized_perception_number_is_uncertain_and_keeps_an_active_latch(value, field):
    fusion, radar = F.FusionRiskAeb(projection(), model_output_binding=model_binding()), Radar()
    assert fusion.step(WORLD, radar=radar.at(WORLD, NEAR), perception=perception(WORLD))["brakeRequest"] == 1.0
    now = WORLD + 50 * MS
    record = perception(now)
    record[field] = [value] if field == "binProbabilities" else value
    result = fusion.step(now, radar=radar.at(now, NEAR), perception=record)
    assert result["state"] == "UNCERTAIN" and result["reason"] == "camera-unusable"
    assert result["brakeRequest"] == 1.0 and result["latched"] is True
    assert fusion.latch.absent == 0


@pytest.mark.parametrize("value", LARGE_JSON_INTS, ids=("large-positive", "large-negative"))
def test_oversized_ego_speed_is_uncertain_and_keeps_an_active_fallback_latch(value):
    fb, radar = V.RadarFallback(projection()), Radar()
    assert fb.step(WORLD, radar=radar.at(WORLD, NEAR, V.RADAR_STREAM), ego_speed=speed(WORLD, 12.0))["brakeRequest"] == 1.0
    now = WORLD + 50 * MS
    result = fb.step(now, radar=radar.at(now, NEAR, V.RADAR_STREAM), ego_speed=speed(now, value))
    assert result["state"] == "UNCERTAIN" and result["reason"] == "ego-speed-unknown"
    assert result["brakeRequest"] == 1.0 and result["fired"] is False and result["latched"] is True
    assert fb.latch.absent == 0


@pytest.mark.parametrize("value", LARGE_JSON_INTS, ids=("large-positive", "large-negative"))
def test_oversized_radar_detection_is_uncertain(value):
    record = Radar().at(WORLD, NEAR)
    record["payload"]["detections"][0][3] = value
    view = A.qualify_radar(record, F.RADAR_STREAM, WORLD, 80 * MS)
    assert view.state == "UNCERTAIN" and "malformed-detections" in view.failures
    assert view.detections == ()


@pytest.mark.parametrize("value", LARGE_JSON_INTS, ids=("large-positive", "large-negative"))
def test_oversized_arbiter_request_uses_only_the_existing_bounded_hold(value):
    arbiter = V.FunctionalArbiter(projection())
    first = arbiter.step(WORLD, [("selector-command", selector(1, "C_NOMINAL")), ("adas-cycle", adas(1, WORLD, 1.0))])
    assert first["value"] == 1.0
    now = WORLD + 50 * MS
    result = arbiter.step(now, [("adas-cycle", adas(2, now, value))])
    assert result["value"] == 1.0 and arbiter.evidence[-1]["kind"] == "held"
    assert "non-finite" in arbiter.evidence[-1]["flags"]
    now = WORLD + 101 * MS
    result = arbiter.step(now, [("adas-cycle", adas(3, now, value))])
    assert result["value"] == 0.0 and arbiter.evidence[-1]["kind"] == "no-valid-source"


@pytest.mark.parametrize("value", LARGE_JSON_INTS, ids=("large-positive", "large-negative"))
@pytest.mark.parametrize("identifier,shape", [
    ("aeb.decelerationMps2", "scalar"), ("aeb.marginM", "scalar"),
    ("fusion.occupancyThreshold", "scalar"), ("aeb.brakeLevel", "scalar"),
    ("radar.mountM", "xy"), ("fusion.distanceBinEdgesM", "list"),
])
def test_oversized_numeric_parameter_is_a_named_projection_refusal(value, identifier, shape):
    if shape == "xy":
        value = [value, 0.0]
    elif shape == "list":
        value = [value]
    params = projection(**{identifier.replace(".", "__"): value})
    with pytest.raises(ValueError, match=identifier.replace(".", r"\.")):
        F.FusionRiskAeb(params, model_output_binding=model_binding())


def test_numeric_projection_preserves_finite_values_and_bool_refusal():
    assert F.FusionRiskAeb(projection(fusion__occupancyThreshold=0.5), model_output_binding=model_binding()).values["fusion.occupancyThreshold"] == 0.5
    with pytest.raises(ValueError, match=r"fusion\.occupancyThreshold"):
        F.FusionRiskAeb(projection(fusion__occupancyThreshold=True), model_output_binding=model_binding())
