"""WP-17d OFFLINE synthetic controls. Every fixture value is TEST-ONLY.

These stdlib-only tests also collect under pytest. They exercise genuine Protocol admission;
none of their physical values, clock budgets or source references selects a scientific protocol.
"""
from __future__ import annotations

import ast
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from assured_aeb.protocol import Protocol, RECORD_SCHEMA
from assured_aeb import window_tables as W


def entry(value, unit, category="policy"):
    return {"value": value, "unit": unit, "category": category, "status": "provisional",
            "source": {"kind": "policy", "reference": "TEST-ONLY synthetic timing fixture; no scientific approval"}}


def record():
    entries = {}

    def add(name, value, unit, category="policy"):
        identifier = "test." + name
        entries[identifier] = entry(value, unit, category)
        return identifier

    envelope = {key: add(key, value, unit, "scenario" if key in ("worstGap", "maxClosingSpeed") else "policy")
                for key, value, unit in (("worstGap", 100, "m"), ("maxClosingSpeed", 10, "m/s"),
                    ("distanceUncertainty", 1, "m"), ("speedUncertainty", 0, "m/s"),
                    ("deceleration", 5, "m/s^2"), ("margin", 5, "m"),
                    ("endToEnd", 8_000_000_000, "ns"), ("reserveFraction", 0.1, "1"))}
    window = {"itemId": "TEST-ONLY-camera"}
    for key, value, unit in (("period", 20_000_000, "ns"), ("latency", 10_000_000, "ns"),
                            ("slack", 5_000_000, "ns"), ("freshness", 35_000_000, "ns"),
                            ("validity", 200_000_000, "ns"), ("marginFraction", 0.5, "1"),
                            ("maxClosingSpeed", 10, "m/s"), ("margin", 5, "m")):
        window[key] = add("window" + key, value, unit)
    path = [{"stageId": f"TEST-ONLY-stage{i}", "from": source, "to": target,
             "latency": add(f"stage{i}", 10_000_000, "ns")}
            for i, (source, target) in enumerate(zip(W.ROUTE, W.ROUTE[1:]))]
    deadlines = {key: add(key, value, "ns") for key, value in
                 (("decisionCycle", 20_000_000), ("monitor", 10_000_000), ("transition", 100_000_000),
                  ("confirmation", 40_000_000), ("fallback", 100_000_000), ("mrcRequest", 100_000_000),
                  ("retainedValidity", 200_000_000))}
    semantics = {"transitionScope": add("transitionScope", W.TRANSITION_SCOPE, "scope"),
                 "confirmationScope": add("confirmationScope", W.CONFIRMATION_SCOPE, "scope")}
    entries[W.BINDINGS_ID] = entry({"schema": W.BINDINGS_SCHEMA, "envelope": envelope,
        "windows": [window], "path": path, "deadlines": deadlines, "semantics": semantics}, "identifier-map")
    return {"schema": RECORD_SCHEMA, "recordId": "TEST-ONLY-WP17d", "declaredAt": "2026-10-24T00:00:00Z", "entries": entries}


def admitted(rec):
    raw = json.dumps(rec, sort_keys=True, allow_nan=False).encode()
    return Protocol.characterisation(raw, expected_digest=hashlib.sha256(raw).hexdigest(), started_at="2026-10-24T00:00:01Z")


def setvalue(rec, name, value):
    rec["entries"]["test." + name]["value"] = value


def rows(report):
    return {row["id"]: row for row in report["rows"]}


def rational(value):
    return Fraction(int(value["numerator"]), int(value["denominator"]))


class WindowTablesTests(unittest.TestCase):
    def refused(self, rec, code="TABLE-CHECK", row=None):
        with self.assertRaises(W.TableRefused) as caught:
            W.generate(admitted(rec))
        self.assertEqual(caught.exception.code, code)
        self.assertFalse(caught.exception.assessment["valid"])
        if row:
            self.assertFalse(rows(caught.exception.assessment)[row]["check"]["passed"])
        return caught.exception.assessment

    def test_valid_report_is_offline_deterministic_and_complete(self):
        protocol = admitted(record())
        seen, original = [], Protocol.entry
        def observed(obj, identifier):
            seen.append(identifier)
            return original(obj, identifier)
        with patch.object(Protocol, "entry", observed):
            report = W.generate(protocol)
        self.assertEqual(set(seen), set(report["inputs"]))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertTrue(report["protocol"]["engineeringDataOnly"])
        self.assertTrue(report["valid"])
        self.assertEqual(report, W.generate(protocol))
        self.assertEqual(report["inputs"], record()["entries"])
        for row in report["rows"]:
            self.assertTrue(row["rule"] and row["unit"])
            self.assertEqual(set(row["inputIds"]), set(row["inputs"]))
            for identifier in row["inputIds"]:
                self.assertEqual(row["inputs"][identifier], protocol.entry(identifier))
            self.assertTrue(row["check"]["passed"])
            self.assertIn(row["check"]["unit"], ("ns", "m", "m/s"))
        unhashed = copy.deepcopy(report)
        digest = unhashed.pop("tableSha256")
        self.assertEqual(digest, hashlib.sha256(json.dumps(unhashed, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest())
        report["inputs"]["test.margin"]["value"] = -1
        self.assertEqual(protocol.value("test.margin"), 5)

    def test_independent_fraction_reference_and_trigger_direction(self):
        report = rows(W.generate(admitted(record())))
        dc, vc, a, margin = Fraction(100)-1, Fraction(10), Fraction(5), Fraction(5)
        bound = (dc-margin-vc*vc/(2*a))/vc
        self.assertEqual(rational(report["envelope.endToEnd"]["value"]), bound*10**9)
        self.assertEqual(dc-vc*bound-vc*vc/(2*a), margin)
        self.assertIn("brake-needed", report["envelope.endToEnd"]["triggerDistinction"])
        self.assertEqual(rational(report["budget.reserve"]["value"]), 800_000_000)

    def test_equality_for_all_declared_bounds_is_allowed(self):
        rec = record()
        for name, value in (("endToEnd", 8_400_000_000), ("windowvalidity", 250_000_000),
                            ("monitor", 20_000_000), ("transition", 200_000_000),
                            ("confirmation", 200_000_000), ("fallback", 200_000_000), ("mrcRequest", 200_000_000)):
            setvalue(rec, name, value)
        binding = rec["entries"][W.BINDINGS_ID]["value"]
        # Exactly exhaust the remainder, without assuming any per-stage allocation policy.
        setvalue(rec, "stage0", 7_520_000_000)
        report = W.generate(admitted(rec))
        self.assertEqual(rows(report)["budget.path"]["remainingNs"], 0)

    def test_fractional_ns_bounds_round_conservatively(self):
        rec = record()
        for name, value in (("worstGap", 1.000000002), ("distanceUncertainty", 0), ("margin", 0),
                            ("maxClosingSpeed", 3), ("deceleration", 9), ("endToEnd", 166_666_667),
                            ("reserveFraction", 0.1), ("windowmargin", 1), ("windowmarginFraction", 0.1),
                            ("windowmaxClosingSpeed", 3), ("windowvalidity", 33_333_333)):
            setvalue(rec, name, value)
        report = rows(W.generate(admitted(rec)))
        self.assertEqual(report["envelope.endToEnd"]["roundedUpperNs"], 166_666_667)
        self.assertEqual(report["window.TEST-ONLY-camera.validity"]["roundedUpperNs"], 33_333_333)
        self.assertEqual(report["budget.reserve"]["roundedLowerNs"], 16_666_667)
        self.assertEqual(rational(report["budget.reserve"]["value"]), Fraction(166_666_667, 10))
        self.assertEqual(rational(report["window.TEST-ONLY-camera.validity"]["exactUpperNs"]), Fraction(100_000_000, 3))
        setvalue(rec, "endToEnd", 166_666_668)
        self.refused(rec, row="envelope.endToEnd")
        setvalue(rec, "endToEnd", 166_666_667)
        setvalue(rec, "windowvalidity", 33_333_334)
        self.refused(rec, row="window.TEST-ONLY-camera.validity")

    def test_failed_inequalities_retain_full_checks(self):
        failures = (("windowfreshness", 34_999_999, "window.TEST-ONLY-camera.freshness"),
                    ("windowvalidity", 250_000_001, "window.TEST-ONLY-camera.validity"),
                    ("endToEnd", 8_400_000_001, "envelope.endToEnd"),
                    ("stage0", 8_000_000_000, "budget.path"),
                    ("monitor", 20_000_001, "deadline.monitor"),
                    ("transition", 200_000_001, "deadline.transition"),
                    ("confirmation", 100_000_001, "deadline.confirmation"),
                    ("fallback", 200_000_001, "deadline.fallback"),
                    ("mrcRequest", 200_000_001, "deadline.mrcRequest"))
        for name, value, row in failures:
            with self.subTest(name=name):
                rec = record()
                setvalue(rec, name, value)
                report = self.refused(rec, row=row)
                self.assertEqual(report["inputs"]["test."+name]["value"], value)
                self.assertTrue(report["tableSha256"])

    def test_transition_includes_confirmation_with_earlier_expiry(self):
        rec = record()
        setvalue(rec, "confirmation", 100_000_000)
        setvalue(rec, "retainedValidity", 100_000_000)
        result = rows(W.generate(admitted(rec)))
        self.assertIn("min(requestTimeNs", result["deadline.confirmation"]["runtimeObligation"])
        self.assertIn("do not add T+C", result["deadline.confirmation"]["rule"])
        for name in ("transitionScope", "confirmationScope"):
            rec = record()
            setvalue(rec, name, "TEST-ONLY-unsupported-phase")
            self.refused(rec, "TABLE-DEADLINE-SCOPE")

    def test_aged_retained_evidence_caps_all_applicable_relative_deadlines(self):
        # ALL timestamps/deadlines are TEST-ONLY; this is a counterexample to omitting absolute expiry.
        rec = record()
        for name, value in (("transition", 100), ("confirmation", 40), ("fallback", 100),
                            ("mrcRequest", 100), ("retainedValidity", 200)):
            setvalue(rec, name, value)
        result = rows(W.generate(admitted(rec)))
        relative = {"requestTimeNs + totalTransitionDeadlineNs": 150+100,
                    "selectorTimeNs + confirmationDeadlineNs": 170+40,
                    "lossDetectionTimeNs + fallbackDeadlineNs": 150+100,
                    "lossDetectionTimeNs + mrcRequestDeadlineNs": 150+100}
        expected = {"transition": ["requestTimeNs + totalTransitionDeadlineNs"],
                    "confirmation": ["requestTimeNs + totalTransitionDeadlineNs", "selectorTimeNs + confirmationDeadlineNs"],
                    "fallback": ["lossDetectionTimeNs + fallbackDeadlineNs"],
                    "mrcRequest": ["lossDetectionTimeNs + mrcRequestDeadlineNs"]}
        # Retained evidence originated before request/detection/selector. Use more than one expiry;
        # neither relative clock may replace the earlier authoritative expiry or restart its duration.
        evidence_expiries = [220, 200]
        completion = 205
        for name, relative_terms in expected.items():
            row = result["deadline."+name]
            self.assertIn("runtimeExpiryTerms", row)
            self.assertEqual(row["runtimeExpiryTerms"], relative_terms+["retainedEvidenceValidUntilNs[*]"])
            self.assertIn("every applicable", row["retainedEvidenceExpiryPolicy"])
            self.assertIn("never rebase or restart", row["retainedEvidenceExpiryPolicy"])
            self.assertIn("retainedEvidenceValidUntilNs[*]", row["runtimeObligation"])
            self.assertIn("test.retainedValidity", row["inputIds"])
            relative_expiry = min(relative[term] for term in relative_terms)
            complete_expiry = min(relative_expiry, *evidence_expiries)
            self.assertLessEqual(completion, relative_expiry)  # old, incomplete obligation admits it
            self.assertGreater(completion, complete_expiry)  # complete obligation refuses it
            self.assertEqual(complete_expiry, 200)
        self.assertIn("do not add T+C", result["deadline.confirmation"]["rule"])

    def test_comparison_units_separate_constant_distance_from_time_bound(self):
        finite = rows(W.generate(admitted(record())))["envelope.endToEnd"]
        self.assertEqual(finite["unit"], "ns")
        self.assertIn("unit", finite["check"])
        self.assertEqual(finite["check"]["unit"], "ns")
        for gap, expected_budget in ((100, 94), (1, -5)):
            rec = record()
            setvalue(rec, "maxClosingSpeed", 0)
            setvalue(rec, "worstGap", gap)
            report = W.generate(admitted(rec)) if gap == 100 else self.refused(rec, row="envelope.endToEnd")
            row = rows(report)["envelope.endToEnd"]
            self.assertEqual(row["unit"], "ns")
            self.assertIsNone(row["value"])
            self.assertIsNone(row["roundedUpperNs"])
            self.assertEqual(row["check"]["unit"], "m")
            self.assertEqual(row["check"]["relation"], ">=")
            self.assertEqual(rational(row["check"]["left"]), expected_budget)
            self.assertEqual(rational(row["check"]["right"]), 0)

    def test_unbounded_zero_speed_never_selects_an_infinite_or_default_deadline(self):
        rec = record()
        setvalue(rec, "maxClosingSpeed", 0)
        setvalue(rec, "windowmaxClosingSpeed", 0)
        setvalue(rec, "windowvalidity", 10**15)
        result = rows(W.generate(admitted(rec)))
        for name in ("envelope.endToEnd", "window.TEST-ONLY-camera.validity"):
            self.assertEqual(result[name]["boundKind"], "unbounded-by-this-model")
            self.assertIsNone(result[name]["roundedUpperNs"])
        self.assertEqual(result["envelope.endToEnd"]["declaredValueNs"], 8_000_000_000)
        setvalue(rec, "endToEnd", 0)
        self.refused(rec, "TABLE-NANOSECONDS")

    def test_negative_constant_budget_is_no_solution_at_both_speeds(self):
        for speed in (0, 10):
            rec = record()
            setvalue(rec, "maxClosingSpeed", speed)
            setvalue(rec, "worstGap", 1)
            result = self.refused(rec, row="envelope.endToEnd")
            self.assertEqual(rows(result)["envelope.endToEnd"]["boundKind"], "no-solution")

    def test_finite_zero_budget_refuses_positive_deadline(self):
        rec = record()
        setvalue(rec, "worstGap", 16)
        result = self.refused(rec, row="envelope.endToEnd")
        self.assertEqual(rows(result)["envelope.endToEnd"]["boundKind"], "zero-budget")
        self.assertEqual(rows(result)["envelope.endToEnd"]["roundedUpperNs"], 0)

    def test_every_consumed_identifier_is_required_without_default(self):
        for identifier in record()["entries"]:
            with self.subTest(identifier=identifier):
                rec = record()
                del rec["entries"][identifier]
                self.refused(rec, "TABLE-PROTOCOL")

    def test_wrong_units_status_and_forbidden_categories_are_refused(self):
        for identifier in record()["entries"]:
            with self.subTest(identifier=identifier):
                for field, value, code in (("unit", "TEST-ONLY-wrong", "TABLE-UNIT"),
                                            ("status", "unresolved", "TABLE-PROTOCOL"),
                                            ("category", "oracle", "TABLE-CATEGORY")):
                    rec = record()
                    rec["entries"][identifier][field] = value
                    self.refused(rec, code)
        for category in ("fault", "metric"):
            rec = record()
            rec["entries"]["test.margin"]["category"] = category
            self.refused(rec, "TABLE-CATEGORY")

    def test_input_numeric_types_and_domains_are_strict(self):
        for name, values, code in (("margin", (True, "5", None, []), "TABLE-NUMBER"),
                                  ("deceleration", (0, -1), "TABLE-RANGE"),
                                  ("margin", (-1,), "TABLE-RANGE"),
                                  ("reserveFraction", (-0.1, 1.01), "TABLE-RANGE"),
                                  ("windowmarginFraction", (-0.1, 1.01), "TABLE-RANGE"),
                                  ("endToEnd", (True, 1.0, "1", 0, -1), "TABLE-NANOSECONDS"),
                                  ("windowperiod", (0,), "TABLE-NANOSECONDS"),
                                  ("windowlatency", (-1,), "TABLE-NANOSECONDS")):
            for value in values:
                with self.subTest(name=name, value=value):
                    rec = record()
                    setvalue(rec, name, value)
                    self.refused(rec, code)
        for name in ("decisionCycle", "monitor", "transition", "confirmation", "fallback", "mrcRequest", "retainedValidity"):
            rec = record()
            setvalue(rec, name, 0)
            self.refused(rec, "TABLE-NANOSECONDS")

    def test_bad_binding_maps_and_identities_are_refused(self):
        for mutation in (lambda b: b.update(schema="TEST-ONLY-unknown"),
                         lambda b: b.update(extra=True), lambda b: b.update(windows=[]),
                         lambda b: b["windows"].append(copy.deepcopy(b["windows"][0])),
                         lambda b: b["windows"][0].update(itemId="")):
            rec = record()
            mutation(rec["entries"][W.BINDINGS_ID]["value"])
            self.refused(rec, "TABLE-BINDINGS")
        rec = record()
        rec["entries"][W.BINDINGS_ID]["value"]["envelope"]["margin"] = "not-an-id"
        self.refused(rec, "TABLE-IDENTIFIER")
        rec = record()
        rec["entries"][W.BINDINGS_ID]["category"] = "runtime"
        self.refused(rec, "TABLE-CATEGORY")

    def test_path_requires_continuity_full_route_and_unique_stages(self):
        for mutation in (lambda p: p.pop(), lambda p: p[0].update(to=W.ROUTE[2]),
                         lambda p: p[1].update(stageId=p[0]["stageId"]),
                         lambda p: p[1].update(**{"from": W.ROUTE[0]})):
            rec = record()
            mutation(rec["entries"][W.BINDINGS_ID]["value"]["path"])
            self.refused(rec, "TABLE-PATH")
        rec = record()
        path = rec["entries"][W.BINDINGS_ID]["value"]["path"]
        path.insert(0, {"stageId": "TEST-ONLY-compute", "from": W.ROUTE[0], "to": W.ROUTE[0], "latency": "test.stage0"})
        self.assertTrue(W.generate(admitted(rec))["valid"])

    def test_speed_uncertainty_is_envelope_only_not_double_applied_to_odd(self):
        rec = record()
        setvalue(rec, "speedUncertainty", 1)
        setvalue(rec, "endToEnd", 7_000_000_000)
        result = rows(W.generate(admitted(rec)))
        self.assertEqual(rational(result["envelope.conservativeSpeed"]["value"]), 11)
        self.assertEqual(result["window.TEST-ONLY-camera.validity"]["roundedUpperNs"], 250_000_000)

    def test_generator_and_protocol_are_not_imported_by_runtime_inventory(self):
        # These are all current runtime modules on this dependency candidate; offline tooling is excluded by role.
        package = Path(W.__file__).parent
        for source in package.glob("*.py"):
            if source.name in ("window_tables.py", "protocol.py", "protocol_audit.py"):
                continue
            for node in ast.walk(ast.parse(source.read_text())):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn(node.module, ("window_tables", "protocol", "assured_aeb.window_tables", "assured_aeb.protocol"), source.name)
                if isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name in ("assured_aeb.window_tables", "assured_aeb.protocol") for alias in node.names), source.name)

    def test_requires_admitted_protocol(self):
        with self.assertRaises(W.TableRefused) as caught:
            W.generate({})
        self.assertEqual(caught.exception.code, "TABLE-PROTOCOL")
