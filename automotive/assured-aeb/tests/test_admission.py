"""Offline tests of the WP-10 increment #1 admission path (no run, no CARLA).

Every bound value below is a TEST VALUE: the D-4c measurements (max_step_host_s, handshake_s) are unknown, the step
(K-10) and the thaw bound come from the caller. None is a protocol value.
"""

from __future__ import annotations

import math
import types

import pytest

import admission as A
import check_topology as C

MS = 1_000_000
TEST_FREEZE = C.FreezeBound(thaw_bound_s=3.26, max_cycle_s=0.1)  # test values (the thaw bound as in the WP-11 dry run)
KNOWN = A.SimTimeFreezeBound(thaw_bound_s=3.26, step_s=0.05, max_step_host_s=0.1, handshake_s=0.2)  # test values
UNKNOWN = A.SimTimeFreezeBound(thaw_bound_s=3.26, step_s=0.05, max_step_host_s=None, handshake_s=None)  # D-4c unknown
WITH_A = types.SimpleNamespace(SIMULATION_TIME_TRIGGERS=True)  # stands in for a platform that provides option (A)


def sim_freeze(fault_id, unit, onset_ms=1_000, duration_ms=500):
    return C.fault("mloc", fault_id, "freeze", unit, onset_ms, duration_ms, unit="ms", domain="carla-simulation")


def _sim(fault, duration_ms):
    fault["extensions"]["io.xverse.experiment"]["duration"] = {"value": duration_ms, "unit": "ms"}
    return fault


def cc1(duration_ms=500):
    return [_sim(sim_freeze("a", "vc-functional-unit"), duration_ms), _sim(sim_freeze("b", "vc-assurance-unit"), duration_ms)]


class Spy:
    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return "called"


def run(faults, *, freeze_bound=TEST_FREEZE, sim_bound=KNOWN, platform=None, schema_paths=()):
    prepare, admit = Spy(), Spy()
    result = A.admit_run("mloc", faults, freeze_bound=freeze_bound, sim_bound=sim_bound, op=0.29, schema_paths=schema_paths,
                         platform=platform, prepare_fn=prepare, admit_fn=admit)
    return result, prepare, admit


# ---- order and stopping: admit_schedule is never reached after a refusal ------------------------------------

@pytest.mark.parametrize("case, kwargs, stage", [
    ("no FreezeBound", {"freeze_bound": None}, "bound-inputs"),
    ("no simulation-time bound", {"sim_bound": None}, "bound-inputs"),
    ("unknown D-4c values", {"sim_bound": UNKNOWN}, "sim-duration"),
    ("interim gate", {}, "fault-admission"),
])
def test_a_refusal_stops_before_prepare_and_admit(case, kwargs, stage):
    result, prepare, admit = run(cc1(), **kwargs)
    assert not result.admitted and result.stage == stage and result.stages_run[-1] == stage
    assert prepare.calls == 0 and admit.calls == 0
    assert "admit-schedule" not in result.stages_run


def test_rule_refusal_stops_before_the_interim_gate_and_admit():
    result, prepare, admit = run([_sim(sim_freeze("lone", "vc-functional-unit"), 500)], platform=WITH_A)
    assert result.stage == "fault-admission" and "every member" in result.refusals[0]
    assert prepare.calls == 0 and admit.calls == 0


def test_tick_keyed_freeze_is_refused_under_option_a():
    result, prepare, admit = run([C.fault("mloc", "t", "freeze", "adas-hpc-unit", 100, 10)], platform=WITH_A)
    assert result.stage == "sim-duration" and "simulation time" in result.refusals[0] and admit.calls == 0


def test_long_duration_breaks_the_inequality():
    # 500 ms -> 10 steps x 0.1 s + 2 x 0.2 s = 1.4 s <= 3.26 s; 1500 ms -> 30 x 0.1 + 0.4 = 3.4 s > 3.26 s
    assert run(cc1(500), platform=WITH_A)[0].admitted
    result, _, admit = run(cc1(1_500), platform=WITH_A)
    assert result.stage == "sim-duration" and "above the thaw bound" in result.refusals[0] and admit.calls == 0


def test_valid_schedule_passes_every_stage_only_with_option_a():
    result, prepare, admit = run(cc1(), platform=WITH_A)
    assert result.admitted and result.stages_run == list(A.STAGES) and prepare.calls == 1 and admit.calls == 1


# ---- the interim position --------------------------------------------------------------------------------------

def test_rc1_platform_does_not_provide_option_a():
    assert A.option_a_available() is False
    assert A.option_a_available(types.SimpleNamespace(SIMULATION_TIME_TRIGGERS="yes")) is False


@pytest.mark.parametrize("faults", [
    cc1(),
    [_sim(sim_freeze("f", "front-zone-unit"), 500)],
    [_sim(sim_freeze("h", "adas-hpc-unit"), 500)],
    [_sim(sim_freeze("g", "vc-assurance-unit"), 500)],
    [C.fault("mloc", "s", "stale", "f09-radar-vc", 100, 10)],
    [C.fault("mloc", "l", "loss", "f09-radar-vc", 100, 10, parameters=C.EVERY_ONE)],
    [C.fault("mloc", "u", "assurance.proposal-unsafe", "f12-proposal", 100, 10)],
    [C.fault("mloc", "e", "assurance.evidence-loss", "f13-qualified-evidence", 100, 10)],
])
def test_every_fault_admission_refuses_until_option_a_exists(faults):
    result, prepare, admit = run(faults)  # the real rc.1 capability probe
    assert not result.admitted and admit.calls == 0 and prepare.calls == 0
    assert result.refusals == [A.INTERIM]


def test_fault_free_arm_is_admitted_on_rc1(schema_paths):
    result = A.admit_run("mloc", [], freeze_bound=None, sim_bound=None, op=0.29, schema_paths=schema_paths)
    assert result.admitted and result.stages_run == ["generate", "prepare", "admit-schedule"]
    assert math.isclose(C.LIVE["cadence"] - result.schedule.health_scan_seconds, 3.26)  # the thaw bound the caller derives


# ---- FreezeBound input validation (LOW-B) ----------------------------------------------------------------------

@pytest.mark.parametrize("thaw, cycle", [(0, 0.1), (-1, 0.1), (float("nan"), 0.1), (float("inf"), 0.1), (3.26, 0), (3.26, True)])
def test_freeze_bound_refuses_invalid_inputs(thaw, cycle):
    with pytest.raises(ValueError):
        C.FreezeBound(thaw_bound_s=thaw, max_cycle_s=cycle)


def test_sim_bound_reports_each_unknown_input():
    assert len(UNKNOWN.problems()) == 2 and KNOWN.problems() == []
    assert len(A.SimTimeFreezeBound(None, 0.0, float("nan"), True).problems()) == 4


def test_sim_duration_units():
    assert A.sim_duration_ns(_sim(sim_freeze("a", "adas-hpc-unit"), 500)) == 500 * MS
    assert A.sim_duration_ns(C.fault("mloc", "t", "freeze", "adas-hpc-unit", 100, 10)) is None  # tick-keyed


# ---- the hub re-check at arming (increment #4 stub) ---------------------------------------------------------

def test_hub_recheck_and_arm_stub():
    hub = A.HubArmingRecheck(C.load("mloc", "topology"))
    ok = A.ArmDescriptor("s", "f09-radar-vc", "stale", 1_000 * MS, 100 * MS)
    assert hub.recheck(ok) == []
    assert hub.recheck(A.ArmDescriptor("x", "f07-camera-adas", "loss", 0, 1))
    assert hub.recheck(A.ArmDescriptor("y", "carla-adapter-unit", "freeze", 0, 1))
    assert hub.recheck(A.ArmDescriptor("z", "vc-functional-unit", "freeze", 0, 1)) == []  # set membership; pairing is admission's
    with pytest.raises(NotImplementedError, match="increment #4"):
        hub.arm(ok)
