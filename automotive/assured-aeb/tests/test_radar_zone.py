"""Offline tests of the U3 smart radar and the front zone (no CARLA, no run).

SPEC holds the configured sensor descriptor values (xverse-compat xdl/descriptors/aeb-sim/carla-sensors.json at 95e9e7a:
radar 100 m, 30 x 10 degrees, 100 m/s, 500 detections): AD-36 class (ii) bounds come from the configured specification.
The thresholds and windows are TEST VALUES; the protocol values are TODO (D-2, AD-06) with no default.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math

import pytest

from assured_aeb import camera_chain as C
from assured_aeb import radar_zone as R
import topology as T

MS = 1_000_000
WORLD = 1_000_000 * MS
SPEC = {"rangeM": 100.0, "horizontalFovDeg": 30.0, "verticalFovDeg": 10.0, "maxVelocityMps": 100.0, "maxDetections": 500}
RADAR_RECORD = {"schema": R.RADAR_CHECKS, "spec": dict(SPEC), "thresholds": {"minCount": 1, "maxCount": 200}}
ZONE_RECORD = {"schema": R.FRONT_ZONE, "cameraFreshnessWindowNs": 80 * MS, "radarFreshnessWindowNs": 80 * MS}


def radar():
    return R.SmartRadar(R.SmartRadarParams.from_record(copy.deepcopy(RADAR_RECORD)), "radar-adas")


def zone():
    return R.FrontZone(R.FrontZoneParams.from_record(dict(ZONE_RECORD)))


def radar_item(sequence, origin_ns, detections=None, count=None):
    detections = [[0.0, 0.01, 40.0, -10.0]] if detections is None else detections
    return {"type": "item", "flowId": "radar-adas", "sequence": sequence, "originNs": origin_ns, "frame": 100 + sequence,
            "value": {"detections": detections, "count": len(detections) if count is None else count}}


def test_configured_specification_matches_the_descriptor_values():
    descriptor = {"rangeM": 100.0, "horizontalFovDeg": 30.0, "verticalFovDeg": 10.0, "maxVelocityMps": 100.0, "maxDetections": 500}
    assert R.SmartRadarParams.from_record(copy.deepcopy(RADAR_RECORD)).spec == descriptor


@pytest.mark.parametrize("mutate", [
    lambda r: r["spec"].pop("rangeM"), lambda r: r["spec"].update(maxDetections=500.5), lambda r: r["thresholds"].update(minCount=-1),
    lambda r: r["thresholds"].update(minCount=300), lambda r: r["thresholds"].update(minCount=200),
    lambda r: r["thresholds"].pop("maxCount"), lambda r: r["thresholds"].update(maxAgeNs=1), lambda r: r.update(extra=1),
])
def test_radar_record_is_refused(mutate):
    record = copy.deepcopy(RADAR_RECORD)
    mutate(record)
    with pytest.raises(ValueError):
        R.SmartRadarParams.from_record(record)


def test_front_zone_record_has_no_defaults():
    for bad in ({"schema": R.FRONT_ZONE}, dict(ZONE_RECORD, cameraFreshnessWindowNs=0), dict(ZONE_RECORD, radarFreshnessWindowNs=1.0)):
        with pytest.raises(ValueError):
            R.FrontZoneParams.from_record(bad)
    with pytest.raises(TypeError):
        R.FrontZone(None)
    with pytest.raises(ValueError):
        R.SmartRadar(R.SmartRadarParams.from_record(copy.deepcopy(RADAR_RECORD)), "camera")


def test_clean_radar_passes_every_class():
    result = radar().step(WORLD + 10 * MS, radar_item(0, WORLD))
    assert [result["checks"][c]["verdict"] for c in ("logical", "plausibility", "statistical")] == ["pass", "pass", "pass"]
    assert result["indicators"] == {"ageNs": 10 * MS, "sequenceGap": 0, "sequenceStatus": "ok", "count": 1}


def test_radar_logical_checks():
    r = radar()
    r.step(WORLD, radar_item(0, WORLD))
    gap = r.step(WORLD + 100 * MS, radar_item(3, WORLD + 100 * MS))
    assert gap["indicators"]["sequenceGap"] == 2 and "sequence-gap" in gap["checks"]["logical"]["failed"]
    assert "count-mismatch" in radar().step(WORLD, radar_item(0, WORLD, count=5))["checks"]["logical"]["failed"]
    assert "future-origin" in radar().step(WORLD - 1, radar_item(0, WORLD))["checks"]["logical"]["failed"]
    assert radar().step(WORLD, {"flowId": "radar-vc"})["checks"]["logical"]["failed"] == ["malformed"]


@pytest.mark.parametrize("detection", [[0.0, 0.0, 100.5, 0.0], [0.0, math.radians(16), 10.0, 0.0],
                                       [math.radians(6), 0.0, 10.0, 0.0], [0.0, 0.0, 10.0, -100.5]])
def test_radar_plausibility_from_the_configured_specification(detection):
    result = radar().step(WORLD, radar_item(0, WORLD, [detection]))
    assert result["checks"]["plausibility"]["failed"] == ["detection-out-of-specification"]


def test_radar_statistical_class():
    assert radar().step(WORLD, radar_item(0, WORLD, []))["checks"]["statistical"]["failed"] == ["count"]
    late = radar().step(WORLD + 200 * MS, radar_item(0, WORLD))
    assert late["indicators"]["ageNs"] == 200 * MS and late["checks"]["statistical"]["verdict"] == "pass"


def test_rounded_detection_at_a_non_default_field_of_view_is_plausible():  # finding 4, LOW-2
    record = copy.deepcopy(RADAR_RECORD)
    record["spec"]["horizontalFovDeg"] = 35.0  # half field 0.305432619... rad
    raw = 0.30543261  # within the raw bound; the adapter rounds it to 6 decimals
    rounded = round(raw, 6)
    assert rounded > math.radians(35.0) / 2 + R.ANGLE_TOLERANCE  # the case that failed before the repair
    r = R.SmartRadar(R.SmartRadarParams.from_record(record), "radar-adas")
    assert r.step(WORLD, radar_item(0, WORLD, [[0.0, rounded, 40.0, 0.0]]))["checks"]["plausibility"]["verdict"] == "pass"
    r2 = R.SmartRadar(R.SmartRadarParams.from_record(record), "radar-adas")
    assert r2.step(WORLD, radar_item(0, WORLD, [[0.0, 0.3060, 40.0, 0.0]]))["checks"]["plausibility"]["verdict"] == "fail"


def _camera_selfcheck(sequence=0, origin=WORLD):
    return {"schema": C.SELFCHECK, "source": "smart-camera", "frame": sequence, "sequence": sequence, "originNs": origin,
            "frameSha256": hashlib.sha256(b"x").hexdigest(), "indicators": {"ageNs": 0},
            "checks": {"logical": {"verdict": "pass", "failed": []}, "plausibility": {"verdict": "pass", "failed": []},
                       "statistical": {"verdict": "pass", "failed": []}}}


def test_front_zone_routes_camera_to_f07_and_radar_to_f08_and_f09():
    z = zone()
    radar_check = radar().step(WORLD + 5 * MS, radar_item(0, WORLD))
    out = z.step(WORLD + 20 * MS, [("smart-camera-evidence", _camera_selfcheck()), ("smart-radar-evidence", radar_check)])
    assert [flow for flow, _ in out] == ["f07-camera-adas", "f08-radar-adas", "f09-radar-vc"]
    f07, f08, f09 = (m for _, m in out)
    assert f07["receivedNs"] == WORLD + 20 * MS and f07["ageNs"] == 20 * MS and f07["checks"]["fresh"] is True
    assert f08["payload"] == f09["payload"] and f08["stream"] != f09["stream"] and f08["payload"] is not f09["payload"]
    assert all(m["checks"]["integrity"]["verdict"] == "pass" for m in (f07, f08, f09))
    flows = {f: T.FLOWS[f] for f in ("f07-camera-adas", "f08-radar-adas", "f09-radar-vc")}
    assert {v[0] for v in flows.values()} == {"front-zone"}  # the WP-12 topology: the front zone produces all three
    assert (flows["f08-radar-adas"][2], flows["f09-radar-vc"][2]) == ("fusion-risk-aeb", "vc-ingress")


def test_front_zone_freshness_integrity_and_sequence():
    z = zone()
    stale = z.step(WORLD + 81 * MS, [("smart-camera-evidence", _camera_selfcheck(0))])[0][1]
    assert stale["checks"]["fresh"] is False
    duplicate = z.step(WORLD + 90 * MS, [("smart-camera-evidence", _camera_selfcheck(0))])[0][1]
    assert duplicate["checks"]["sequence"] == "duplicate"
    future = zone().step(WORLD - 1, [("smart-camera-evidence", _camera_selfcheck(0))])[0][1]
    assert future["checks"]["fresh"] is False
    broken = zone().step(WORLD, [("smart-camera-evidence", dict(_camera_selfcheck(), frameSha256="zz"))])[0][1]
    assert broken["checks"]["integrity"]["verdict"] == "fail"


def test_front_zone_carries_the_sensor_plausibility_forward_and_no_pixels():
    radar_check = radar().step(WORLD, radar_item(0, WORLD, [[0.0, 0.0, 150.0, 0.0]]))
    out = zone().step(WORLD, [("smart-radar-evidence", radar_check)])
    assert all(m["checks"]["plausibility"] == "fail" for _, m in out)
    assert all(not isinstance(v, (bytes, bytearray)) for _, m in out for v in m.values())
    assert "pixels" not in json.dumps([m for _, m in out])
