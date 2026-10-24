"""Accepted WP-15 DN-1 source successor; all numeric fixtures are TEST-ONLY.

No MRC execution, availability classification, simulation or protocol value is supplied here.
"""
from __future__ import annotations

import math

import pytest

from assured_aeb import brake_esc as B
from assured_aeb import vc_functional as V
from test_aeb_logic import MS, WORLD, adas, fallback, projection, selector


@pytest.mark.parametrize("source,configuration,make", [("adas-cycle", "C_NOMINAL", adas),
                                                      ("fallback-request", "C_DEGRADED_RADAR", fallback)])
@pytest.mark.parametrize("raw,expected", [(0.0, 0.0), (0.6, 0.6), (1.4, 1.0), (-0.2, 0.0)])
def test_terminal_holds_the_actual_clamped_emission_from_either_operational_source(source, configuration, make,
                                                                                  raw, expected):
    arbiter = V.FunctionalArbiter(projection())
    initial = arbiter.step(WORLD, [("selector-command", selector(1, configuration)), (source, make(1, WORLD, raw))])
    assert initial["value"] == expected
    assert arbiter.evidence[-1]["terminalHoldProvenance"] is None
    for cycle, offset in enumerate((MS, 10_000 * MS, 1_000_000 * MS), 1):
        now = WORLD + offset
        inbox = [("adas-cycle", adas(10 + cycle, now, 1.0 - expected)),
                 ("fallback-request", fallback(10 + cycle, now, 1.0 - expected))]
        if cycle == 1:
            inbox.insert(0, ("selector-command", selector(2, "S_MRC_REQUESTED", now)))
        request = arbiter.step(now, inbox)
        evidence = arbiter.evidence[-1]
        assert request["value"] == expected
        assert request["sequence"] == cycle + 1 and request["originNs"] == now
        assert set(request) == B.ARBITER_REQUEST_MEMBERS
        assert evidence["kind"] == "terminal-entry-value-hold" and evidence["value"] == expected
        assert evidence["terminalHoldProvenance"] == "last-emitted-request"
        assert evidence["selectedInterface"] is evidence["sourceSequence"] is evidence["sourceOriginNs"] is None
        assert evidence["forwardedState"] is evidence["forwardedReason"] is evidence["rawValue"] is None
        assert not evidence["clamped"]
    # The held value still crosses the unchanged real WP-04 chassis/node contracts.
    routed = B.ChassisZone().step(now, [("brake-request", request)])
    node = B.BrakeEscNode(B.BrakeNodeParams.from_record({"schema": B.NODE_PARAMS, "stalenessWindowNs": 80 * MS,
                                                       "computeLatencyNs": 0}))
    assert "accepted" in [event["status"] for event in node.step(now, [message for _, message in routed])["status"]]


def test_terminal_snapshots_zero_after_source_hold_expiry_instead_of_the_older_positive_cache():
    arbiter = V.FunctionalArbiter(projection())
    arbiter.step(WORLD, [("selector-command", selector(1, "C_NOMINAL")), ("adas-cycle", adas(1, WORLD, 0.8))])
    assert arbiter.step(WORLD + 101 * MS, [])["value"] == 0.0
    assert arbiter.evidence[-1]["kind"] == "no-valid-source"
    assert arbiter.step(WORLD + 102 * MS, [("selector-command", selector(2, "S_MRC_REQUESTED")),
                                          ("adas-cycle", adas(2, WORLD + 102 * MS, 1.0))])["value"] == 0.0
    assert arbiter.evidence[-1]["terminalHoldProvenance"] == "last-emitted-request"
    assert arbiter.step(WORLD + 1_000_000 * MS, [])["value"] == 0.0


@pytest.mark.parametrize("live_first", [False, True])
def test_empty_history_is_explicit_neutral_and_same_inbox_live_order_cannot_supply_a_snapshot(live_first):
    arbiter = V.FunctionalArbiter(projection())
    terminal = ("selector-command", selector(1, "S_MRC_REQUESTED"))
    live = ("adas-cycle", adas(1, WORLD, 1.0))
    request = arbiter.step(WORLD, [live, terminal] if live_first else [terminal, live])
    assert request["value"] == 0.0 and arbiter.evidence[-1]["terminalHoldProvenance"] == "initial-neutral-no-prior-emission"
    assert arbiter.step(WORLD + MS, [])["value"] == 0.0
    assert arbiter.evidence[-1]["terminalHoldProvenance"] == "initial-neutral-no-prior-emission"


def test_emitted_no_selector_zero_is_actual_history_rather_than_empty_initialization():
    arbiter = V.FunctionalArbiter(projection())
    arbiter.step(WORLD, [])
    arbiter.step(WORLD + MS, [("selector-command", selector(1, "S_MRC_REQUESTED"))])
    assert arbiter.evidence[-1]["terminalHoldProvenance"] == "last-emitted-request"


def test_terminal_snapshot_is_independent_of_mutable_source_cache_and_returned_request():
    arbiter = V.FunctionalArbiter(projection())
    source = adas(1, WORLD, 0.4)
    emitted = arbiter.step(WORLD, [("selector-command", selector(1, "C_NOMINAL")), ("adas-cycle", source)])
    source["brakeRequest"], emitted["value"] = 0.9, 0.8
    assert arbiter.step(WORLD + MS, [("selector-command", selector(2, "S_MRC_REQUESTED"))])["value"] == 0.4
    source["brakeRequest"] = math.nan
    assert arbiter.step(WORLD + 1000 * MS, [("adas-cycle", source), ("fallback-request", {})])["value"] == 0.4


@pytest.mark.parametrize("recovery", ["C_NOMINAL", "C_DEGRADED_RADAR"])
def test_terminal_lockout_refuses_recovery_in_entry_inbox_and_later_and_duplicate_entry_is_idempotent(recovery):
    arbiter = V.FunctionalArbiter(projection())
    arbiter.step(WORLD, [("selector-command", selector(1, "C_NOMINAL")), ("adas-cycle", adas(1, WORLD, 0.7))])
    request = arbiter.step(WORLD + MS, [("selector-command", selector(2, "S_MRC_REQUESTED")),
                                       ("selector-command", selector(3, recovery))])
    assert request["value"] == 0.7 and arbiter.evidence[-1]["refusals"] == ["selector-terminal-lockout"]
    for offset, message, refusal in ((2, selector(4, "S_MRC_REQUESTED"), "selector-terminal-already-entered"),
                                      (3, selector(5, recovery), "selector-terminal-lockout"),
                                      (4, selector(2, "S_MRC_REQUESTED"), "selector-replayed"),
                                      (5, selector(6, recovery, source="proposer"), "selector-wrong-source")):
        request = arbiter.step(WORLD + offset * MS, [("selector-command", message)])
        assert request["value"] == 0.7
        assert arbiter.evidence[-1]["refusals"] == [refusal]
        assert arbiter.configuration == "S_MRC_REQUESTED" and arbiter.selector_sequence == 2
        assert arbiter.evidence[-1]["terminalHoldProvenance"] == "last-emitted-request"


@pytest.mark.parametrize("old_value", ["adas-cycle", "fallback-request", "none", "unknown"])
def test_obsolete_live_terminal_projection_is_refused_instead_of_ignored(old_value):
    assert "arbiter.mrcSource" not in V.ARBITER_DECLARATION
    with pytest.raises(ValueError, match="arbiter.mrcSource: obsolete"):
        V.FunctionalArbiter(projection(arbiter__mrcSource=old_value))
