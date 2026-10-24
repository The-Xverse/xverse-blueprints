"""Offline AD-06/AD-07 window/deadline checks (WP-17d, review findings 1–2).

Every scientific input is read by identifier through an admitted Protocol. Arithmetic is exact over the canonical
stored representation of each decoded numeric value; this does not recover arbitrary-precision original JSON tokens.
The full report is offline metadata, never a runtime projection or evidence of physical safety/fitness for purpose.
"""
from __future__ import annotations

import copy
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

from .protocol import IDENTIFIER, Protocol, ProtocolRefused, RUNTIME_LIMIT

BINDINGS_ID = "timing.tableBindings"
BINDINGS_SCHEMA = "assured-aeb.timing-bindings/1"
TABLE_SCHEMA = "assured-aeb.window-deadline-tables/1"
NS_PER_SECOND = 1_000_000_000  # exact SI unit conversion, not a protocol parameter
ROUTE = ("camera", "front-zone", "adas-ad-hpc", "vehicle-control-hpc", "chassis-zone", "brake-esc")
TRANSITION_SCOPE = "request-to-confirmed-total"
CONFIRMATION_SCOPE = "selector-to-confirmed"


class TableRefused(ValueError):
    """No accepted table exists; assessment retains the offline input/check diagnostics."""

    def __init__(self, code: str, detail: str, assessment: dict | None = None):
        self.code, self.assessment = code, copy.deepcopy(assessment)
        super().__init__(f"{code}: {detail}")


def _refuse(code, detail):
    raise TableRefused(code, detail, {"valid": False, "status": "input-refused", "code": code, "detail": detail})


def _members(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        _refuse("TABLE-BINDINGS", f"{label} members must be exactly {sorted(names)}")
    return value


def _identity(value):
    return isinstance(value, str) and bool(value.strip()) and "\n" not in value and "\x00" not in value


def _exact(value):
    q = Fraction(value)
    return {"numerator": str(q.numerator), "denominator": str(q.denominator)}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class _Inputs:
    def __init__(self, protocol):
        self.protocol, self.entries = protocol, {}

    def entry(self, identifier, unit=None):
        if not isinstance(identifier, str) or IDENTIFIER.fullmatch(identifier) is None:
            _refuse("TABLE-IDENTIFIER", f"invalid identifier reference {identifier!r}")
        if identifier not in self.entries:
            try:
                entry = self.protocol.entry(identifier)
            except ProtocolRefused as error:
                _refuse("TABLE-PROTOCOL", str(error))
            if entry["category"] not in ("runtime", "scenario", "policy"):
                _refuse("TABLE-CATEGORY", f"{identifier}: oracle/fault/metric entries are not timing-table inputs")
            self.entries[identifier] = entry
        entry = self.entries[identifier]
        if unit is not None and entry["unit"] != unit:
            _refuse("TABLE-UNIT", f"{identifier}: expected {unit}, found {entry['unit']}")
        return entry

    def number(self, identifier, unit, *, positive=False, fraction=False):
        value = self.entry(identifier, unit)["value"]
        if type(value) not in (int, float):
            _refuse("TABLE-NUMBER", f"{identifier}: a decoded finite numeric value is required")
        try:
            # str(int/float) is the explicitly adopted canonical stored-decimal interpretation.
            decimal = Decimal(str(value))
            if not decimal.is_finite():
                raise ValueError("non-finite")
            out = Fraction(decimal)
        except (ValueError, ArithmeticError):
            _refuse("TABLE-NUMBER", f"{identifier}: invalid finite numeric value")
        if out < 0 or (positive and out == 0) or (fraction and out > 1):
            _refuse("TABLE-RANGE", f"{identifier}: value outside its declared nonnegative/positive/fraction domain")
        return out

    def ns(self, identifier, *, positive=False):
        value = self.entry(identifier, "ns")["value"]
        if type(value) is not int or value < 0 or (positive and value == 0):
            _refuse("TABLE-NANOSECONDS", f"{identifier}: exact {'positive' if positive else 'nonnegative'} integer ns required")
        return value


def _bindings(inputs):
    entry = inputs.entry(BINDINGS_ID, "identifier-map")
    if entry["category"] != "policy":
        _refuse("TABLE-CATEGORY", "the table reference map is an offline policy entry")
    value = _members(entry["value"], {"schema", "envelope", "windows", "path", "deadlines", "semantics"}, "table bindings")
    if value["schema"] != BINDINGS_SCHEMA:
        _refuse("TABLE-BINDINGS", "unknown binding-map schema")
    _members(value["envelope"], {"worstGap", "maxClosingSpeed", "distanceUncertainty", "speedUncertainty", "deceleration",
                                "margin", "endToEnd", "reserveFraction"}, "envelope")
    _members(value["deadlines"], {"decisionCycle", "monitor", "transition", "confirmation", "fallback", "mrcRequest", "retainedValidity"}, "deadlines")
    _members(value["semantics"], {"transitionScope", "confirmationScope"}, "deadline semantics")
    if not isinstance(value["windows"], list) or not value["windows"] or not isinstance(value["path"], list) or not value["path"]:
        _refuse("TABLE-BINDINGS", "non-empty window and path declarations are required")
    ids = set()
    for item in value["windows"]:
        _members(item, {"itemId", "period", "latency", "slack", "freshness", "validity", "marginFraction", "maxClosingSpeed", "margin"}, "window")
        if not _identity(item["itemId"]) or item["itemId"] in ids:
            _refuse("TABLE-BINDINGS", "window identities must be unique")
        ids.add(item["itemId"])
    ids, position = set(), 0
    for stage in value["path"]:
        _members(stage, {"stageId", "from", "to", "latency"}, "path stage")
        if not _identity(stage["stageId"]) or stage["stageId"] in ids or stage["from"] != ROUTE[position]:
            _refuse("TABLE-PATH", "duplicate stage identity or discontinuous nominal route")
        ids.add(stage["stageId"])
        if stage["to"] == ROUTE[position]:
            continue  # declared per-unit computation, not an inferred zero-latency hop
        if position + 1 == len(ROUTE) or stage["to"] != ROUTE[position + 1]:
            _refuse("TABLE-PATH", "a path stage skips or leaves the required abstract route")
        position += 1
    if position + 1 != len(ROUTE):
        _refuse("TABLE-PATH", "the full camera-to-brake/ESC abstract route is not covered")
    return value


def _expiry_contract(*relative_terms):
    """Offline symbolic obligation; actual event/evidence timestamps are runtime inputs."""
    terms = [*relative_terms, "retainedEvidenceValidUntilNs[*]"]
    return {"runtimeExpiryTerms": terms,
            "runtimeObligation": "complete the declared response by min(" + ", ".join(terms) + "); runtime enforcement not verified here",
            "retainedEvidenceExpiryPolicy": "include every applicable retained-path evidence absolute validUntilNs; evidence can predate request/detection/selector; never rebase or restart its validity at those events"}


def generate(protocol: Protocol) -> dict:
    """Return an offline checked report; refuse inputs/inequalities without changing a declared value.

    These checks concern declared model bounds and deadline semantics. They do not prove that the runtime enforces
    earlier total/confirmation expiry, that any computation meets its declaration, or that a physical model is valid.
    """
    if not isinstance(protocol, Protocol):
        _refuse("TABLE-PROTOCOL", "an admitted offline Protocol object is required")
    inputs = _Inputs(protocol)
    binding = _bindings(inputs)
    rows = []

    def row(identifier, rule, refs, value, unit, relation, left, right, passed, *, check_unit=None, **details):
        refs = list(dict.fromkeys(refs))
        rows.append({"id": identifier, "rule": rule, "inputIds": refs,
                     "inputs": {key: copy.deepcopy(inputs.entries[key]) for key in refs},
                     "value": None if value is None else _exact(value), "unit": unit,
                     "check": {"relation": relation, "unit": unit if check_unit is None else check_unit,
                               "left": None if left is None else _exact(left),
                               "right": None if right is None else _exact(right), "passed": bool(passed)}, **details})

    for item in binding["windows"]:
        p, latency, slack = (inputs.ns(item[key], positive=key == "period") for key in ("period", "latency", "slack"))
        freshness, validity = inputs.ns(item["freshness"]), inputs.ns(item["validity"])
        minimum = p + latency + slack
        row(f"window.{item['itemId']}.freshness", "freshness >= period + declaredLatency + slack",
            [item[key] for key in ("period", "latency", "slack", "freshness")], minimum, "ns", ">=", freshness, minimum,
            freshness >= minimum, declaredValueNs=freshness, roundedLowerNs=math.ceil(Fraction(minimum)))
        fraction = inputs.number(item["marginFraction"], "1", fraction=True)
        margin = inputs.number(item["margin"], "m")
        speed = inputs.number(item["maxClosingSpeed"], "m/s")
        growth, allowance = speed * validity / NS_PER_SECOND, fraction * margin
        bound = allowance * NS_PER_SECOND / speed if speed else None
        row(f"window.{item['itemId']}.validity", "ODDMaxClosingSpeed * validity / nsPerSecond <= marginFraction * margin",
            [item[key] for key in ("validity", "marginFraction", "margin", "maxClosingSpeed")], growth, "m", "<=", growth, allowance,
            growth <= allowance, declaredValueNs=validity, boundKind="finite" if bound is not None else "unbounded-by-this-model",
            exactUpperNs=None if bound is None else _exact(bound), roundedUpperNs=None if bound is None else math.floor(bound),
            speedMeaning="declared physical ODD bound; not the conservative measured envelope speed")

    envelope = binding["envelope"]
    d = inputs.number(envelope["worstGap"], "m")
    v = inputs.number(envelope["maxClosingSpeed"], "m/s")
    dd = inputs.number(envelope["distanceUncertainty"], "m")
    dv = inputs.number(envelope["speedUncertainty"], "m/s")
    a = inputs.number(envelope["deceleration"], "m/s^2", positive=True)
    margin = inputs.number(envelope["margin"], "m")
    end_to_end = inputs.ns(envelope["endToEnd"], positive=True)
    dc, vc = d - dd, max(Fraction(0), v + dv)
    budget = dc - margin - vc * vc / (2 * a)
    row("envelope.conservativeDistance", "d_c = worstGap - distanceUncertainty",
        [envelope[key] for key in ("worstGap", "distanceUncertainty")], dc, "m", "definition", dc, dc, True)
    row("envelope.conservativeSpeed", "v_c = max(0, worstMeasuredClosingSpeed + speedUncertainty)",
        [envelope[key] for key in ("maxClosingSpeed", "speedUncertainty")], vc, "m/s", "definition", vc, vc, True,
        speedMeaning="conservative measured maximum plus declared uncertainty; distinct from physical ODD validity bound")
    bound = budget * NS_PER_SECOND / vc if vc else None
    if budget < 0:
        kind, passed = "no-solution", False
    elif bound is None:
        kind, passed = "unbounded-by-this-model", True
    else:
        kind = "zero-budget" if bound == 0 else "finite"
        passed = end_to_end <= math.floor(bound)
    row("envelope.endToEnd", "d_c - v_c*T - v_c^2/(2*a_b) >= margin; T boundary = (d_c-margin-v_c^2/(2*a_b))/v_c",
        list(envelope[key] for key in ("worstGap", "maxClosingSpeed", "distanceUncertainty", "speedUncertainty", "deceleration", "margin", "endToEnd")),
        bound, "ns", "<=" if bound is not None else ">=",
        end_to_end if bound is not None else budget, math.floor(bound) if bound is not None else 0, passed,
        check_unit="ns" if bound is not None else "m",
        boundKind=kind, roundedUpperNs=None if bound is None else math.floor(bound), declaredValueNs=end_to_end,
        constantDistanceBudgetM=_exact(budget), brakingDistanceM=_exact(vc * vc / (2 * a)),
        triggerDistinction="AD-05 <= is the brake-needed predicate; this >= side defines available delay, not a new safety claim")

    fraction = inputs.number(envelope["reserveFraction"], "1", fraction=True)
    reserve_exact = fraction * end_to_end
    reserve = math.ceil(reserve_exact)
    row("budget.reserve", "reserve = ceil(reserveFraction * declaredEndToEndNs)",
        [envelope["reserveFraction"], envelope["endToEnd"]], reserve_exact, "ns", ">=", reserve, reserve_exact,
        reserve >= reserve_exact, roundedLowerNs=reserve)
    total, path_refs = 0, []
    for stage in binding["path"]:
        latency = inputs.ns(stage["latency"])
        total += latency
        path_refs.append(stage["latency"])
        row(f"path.{stage['stageId']}", "declared AD-30 stage latency; no inferred allocation", [stage["latency"]], latency,
            "ns", "definition", latency, latency, True, routeFrom=stage["from"], routeTo=stage["to"])
    available = end_to_end - reserve
    row("budget.path", "sum(declared stage latencies) <= declaredEndToEndNs - ceil(reserveFraction * declaredEndToEndNs)",
        [*path_refs, envelope["endToEnd"], envelope["reserveFraction"]], total, "ns", "<=", total, available, total <= available,
        reserveNs=reserve, availableNs=available, remainingNs=available-total, abstractRoute=list(ROUTE))

    deadlines = binding["deadlines"]
    values = {key: inputs.ns(identifier, positive=True) for key, identifier in deadlines.items()}
    semantics = binding["semantics"]
    scopes = {key: inputs.entry(identifier, "scope")["value"] for key, identifier in semantics.items()}
    if scopes != {"transitionScope": TRANSITION_SCOPE, "confirmationScope": CONFIRMATION_SCOPE}:
        _refuse("TABLE-DEADLINE-SCOPE", "explicit total-transition and post-selector confirmation scopes are required")
    row("deadline.monitor", "monitorDeadline <= decisionCycle", [deadlines["monitor"], deadlines["decisionCycle"]],
        values["monitor"], "ns", "<=", values["monitor"], values["decisionCycle"], values["monitor"] <= values["decisionCycle"])
    row("deadline.transition", "total request-to-confirmed transitionDeadline <= retainedValidity",
        [deadlines["transition"], deadlines["retainedValidity"], semantics["transitionScope"]], values["transition"], "ns", "<=",
        values["transition"], values["retainedValidity"], values["transition"] <= values["retainedValidity"],
        **_expiry_contract("requestTimeNs + totalTransitionDeadlineNs"))
    row("deadline.confirmation", "post-selector confirmationDeadline <= total transitionDeadline (included phase; do not add T+C)",
        [deadlines["confirmation"], deadlines["transition"], deadlines["retainedValidity"], semantics["transitionScope"], semantics["confirmationScope"]],
        values["confirmation"], "ns", "<=", values["confirmation"], values["transition"], values["confirmation"] <= values["transition"],
        **_expiry_contract("requestTimeNs + totalTransitionDeadlineNs", "selectorTimeNs + confirmationDeadlineNs"))
    for key in ("fallback", "mrcRequest"):
        row(f"deadline.{key}", "loss-detection-to-request deadline <= retainedValidity", [deadlines[key], deadlines["retainedValidity"]],
            values[key], "ns", "<=", values[key], values["retainedValidity"], values[key] <= values["retainedValidity"],
            scope="request emission only; no external MRC execution/effectiveness claim",
            **_expiry_contract("lossDetectionTimeNs + " + key + "DeadlineNs"))

    metadata = protocol.metadata()
    if protocol.kind == "principal":
        inputs.entry(RUNTIME_LIMIT)  # retain the entry consumed by metadata(), too
    report = {"schema": TABLE_SCHEMA, "valid": all(item["check"]["passed"] for item in rows),
              "protocol": metadata, "generatorSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "arithmetic": "exact rational over canonical str(decoded int/finite float); original JSON decimal precision not preserved",
              "rounding": {"lowerBoundsAndReserve": "ceil", "upperBounds": "floor", "timeUnit": "integer ns"},
              "clockLimit": "one canonical monotonic simulator clock; synchronization-fault robustness not established",
              "inputs": copy.deepcopy(inputs.entries), "rows": rows,
              "limits": ["offline declared-model algebra only; no physical-safety, runtime-enforcement or fitness claim",
                         "full table/source metadata is excluded from runtime units and projections"]}
    report["tableSha256"] = hashlib.sha256(_json(report)).hexdigest()
    if not report["valid"]:
        failed = [item["id"] for item in rows if not item["check"]["passed"]]
        raise TableRefused("TABLE-CHECK", "declared timing values fail: " + ", ".join(failed), report)
    return report
