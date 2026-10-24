"""U5 ``vc-functional`` productive logic: radar-only fallback and functional arbiter (WP-13 #1; review-wp13-logic finding 1
§1.6-1.7).

``RadarFallback`` applies the AD-05 rule to the direct radar stream, F09 through ``vc-ingress``. It fires only within the
degraded-ODD ego-speed bound (FR-028, FR-029). The ego speed comes from the qualified vehicle-state evidence that the
WP-14 validator supplies.

``FunctionalArbiter`` follows the restricted form of R-3 (decisions.md "WP-13 R-1 to R-7"):
- it never selects a source other than the selector's;
- with no fresh, finite request from that source, it holds that source's last valid request for at most the hold
  window, then requests 0.0 with ``no-valid-source``;
- ``UNCERTAIN`` and ``UNSAFE`` are forwarded in the arbiter-cycle evidence, keyed by the request sequence, and not acted
  on.

WP-15 DN-1 supersedes the terminal live-source alternatives: terminal entry snapshots the last emitted clamped
request, including zero, and irreversibly holds it. With no prior emission only the existing neutral initial zero
is held, explicitly identified in evidence. No external MRC is executed and no availability credit is implied.

The ``brake-request`` keeps exactly the five WP-04 members, so the chassis zone accepts it.
"""

from __future__ import annotations

import math
from typing import Any

from .aeb_rule import (SHARED_DECLARATION, Latch, corridor_from, nearest_in_corridor, qualify_radar, rule_declaration,
                       rule_from, weakest)
from .brake_esc import BRAKE_MAX, BRAKE_MIN, brake_request
from .checks import is_int, is_number
from .parameters import Projection, params_digest

FALLBACK_REQUEST = "assured-aeb.fallback-request/1"
ADAS_CYCLE = "assured-aeb.adas-cycle/1"
SELECTOR = "assured-aeb.selector-command/1"
ARBITER_CYCLE = "assured-aeb.arbiter-cycle/1"
RADAR_STREAM = "f09-radar-vc"
USABLE = ("NOMINAL", "DEGRADED")
CONFIGURATIONS = ("C_NOMINAL", "C_DEGRADED_RADAR", "S_MRC_REQUESTED")
#: Configuration semantics (Note 21 [N] 1515, 1519): sourced, not parameters. ``S_MRC_REQUESTED`` is declared.
SOURCE_OF = {"C_NOMINAL": "adas-cycle", "C_DEGRADED_RADAR": "fallback-request"}
SCHEMA_OF = {"adas-cycle": ADAS_CYCLE, "fallback-request": FALLBACK_REQUEST}
SOURCE_ELEMENT = {"adas-cycle": "fusion-risk-aeb", "fallback-request": "radar-fallback"}

FALLBACK_DECLARATION: dict[str, tuple] = {
    **SHARED_DECLARATION,
    "fallback.corridor.halfWidthM": ("positive-number",), "fallback.corridor.maxRangeM": ("positive-number",),
    "fallback.radarFreshnessNs": ("positive-int",), "fallback.vehicleStateFreshnessNs": ("positive-int",),
    "fallback.oddMaxEgoSpeedMps": ("positive-number",),
    **rule_declaration("fallback"),
}
ARBITER_DECLARATION: dict[str, tuple] = {
    "arbiter.requestFreshnessNs": ("positive-int",), "arbiter.holdWindowNs": ("non-negative-int",),
}


class RadarFallback:
    def __init__(self, projection: Projection) -> None:
        if type(projection) is not Projection:
            raise TypeError("a validated Projection is required (no default parameters)")
        self.values = projection.take(FALLBACK_DECLARATION)
        self.params_sha256 = params_digest(self.values)
        self.corridor = corridor_from(self.values, "fallback")
        self.rule = rule_from(self.values, "fallback")
        self.latch = Latch(self.rule)
        self.radar: Any = None
        self.speed: Any = None
        self.sequence = 0
        self.cycle = 0

    def _ego(self, now_ns: int) -> tuple[str, str | None, dict[str, Any]]:
        speed = self.speed
        if not (isinstance(speed, dict) and set(speed) == {"speedMps", "originNs", "state"} and is_number(speed["speedMps"])
                and speed["speedMps"] >= 0 and is_int(speed["originNs"])):
            return "UNCERTAIN", "ego-speed-unknown", {"state": "UNCERTAIN", "speedMps": None, "ageNs": None}
        age = now_ns - speed["originNs"]
        record = {"state": weakest(speed["state"]), "speedMps": float(speed["speedMps"]), "ageNs": age}
        if age < 0 or age > self.values["fallback.vehicleStateFreshnessNs"] or record["state"] not in USABLE:
            return "UNCERTAIN", "ego-speed-unknown", record
        if speed["speedMps"] > self.values["fallback.oddMaxEgoSpeedMps"]:
            return "UNSAFE", "outside-degraded-odd", record
        return record["state"], None, record

    def step(self, now_ns: int, *, radar: Any = None, ego_speed: Any = None) -> dict[str, Any]:
        if not is_int(now_ns):
            raise ValueError("simulation time must be integer nanoseconds")
        self.sequence += 1
        if radar is not None:
            self.radar = radar
        if ego_speed is not None:
            self.speed = ego_speed
        decision = radar is not None
        if decision:
            self.cycle += 1
        view = qualify_radar(self.radar, RADAR_STREAM, now_ns, self.values["fallback.radarFreshnessNs"]) if self.radar is not None \
            else None
        radar_state = view.state if view is not None else "UNCERTAIN"
        ego_state, gate_reason, ego = self._ego(now_ns)
        selected = nearest_in_corridor(view.detections, self.corridor) if view is not None and radar_state in USABLE else None
        hypothesis = {"present": False, "agreement": "radar-only", "distanceM": None, "closingSpeedMps": None,
                      "distanceUncertaintyM": self.rule.distance_uncertainty_m,
                      "speedUncertaintyMps": self.rule.speed_uncertainty_mps, "residualM": None}
        reason = None
        if not decision:
            reason = "no-input"
        elif radar_state not in USABLE:
            reason = "radar-unusable"
        elif gate_reason is not None:
            reason = gate_reason
        if selected is not None:
            hypothesis["distanceM"], hypothesis["closingSpeedMps"] = selected[1], selected[2]
            hypothesis["present"] = True
        fired, v_c = False, None
        if hypothesis["present"]:
            hypothesis["residualM"] = self.rule.residual(selected[1], selected[2])
            v_c = self.rule.conservative(selected[1], selected[2])[1]
            fired = reason is None and hypothesis["residualM"] <= 0  # the ODD gate and the ego speed gate firing only
        if not decision:
            request = self.latch.hold()
        elif radar_state not in USABLE or ego_state not in USABLE:
            request = self.latch.uncertain()
        else:
            request = self.latch.decide(hypothesis["present"], fired, v_c)
        state = "UNCERTAIN" if not decision else weakest(radar_state, ego_state)
        return {"schema": FALLBACK_REQUEST, "source": "radar-fallback", "cycle": self.cycle, "sequence": self.sequence,
                "originNs": now_ns, "brakeRequest": request, "fired": fired, "latched": self.latch.latched, "reason": reason,
                "hypothesis": hypothesis,
                "sources": {"radar": {"state": radar_state, "originNs": view.origin_ns if view else None,
                                      "ageNs": view.age_ns if view else None, "sequence": view.sequence if view else None,
                                      "count": len(view.detections) if view else None,
                                      "failures": list(view.failures) if view else ["no-radar"],
                                      "selectedDetection": selected[0] if selected else None},
                            "egoSpeed": ego},
                "state": state, "paramsSha256": self.params_sha256}


class FunctionalArbiter:
    """One brake request per decision cycle, following only the configuration manager's selector (A-3)."""

    def __init__(self, projection: Projection) -> None:
        if type(projection) is not Projection:
            raise TypeError("a validated Projection is required (no default parameters)")
        if "arbiter.mrcSource" in projection.entries:
            raise ValueError("arbiter.mrcSource: obsolete terminal live-source parameter; WP-15 DN-1 requires entry-value hold")
        self.values = projection.take(ARBITER_DECLARATION)
        self.params_sha256 = params_digest(self.values)
        self.configuration: str | None = None
        self.selector_sequence: int | None = None
        self.last_used: dict[str, int] = {}  # per source: the last request sequence used
        self.last_valid: dict[str, dict[str, Any]] = {}  # per source: the last valid request (R-3 hold, per source)
        self.last_emitted_value: float | None = None
        self.terminal_value: float | None = None
        self.terminal_hold_provenance: str | None = None
        self.sequence = 0
        self.qualified_seen = 0
        self.evidence: list[dict[str, Any]] = []

    def _selected(self) -> str | None:
        return SOURCE_OF.get(self.configuration)

    def _accept_selector(self, message: Any, refusals: list[str]) -> None:
        if not (isinstance(message, dict) and set(message) == {"schema", "source", "sequence", "originNs", "configuration"}
                and message["schema"] == SELECTOR and is_int(message["sequence"]) and is_int(message["originNs"])):
            refusals.append("selector-malformed")
        elif message["source"] != "configuration-manager":
            refusals.append("selector-wrong-source")
        elif message["configuration"] not in CONFIGURATIONS:
            refusals.append("selector-unknown-configuration")
        elif self.selector_sequence is not None and message["sequence"] <= self.selector_sequence:
            refusals.append("selector-replayed")
        elif self.configuration == "S_MRC_REQUESTED":
            refusals.append("selector-terminal-already-entered" if message["configuration"] == "S_MRC_REQUESTED"
                            else "selector-terminal-lockout")
        else:
            self.configuration, self.selector_sequence = message["configuration"], message["sequence"]
            if self.configuration == "S_MRC_REQUESTED":
                self.terminal_value = self.last_emitted_value if self.last_emitted_value is not None else 0.0
                self.terminal_hold_provenance = ("last-emitted-request" if self.last_emitted_value is not None
                                                 else "initial-neutral-no-prior-emission")

    def step(self, now_ns: int, inbox: list[tuple[str, Any]]) -> dict[str, Any]:
        """One decision cycle: return exactly one WP-04 ``brake-request``; append one arbiter-cycle evidence record."""

        if not is_int(now_ns):
            raise ValueError("simulation time must be integer nanoseconds")
        refusals: list[str] = []
        requests: dict[str, list[Any]] = {"adas-cycle": [], "fallback-request": []}
        for interface, message in inbox:
            if interface == "selector-command":
                self._accept_selector(message, refusals)
            elif interface in requests:
                requests[interface].append(message)
            elif interface == "qualified-evidence":
                self.qualified_seen += 1  # received and counted only; its use is WP-14's
            else:
                refusals.append(f"undeclared-interface-{interface}")
        selected = self._selected()
        kind, value, raw, clamped, chosen, flags = "no-selector", 0.0, None, False, None, []
        if self.configuration == "S_MRC_REQUESTED":
            kind, value = "terminal-entry-value-hold", self.terminal_value
        if selected is not None:
            fresh = None
            for message in sorted((m for m in requests[selected] if isinstance(m, dict) and is_int(m.get("sequence"))),
                                  key=lambda m: m["sequence"]):
                ok = (message.get("schema") == SCHEMA_OF[selected] and message.get("source") == SOURCE_ELEMENT[selected]
                      and is_int(message.get("originNs")) and message["sequence"] > self.last_used.get(selected, -1))
                if not ok:
                    flags.append("request-refused")
                    continue
                self.last_used[selected] = message["sequence"]
                age = now_ns - message["originNs"]
                if not is_number(message.get("brakeRequest")):
                    flags.append("non-finite")
                elif 0 <= age <= self.values["arbiter.requestFreshnessNs"]:
                    fresh = message
                else:
                    flags.append("stale")
            if fresh is not None:
                kind, chosen, raw = "fresh", fresh, float(fresh["brakeRequest"])
                self.last_valid[selected] = fresh
            else:
                held = self.last_valid.get(selected)
                if held is not None and 0 <= now_ns - held["originNs"] <= self.values["arbiter.holdWindowNs"]:
                    kind, chosen, raw = "held", held, float(held["brakeRequest"])
                else:
                    kind = "no-valid-source"
            if raw is not None:
                value = min(BRAKE_MAX, max(BRAKE_MIN, raw))
                clamped = value != raw
        if not math.isfinite(value):  # unreachable: raw values are finite; kept as a guard
            value, kind = 0.0, "no-valid-source"
        self.sequence += 1
        request = brake_request(self.sequence, now_ns, value)
        self.last_emitted_value = request["value"]
        self.evidence.append({"schema": ARBITER_CYCLE, "sequence": self.sequence, "originNs": now_ns,
                              "configuration": self.configuration, "selectorSequence": self.selector_sequence,
                              "selectedInterface": selected, "kind": kind, "value": value, "rawValue": raw, "clamped": clamped,
                              "sourceSequence": chosen["sequence"] if chosen else None,
                              "sourceOriginNs": chosen["originNs"] if chosen else None,
                              "forwardedState": chosen.get("state") if chosen else None,
                              "forwardedReason": chosen.get("reason") if chosen else None,
                              "terminalHoldProvenance": self.terminal_hold_provenance,
                              "flags": sorted(set(flags)), "refusals": refusals, "paramsSha256": self.params_sha256})
        return request
