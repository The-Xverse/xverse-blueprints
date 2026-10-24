"""U3 smart-radar self-checks and front-zone checks (WP-07; FR-002, FR-034; AD-18 C, AD-36 B; review-wp07 finding 1
§1.4-1.5).

``SmartRadar`` computes its indicators from its own output only (detection count, frame continuity, age) in the three
AD-36 classes; its plausibility bounds are the configured sensor specification (``carla-sensors.json``). ``FrontZone``
assigns reception timestamps, checks freshness, integrity and sequence, carries the sensors' verdicts forward, and
routes camera evidence to F07 and radar evidence to both F08 and F09. It decides nothing and carries no pixels.
Thresholds and windows are protocol values with no default. Times are absolute integer ns.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from typing import Any

from .camera_chain import SELFCHECK as CAMERA_SELFCHECK
from .checks import CLASSES, HEX64, exact, is_int, is_number, sequence_status, verdict

RADAR_CHECKS = "assured-aeb.smart-radar-checks/1"
RADAR_SELFCHECK = "assured-aeb.radar-selfcheck/1"
FRONT_ZONE = "assured-aeb.front-zone-checks/1"
CAMERA_EVIDENCE = "assured-aeb.camera-evidence/1"
RADAR_EVIDENCE = "assured-aeb.radar-evidence/1"
RADAR_FLOWS = ("radar-adas", "radar-vc")  # the adapter's radar flows (compat protocol.py 31); WP-10 wires one of them
SPEC = {"rangeM", "horizontalFovDeg", "verticalFovDeg", "maxVelocityMps", "maxDetections"}
#: Class (iii) count bounds (D-2; no defaults). The age bound is the front zone's AD-06 window (finding 4, LOW-1).
RADAR_THRESHOLDS = {"minCount", "maxCount"}
ANGLE_TOLERANCE = 1e-9  # as the adapter (compat sensors.py ANGLE_TOLERANCE): a numerical tolerance, not a protocol value
#: Half a unit of the adapter's rounding (compat sensors.py 62: altitude and azimuth to 6 decimals, depth and velocity
#: to 3): the smart radar sees rounded values, so its bounds allow this much (review-wp07 finding 4, LOW-2).
ANGLE_ROUNDING = 0.5e-6
LINEAR_ROUNDING = 0.5e-3


@dataclass(frozen=True)
class SmartRadarParams:
    spec: dict[str, float]
    thresholds: dict[str, int]

    @classmethod
    def from_record(cls, record: Any) -> "SmartRadarParams":
        record = exact(record, RADAR_CHECKS, {"schema", "spec", "thresholds"})
        spec, thresholds = record["spec"], record["thresholds"]
        if not isinstance(spec, dict) or set(spec) != SPEC or not all(is_number(v) and v > 0 for v in spec.values()) \
                or not is_int(spec["maxDetections"]):
            raise ValueError(f"spec must be exactly {sorted(SPEC)}, positive, from the configured sensor descriptor")
        if not isinstance(thresholds, dict) or set(thresholds) != RADAR_THRESHOLDS or not all(is_int(v) and v >= 0 for v in thresholds.values()) \
                or thresholds["minCount"] >= thresholds["maxCount"]:
            raise ValueError(f"thresholds must be exactly {sorted(RADAR_THRESHOLDS)} as non-negative integers (no defaults; D-2)")
        return cls(dict(spec), dict(thresholds))


class SmartRadar:
    def __init__(self, params: SmartRadarParams, flow_id: str) -> None:
        if type(params) is not SmartRadarParams:
            raise TypeError("SmartRadarParams.from_record is required (no default parameters)")
        if flow_id not in RADAR_FLOWS:
            raise ValueError(f"flow_id must be one of {RADAR_FLOWS}")
        self.params, self.flow_id = params, flow_id
        self.last_sequence: int | None = None
        self.last_frame: int | None = None

    def step(self, now_ns: int, item: Any) -> dict[str, Any]:
        if not is_int(now_ns):
            raise ValueError("simulation time must be integer nanoseconds")
        logical, plausibility, statistical = [], [], []
        value = item.get("value") if isinstance(item, dict) else None
        if not (isinstance(item, dict) and item.get("flowId") == self.flow_id and is_int(item.get("sequence"))
                and is_int(item.get("originNs")) and isinstance(value, dict) and isinstance(value.get("detections"), list)
                and is_int(value.get("count"))):
            return {"schema": RADAR_SELFCHECK, "source": "smart-radar", "flowId": self.flow_id, "frame": None, "sequence": None,
                    "originNs": None, "detections": [], "count": None, "indicators": {},
                    "checks": {"logical": verdict(["malformed"]), "plausibility": verdict([], False),
                               "statistical": verdict([], False)}}
        detections, count = value["detections"], value["count"]
        status, gap = sequence_status(self.last_sequence, item["sequence"])
        if status != "ok":
            logical.append(f"sequence-{status}")
        if status in ("ok", "gap"):
            self.last_sequence = item["sequence"]
        frame = item.get("frame")
        if is_int(frame):
            if self.last_frame is not None and frame <= self.last_frame:
                logical.append("frame-not-increasing")
            self.last_frame = frame if self.last_frame is None else max(frame, self.last_frame)
        if count != len(detections):
            logical.append("count-mismatch")
        age = now_ns - item["originNs"]
        if age < 0:
            logical.append("future-origin")
        spec = self.params.spec
        half_h = math.radians(spec["horizontalFovDeg"]) / 2 + ANGLE_TOLERANCE + ANGLE_ROUNDING
        half_v = math.radians(spec["verticalFovDeg"]) / 2 + ANGLE_TOLERANCE + ANGLE_ROUNDING
        if len(detections) > spec["maxDetections"]:
            plausibility.append("too-many-detections")
        for row in detections:
            if not (isinstance(row, list) and len(row) == 4 and all(is_number(v) for v in row)):
                logical.append("malformed-detection")
                break
            alt, az, depth, vel = row
            if not (0 <= depth <= spec["rangeM"] + LINEAR_ROUNDING) or abs(vel) > spec["maxVelocityMps"] + LINEAR_ROUNDING \
                    or abs(az) > half_h or abs(alt) > half_v:
                plausibility.append("detection-out-of-specification")
                break
        t = self.params.thresholds
        if not t["minCount"] <= len(detections) <= t["maxCount"]:
            statistical.append("count")
        checks = dict(zip(CLASSES, (verdict(logical), verdict(plausibility), verdict(statistical))))
        return {"schema": RADAR_SELFCHECK, "source": "smart-radar", "flowId": self.flow_id, "frame": frame,
                "sequence": item["sequence"], "originNs": item["originNs"], "detections": detections, "count": count,
                "indicators": {"ageNs": age, "sequenceGap": gap, "sequenceStatus": status, "count": len(detections)},
                "checks": checks}


@dataclass(frozen=True)
class FrontZoneParams:
    camera_window_ns: int
    radar_window_ns: int

    @classmethod
    def from_record(cls, record: Any) -> "FrontZoneParams":
        record = exact(record, FRONT_ZONE, {"schema", "cameraFreshnessWindowNs", "radarFreshnessWindowNs"})
        windows = (record["cameraFreshnessWindowNs"], record["radarFreshnessWindowNs"])
        if not all(is_int(v) and v > 0 for v in windows):
            raise ValueError("freshness windows must be positive integers (no defaults; AD-06)")
        return cls(*windows)


CAMERA_SELFCHECK_MEMBERS = frozenset({"schema", "source", "frame", "sequence", "originNs", "frameSha256", "indicators", "checks"})
RADAR_SELFCHECK_MEMBERS = frozenset({"schema", "source", "flowId", "frame", "sequence", "originNs", "detections", "count",
                                     "indicators", "checks"})


class FrontZone:
    """U3 front zonal ECU: reception timestamps, freshness, integrity and sequence checks; F07, F08, F09 routing."""

    def __init__(self, params: FrontZoneParams) -> None:
        if type(params) is not FrontZoneParams:
            raise TypeError("FrontZoneParams.from_record is required (no default parameters)")
        self.params = params
        self.last: dict[str, int | None] = {"smart-camera": None, "smart-radar": None}

    def _common(self, now_ns: int, sensor: str, item: dict[str, Any], window: int, integrity: list[str]) -> dict[str, Any]:
        origin = item.get("originNs")
        age = now_ns - origin if is_int(origin) else None
        sequence = item.get("sequence")
        seq_status = "unknown"
        if is_int(sequence):
            seq_status, _ = sequence_status(self.last[sensor], sequence)
            if seq_status in ("ok", "gap"):
                self.last[sensor] = sequence
        sensor_checks = item.get("checks") if isinstance(item.get("checks"), dict) else {}
        plausibility = (sensor_checks.get("plausibility") or {}).get("verdict", "not-evaluated")
        return {"sensor": sensor, "originNs": origin, "receivedNs": now_ns, "ageNs": age, "sequence": sequence,
                "checks": {"integrity": verdict(integrity), "sequence": seq_status,
                           "fresh": age is not None and 0 <= age <= window, "plausibility": plausibility,
                           "sensorSelfCheck": sensor_checks}}

    def step(self, now_ns: int, inbox: list[tuple[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
        """Process ``(interface, item)`` pairs; return ``(flow id, message)`` pairs for F07, F08 and F09."""

        if not is_int(now_ns):
            raise ValueError("simulation time must be integer nanoseconds")
        out = []
        for interface, item in inbox:
            if interface == "smart-camera-evidence":
                integrity = [] if (isinstance(item, dict) and set(item) == CAMERA_SELFCHECK_MEMBERS and item.get("schema") == CAMERA_SELFCHECK
                                   and isinstance(item.get("frameSha256"), str) and HEX64.match(item["frameSha256"])) else ["camera-item"]
                base = self._common(now_ns, "smart-camera", item if isinstance(item, dict) else {}, self.params.camera_window_ns, integrity)
                payload = {"frameSha256": item.get("frameSha256"), "frame": item.get("frame"),
                           "indicators": item.get("indicators")} if isinstance(item, dict) else {}
                out.append(("f07-camera-adas", copy.deepcopy({"schema": CAMERA_EVIDENCE, "source": "front-zone",
                                                              "stream": "f07-camera-adas", **base, "payload": payload})))
            elif interface == "smart-radar-evidence":
                integrity = [] if (isinstance(item, dict) and set(item) == RADAR_SELFCHECK_MEMBERS
                                   and item.get("schema") == RADAR_SELFCHECK) else ["radar-item"]
                base = self._common(now_ns, "smart-radar", item if isinstance(item, dict) else {}, self.params.radar_window_ns, integrity)
                payload = {"detections": item.get("detections"), "count": item.get("count"), "frame": item.get("frame"),
                           "indicators": item.get("indicators")} if isinstance(item, dict) else {}
                for flow in ("f08-radar-adas", "f09-radar-vc"):
                    out.append((flow, copy.deepcopy({"schema": RADAR_EVIDENCE, "source": "front-zone", "stream": flow, **base,
                                                     "payload": payload})))
        return out
