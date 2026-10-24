"""Shared deterministic AEB logic for U4 and U5 (WP-13 #1; review-wp13-logic finding 1 §1.3-1.4).

This module covers:
- the Note 9 states and the weakest-link aggregate (AD-35 B: unknown counts as ``UNCERTAIN``, no weights);
- the advisory qualification of the front zone's ``assured-aeb.radar-evidence/1`` messages (AD-36 classes);
- the in-corridor nearest-detection selection;
- the conservative AD-05 residual ``r = (d − δd) − v_c·t_lat − v_c²/(2·a_b) − m`` with ``v_c = max(0, v + δv)``;
- the R-2 latch (decisions.md "WP-13 R-1 to R-7").

Every value is a parameter read by identifier (``parameters.py``). Times are absolute world-clock integer ns. No ML and
no host time are used here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .checks import is_int, is_number

STATES = ("NOMINAL", "DEGRADED", "UNCERTAIN", "UNSAFE")  # Note 9, in increasing severity
RADAR_EVIDENCE = "assured-aeb.radar-evidence/1"  # radar_zone.RADAR_EVIDENCE (not imported: U4/U5 must not need U3 code)


def weakest(*states: Any) -> str:
    """AD-35 B: the weakest (most severe) state; anything unknown counts as ``UNCERTAIN``."""

    worst = 0
    for state in states:
        worst = max(worst, STATES.index(state) if state in STATES else STATES.index("UNCERTAIN"))
    return STATES[worst]


def _verdict(checks: Any, name: str) -> Any:
    entry = checks.get(name) if isinstance(checks, dict) else None
    return entry.get("verdict") if isinstance(entry, dict) else None


@dataclass(frozen=True)
class RadarView:
    """The consumer's qualified view of one radar-evidence message."""

    state: str
    failures: tuple[str, ...]
    origin_ns: int | None
    age_ns: int | None
    sequence: int | None
    detections: tuple[tuple[float, float, float, float], ...]


def qualify_radar(message: Any, stream: str, now_ns: int, freshness_ns: int) -> RadarView:
    """Advisory state of a radar-evidence message on ``stream`` (finding 1 §1.3); WP-14 re-derives its own."""

    failures: list[str] = []
    if not (isinstance(message, dict) and message.get("schema") == RADAR_EVIDENCE and message.get("source") == "front-zone"
            and message.get("stream") == stream):
        return RadarView("UNCERTAIN", ("radar-message",), None, None, None, ())
    origin = message.get("originNs")
    age = now_ns - origin if is_int(origin) else None
    checks = message.get("checks") if isinstance(message.get("checks"), dict) else {}
    if _verdict(checks, "integrity") != "pass":
        failures.append("integrity")
    if checks.get("sequence") not in ("ok", "gap"):
        failures.append(f"sequence-{checks.get('sequence')}")
    if checks.get("plausibility") != "pass":
        failures.append("front-zone-plausibility")
    sensor = checks.get("sensorSelfCheck") if isinstance(checks.get("sensorSelfCheck"), dict) else {}
    for name in ("logical", "plausibility"):
        if _verdict(sensor, name) != "pass":
            failures.append(f"sensor-{name}")
    if age is None or age < 0 or age > freshness_ns:
        failures.append("stale")
    payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
    rows = payload.get("detections")
    detections: list[tuple[float, float, float, float]] = []
    if not isinstance(rows, list) or not all(isinstance(r, list) and len(r) == 4 and all(is_number(v) for v in r) for r in rows):
        failures.append("malformed-detections")
    else:
        detections = [tuple(float(v) for v in r) for r in rows]
    if failures:
        state = "UNCERTAIN"
    elif _verdict(sensor, "statistical") == "fail":
        state, failures = "DEGRADED", ["sensor-statistical"]
    else:
        state = "NOMINAL"
    sequence = message.get("sequence") if is_int(message.get("sequence")) else None
    return RadarView(state, tuple(failures), origin if is_int(origin) else None, age, sequence, tuple(detections))


@dataclass(frozen=True)
class Corridor:
    ego_front_m: float
    mount_xy: tuple[float, float]
    half_width_m: float
    max_range_m: float
    closing_speed_sign: int


def nearest_in_corridor(detections: tuple[tuple[float, float, float, float], ...], corridor: Corridor
                        ) -> tuple[int, float, float] | None:
    """``(index, distance d, closing speed v)`` of the nearest in-corridor detection; ties keep the lower index."""

    best = None
    for index, (_alt, az, depth, vel) in enumerate(detections):
        x = corridor.mount_xy[0] + depth * math.cos(az)
        y = corridor.mount_xy[1] + depth * math.sin(az)
        d = x - corridor.ego_front_m
        if 0 <= d <= corridor.max_range_m and abs(y) <= corridor.half_width_m and (best is None or d < best[1]):
            best = (index, d, corridor.closing_speed_sign * vel)
    return best


@dataclass(frozen=True)
class Rule:
    distance_uncertainty_m: float
    speed_uncertainty_mps: float
    latency_ns: int
    deceleration_mps2: float
    margin_m: float
    brake_level: float
    release_speed_mps: float
    release_absent_cycles: int

    def conservative(self, d: float, v: float) -> tuple[float, float]:
        return d - self.distance_uncertainty_m, max(0.0, v + self.speed_uncertainty_mps)

    def residual(self, d: float, v: float) -> float:
        """AD-05 B runtime residual; the rule fires when it is ``<= 0`` on a present hypothesis."""

        d_c, v_c = self.conservative(d, v)
        t = self.latency_ns / 1e9
        return d_c - v_c * t - v_c * v_c / (2.0 * self.deceleration_mps2) - self.margin_m


class Latch:
    """R-2: once fired the request holds at ``brake_level`` until the conservative closing speed of a present
    hypothesis is ``<= release_speed_mps``, or the hypothesis is absent on ``release_absent_cycles`` consecutive
    decision cycles."""

    def __init__(self, rule: Rule) -> None:
        self.rule = rule
        self.latched = False
        self.absent = 0

    def decide(self, present: bool, fired: bool, v_c: float | None) -> float:
        """One decision cycle; return the request value."""

        if fired:
            self.latched, self.absent = True, 0
        elif self.latched:
            if present:
                self.absent = 0
                if v_c is not None and v_c <= self.rule.release_speed_mps:
                    self.latched = False
            else:
                self.absent += 1
                if self.absent >= self.rule.release_absent_cycles:
                    self.latched, self.absent = False, 0
        return self.rule.brake_level if self.latched else 0.0

    def hold(self) -> float:
        """A step that is not a decision cycle (no input): the latch neither counts nor releases."""

        return self.rule.brake_level if self.latched else 0.0


def rule_declaration(prefix: str) -> dict[str, tuple]:
    """The identifiers of one rule-and-latch set (``aeb`` for U4, ``fallback`` for U5)."""

    return {f"{prefix}.distanceUncertaintyM": ("non-negative-number",), f"{prefix}.speedUncertaintyMps": ("non-negative-number",),
            f"{prefix}.latencyNs": ("non-negative-int",), f"{prefix}.decelerationMps2": ("positive-number",),
            f"{prefix}.marginM": ("non-negative-number",), f"{prefix}.brakeLevel": ("unit-interval-open-low",),
            f"{prefix}.releaseSpeedMps": ("non-negative-number",), f"{prefix}.releaseAbsentCycles": ("positive-int",)}


def rule_from(values: dict[str, Any], prefix: str) -> Rule:
    return Rule(float(values[f"{prefix}.distanceUncertaintyM"]), float(values[f"{prefix}.speedUncertaintyMps"]),
                values[f"{prefix}.latencyNs"], float(values[f"{prefix}.decelerationMps2"]), float(values[f"{prefix}.marginM"]),
                float(values[f"{prefix}.brakeLevel"]), float(values[f"{prefix}.releaseSpeedMps"]),
                values[f"{prefix}.releaseAbsentCycles"])


SHARED_DECLARATION = {"vehicle.egoFrontM": ("non-negative-number",), "radar.mountM": ("xy",), "radar.closingSpeedSign": ("sign",)}


def corridor_from(values: dict[str, Any], prefix: str) -> Corridor:
    mount = values["radar.mountM"]
    return Corridor(float(values["vehicle.egoFrontM"]), (float(mount[0]), float(mount[1])),
                    float(values[f"{prefix}.corridor.halfWidthM"]), float(values[f"{prefix}.corridor.maxRangeM"]),
                    values["radar.closingSpeedSign"])
