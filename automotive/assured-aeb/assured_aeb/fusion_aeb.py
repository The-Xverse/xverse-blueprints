"""U4 ``fusion-risk-aeb``: fusion, risk and the AEB decision without ML inside (WP-13 #1; review-wp13-logic finding 1
§1.5).

The inputs are the intra-unit ``perception-output`` (increment #3 produces it) and F08 radar evidence. The output is one
``assured-aeb.adas-cycle/1`` record per simulator step, sent on F11 to ``vc-ingress``. The rules:
- **R-1:** in ``C_NOMINAL`` an obstacle is present only when the camera is positive **and** radar corroborates it.
- **R-2:** the request latches.
- **R-6:** a step with an input is a decision cycle, and a step without one still yields a ``no-input`` record.

Every value is read by identifier from the FR-028 projection.
"""

from __future__ import annotations

import math
from typing import Any

from .aeb_rule import (SHARED_DECLARATION, Latch, corridor_from, nearest_in_corridor, qualify_radar, rule_declaration,
                       rule_from, weakest)
from .checks import HEX64, is_int, is_number
from .parameters import Projection, params_digest

PERCEPTION_OUTPUT = "assured-aeb.perception-output/1"
ADAS_CYCLE = "assured-aeb.adas-cycle/1"
SOURCE = "fusion-risk-aeb"
RADAR_STREAM = "f08-radar-adas"
PERCEPTION_MEMBERS = frozenset({"schema", "source", "frame", "frameSha256", "originNs", "occupancyProbability",
                                "binProbabilities", "predictedBin", "oodScore", "oodFlag", "inputQuality", "provenance",
                                "state", "reason"})
USABLE = ("NOMINAL", "DEGRADED")

DECLARATION: dict[str, tuple] = {
    **SHARED_DECLARATION,
    "fusion.corridor.halfWidthM": ("positive-number",), "fusion.corridor.maxRangeM": ("positive-number",),
    "fusion.cameraFreshnessNs": ("positive-int",), "fusion.radarFreshnessNs": ("positive-int",),
    "fusion.occupancyThreshold": ("probability",), "fusion.distanceBinEdgesM": ("increasing-positive-list",),
    "fusion.associationToleranceM": ("non-negative-number",),
    **rule_declaration("aeb"),
}


def bin_interval(predicted: Any, edges: list[float]) -> tuple[float, float] | None:
    """The distance interval of a WP-09 bin label (``overlap``, ``bin-i``, ``beyond``); ``None`` for no interval."""

    if predicted == "overlap":
        return (-math.inf, 0.0)
    if predicted == "beyond":
        return (edges[-1], math.inf)
    if isinstance(predicted, str) and predicted.startswith("bin-") and predicted[4:].isdigit():
        i = int(predicted[4:])
        if i < len(edges):
            return (0.0 if i == 0 else edges[i - 1], edges[i])
    return None


def _perception_ok(record: Any) -> bool:
    return (isinstance(record, dict) and set(record) == PERCEPTION_MEMBERS and record["schema"] == PERCEPTION_OUTPUT
            and record["source"] == "perception" and is_int(record["originNs"]) and isinstance(record["frameSha256"], str)
            and HEX64.match(record["frameSha256"]) is not None and is_number(record["occupancyProbability"])
            and 0 <= record["occupancyProbability"] <= 1 and type(record["oodFlag"]) is bool and isinstance(record["state"], str))


class FusionRiskAeb:
    def __init__(self, projection: Projection) -> None:
        if type(projection) is not Projection:
            raise TypeError("a validated Projection is required (no default parameters)")
        self.values = projection.take(DECLARATION)
        self.params_sha256 = params_digest(self.values)
        self.corridor = corridor_from(self.values, "fusion")
        self.rule = rule_from(self.values, "aeb")
        self.latch = Latch(self.rule)
        self.edges = [float(e) for e in self.values["fusion.distanceBinEdgesM"]]
        self.camera: dict[str, Any] | None = None
        self.radar: dict[str, Any] | None = None
        self.sequence = 0
        self.cycle = 0

    def step(self, now_ns: int, *, radar: Any = None, perception: Any = None) -> dict[str, Any]:
        """One simulator step; ``radar`` and ``perception`` are the items delivered at this step (or ``None``)."""

        if not is_int(now_ns):
            raise ValueError("simulation time must be integer nanoseconds")
        self.sequence += 1
        if radar is not None:
            self.radar = radar
        if perception is not None:
            self.camera = perception
        decision = radar is not None or perception is not None
        if decision:
            self.cycle += 1
        camera_src, camera_state, camera_rec = self._camera(now_ns)
        view = qualify_radar(self.radar, RADAR_STREAM, now_ns, self.values["fusion.radarFreshnessNs"]) if self.radar is not None \
            else None
        radar_state = view.state if view is not None else "UNCERTAIN"
        selected = nearest_in_corridor(view.detections, self.corridor) if view is not None and view.state in USABLE else None
        hypothesis = {"present": False, "agreement": None, "distanceM": None, "closingSpeedMps": None,
                      "distanceUncertaintyM": self.rule.distance_uncertainty_m, "speedUncertaintyMps": self.rule.speed_uncertainty_mps,
                      "residualM": None}
        reason, outcome = None, None
        if not decision:
            reason = "no-input"
        elif camera_state not in USABLE:
            reason = "camera-unusable"
        elif radar_state not in USABLE:
            reason = "radar-unusable"
        else:
            positive = camera_rec["occupancyProbability"] >= self.values["fusion.occupancyThreshold"] and not camera_rec["oodFlag"]
            interval = bin_interval(camera_rec["predictedBin"], self.edges)
            tol = self.values["fusion.associationToleranceM"]
            associated = positive and selected is not None and interval is not None \
                and interval[0] - tol <= selected[1] <= interval[1] + tol
            if associated:
                agreement = "agree"
            elif positive:
                agreement, outcome = "camera-only", "UNCERTAIN"
            elif selected is not None:
                agreement, outcome = "radar-only", "DEGRADED"
            else:
                agreement = "none"
            hypothesis["agreement"] = agreement
            if selected is not None:
                hypothesis["distanceM"], hypothesis["closingSpeedMps"] = selected[1], selected[2]
            hypothesis["present"] = associated
        fired, v_c = False, None
        if hypothesis["present"]:
            hypothesis["residualM"] = self.rule.residual(hypothesis["distanceM"], hypothesis["closingSpeedMps"])
            fired = hypothesis["residualM"] <= 0
            v_c = self.rule.conservative(hypothesis["distanceM"], hypothesis["closingSpeedMps"])[1]
        request = self.latch.decide(hypothesis["present"], fired, v_c) if decision else self.latch.hold()
        state = "UNCERTAIN" if not decision else weakest(camera_state, radar_state, *([outcome] if outcome else []))
        return {"schema": ADAS_CYCLE, "source": SOURCE, "cycle": self.cycle, "sequence": self.sequence, "originNs": now_ns,
                "brakeRequest": request, "fired": fired, "latched": self.latch.latched, "reason": reason,
                "hypothesis": hypothesis,
                "sources": {"camera": camera_src,
                            "radar": {"state": radar_state, "originNs": view.origin_ns if view else None,
                                      "ageNs": view.age_ns if view else None, "sequence": view.sequence if view else None,
                                      "count": len(view.detections) if view else None,
                                      "failures": list(view.failures) if view else ["no-radar"],
                                      "selectedDetection": selected[0] if selected else None}},
                "state": state, "paramsSha256": self.params_sha256}

    def _camera(self, now_ns: int) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
        record = self.camera
        if record is None:
            return {"state": "UNCERTAIN", "failures": ["no-perception-output"], "originNs": None, "ageNs": None,
                    "frameSha256": None, "occupancyProbability": None, "predictedBin": None, "oodFlag": None,
                    "provenance": None}, "UNCERTAIN", None
        if not _perception_ok(record):
            return {"state": "UNCERTAIN", "failures": ["perception-output-malformed"], "originNs": None, "ageNs": None,
                    "frameSha256": None, "occupancyProbability": None, "predictedBin": None, "oodFlag": None,
                    "provenance": None}, "UNCERTAIN", None
        age = now_ns - record["originNs"]
        failures = []
        state = weakest(record["state"])
        if age < 0 or age > self.values["fusion.cameraFreshnessNs"]:
            failures.append("stale")
            state = weakest(state, "UNCERTAIN")
        return {"state": state, "failures": failures, "originNs": record["originNs"], "ageNs": age,
                "frameSha256": record["frameSha256"], "occupancyProbability": record["occupancyProbability"],
                "predictedBin": record["predictedBin"], "oodFlag": record["oodFlag"],
                "provenance": record["provenance"]}, state, record
