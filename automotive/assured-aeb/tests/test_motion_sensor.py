"""Offline tests of the WP-05 modelled motion sensor (no run, no CARLA).

Every parameter value below is a TEST VALUE for these tests only; the model values are TODO (AD-27; class J).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from assured_aeb import motion_sensor as M
import topology as T

HERE = Path(__file__).resolve().parents[1]
MS = 1_000_000
TEST_RECORD = {"schema": M.PARAMS, "samplingPeriodNs": 50 * MS, "speedQuantumMps": 0.01, "accelQuantumMps2": 0.01,
               "noiseModel": "gaussian-additive", "speedNoiseStdMps": 0.1, "accelNoiseStdMps2": 0.2, "seed": 7,
               "latencyNs": 20 * MS}  # test values


def sensor(origin_ns=0, **changes):
    s = M.MotionSensor(M.MotionSensorParams.from_record(dict(TEST_RECORD, **changes)))
    if origin_ns is not None:
        s.bind_origin(origin_ns)
    return s


def item(origin_ns, speed=10.0, accel=-1.0):
    return {"flowId": "vehicle-motion", "originNs": origin_ns, "value": {"speedMps": speed, "accelForwardMps2": accel}}


def run(s, origins, speed=10.0):
    return [s.step(item(o, speed)) for o in origins]


# ---- parameters ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("change", [
    {"samplingPeriodNs": 0}, {"samplingPeriodNs": 1.5}, {"speedQuantumMps": 0}, {"accelQuantumMps2": -1},
    {"noiseModel": "uniform"}, {"speedNoiseStdMps": -0.1}, {"accelNoiseStdMps2": float("nan")}, {"seed": -1},
    {"seed": 1.0}, {"latencyNs": -1}, {"schema": "other"},
])
def test_out_of_domain_parameters_are_refused(change):
    with pytest.raises(ValueError):
        M.MotionSensorParams.from_record(dict(TEST_RECORD, **change))


@pytest.mark.parametrize("member", sorted(M.PARAM_MEMBERS))
def test_every_member_is_required(member):
    with pytest.raises(ValueError):
        M.MotionSensorParams.from_record({k: v for k, v in TEST_RECORD.items() if k != member})


def test_extra_member_and_missing_record_are_refused():
    with pytest.raises(ValueError):
        M.MotionSensorParams.from_record(dict(TEST_RECORD, extra=1))
    with pytest.raises(TypeError):
        M.MotionSensor(None)


# ---- sampling ------------------------------------------------------------------------------------------------

def test_one_sample_per_slot_on_the_simulation_time_grid():
    outputs = run(sensor(), [0, 10 * MS, 49 * MS, 50 * MS, 120 * MS])
    assert [o["slot"] if o else None for o in outputs] == [0, None, None, 1, 2]
    assert [o["sequence"] for o in outputs if o] == [1, 2, 3]


def test_no_sample_is_invented_between_frames_and_a_stalled_input_yields_nothing():
    s = sensor()
    assert s.step(item(100 * MS)) is not None
    assert s.step(item(100 * MS)) is None and s.refused["not-advancing"] == 1
    assert s.step(item(90 * MS)) is None and s.refused["not-advancing"] == 2
    gap = s.step(item(400 * MS))  # frames 150-350 ms missing: one sample for the next frame, none invented
    assert gap["slot"] == 8 and gap["sequence"] == 2


def test_latency_stamp():
    out = sensor().step(item(100 * MS))
    assert out["originNs"] == 100 * MS and out["deliverAtNs"] == 120 * MS


# ---- model ---------------------------------------------------------------------------------------------------

def test_without_noise_the_output_is_the_quantised_input():
    out = sensor(speedNoiseStdMps=0.0, accelNoiseStdMps2=0.0, speedQuantumMps=0.5, accelQuantumMps2=0.25).step(item(0, 10.3, -1.1))
    assert out["speedMps"] == 10.5 and out["accelForwardMps2"] == -1.0


def test_values_differ_from_the_input_by_the_declared_model():  # V14
    outs = [o for o in run(sensor(), [k * 50 * MS for k in range(200)]) if o]
    errors = [o["speedMps"] - 10.0 for o in outs]
    assert any(abs(e) > 0.005 for e in errors)
    mean = sum(errors) / len(errors)
    std = (sum((e - mean) ** 2 for e in errors) / (len(errors) - 1)) ** 0.5
    assert abs(mean) < 0.05 and 0.07 < std < 0.13  # test std 0.1 plus quantum 0.01; loose statistical bounds
    assert all(o["speedMps"] == round(o["speedMps"], 2) for o in outs)  # on the quantum grid, no float artefact


def test_negative_noisy_speed_is_clamped_to_zero():
    outs = [o for o in run(sensor(speedNoiseStdMps=1.0), [k * 50 * MS for k in range(100)], speed=0.0) if o]
    assert all(o["speedMps"] >= 0.0 for o in outs) and any(o["speedMps"] == 0.0 for o in outs)


# ---- determinism ---------------------------------------------------------------------------------------------

def test_same_seed_same_stream_and_different_seed_differs():
    origins = [k * 50 * MS for k in range(50)]
    a, b, c = run(sensor(), origins), run(sensor(), origins), run(sensor(seed=8), origins)
    assert a == b
    assert [o["speedMps"] for o in a] != [o["speedMps"] for o in c]


def test_noise_is_keyed_by_simulation_time_slot_not_by_history():
    full = {o["slot"]: o["speedMps"] for o in run(sensor(), [k * 50 * MS for k in range(20)])}
    sparse = {o["slot"]: o["speedMps"] for o in run(sensor(), [k * 50 * MS for k in (0, 7, 13, 19)])}
    assert all(full[slot] == value for slot, value in sparse.items())


def test_paired_arms_see_identical_evidence_up_to_the_divergent_input():  # PAIR-1
    common = [item(k * 50 * MS, 10.0 - 0.1 * k) for k in range(10)]
    arm_a, arm_b = sensor(), sensor()
    out_a = [arm_a.step(i) for i in common] + [arm_a.step(item(500 * MS, 8.0))]
    out_b = [arm_b.step(i) for i in common] + [arm_b.step(item(500 * MS, 9.0))]
    assert out_a[:10] == out_b[:10] and out_a[10] != out_b[10]


# ---- output vocabulary ---------------------------------------------------------------------------------------

def test_output_is_in_the_closed_vocabulary_and_carries_no_true_value():
    out = sensor().step(item(0, 12.345678, -0.5))
    assert M.check_output(out) == []
    assert "value" not in out and "trueSpeedMps" not in out and "noise" not in out
    assert M.check_output(dict(out, trueSpeedMps=12.3)) and M.check_output(dict(out, source="carla-client"))


# ---- separation (V14; FR-021; DYN-002) -------------------------------------------------------------------------

@pytest.mark.parametrize("content, reason", [
    ({"header": True, "evaluationOnly": True, "role": "xverse-lite-ego"}, "evaluation-content"),
    ({"schema": "xverse-compat.evaluation-observer/2", "frame": 10, "simElapsedNs": 500, "roles": {}}, "evaluation-content"),
    ({"flowId": "radar-adas", "originNs": 0, "value": {}}, "other-flow"),
    ({"flowId": "vehicle-motion", "originNs": 0, "value": {"speedMps": -1, "accelForwardMps2": 0}}, "malformed"),
    ("frame 10", "not-an-item"),
])
def test_sensor_refuses_observer_output_and_other_inputs(content, reason):
    s = sensor()
    assert s.step(content) is None and s.refused == {reason: 1}


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(("." * node.level) + (node.module or ""))
    return names


def test_sensor_module_imports_no_observer_evaluation_or_oracle_code():
    imports = _imports(HERE / "assured_aeb" / "motion_sensor.py")
    assert imports <= {"__future__", "dataclasses", "decimal", "hashlib", "json", "math", "random", "typing"}


def test_no_oracle_or_evaluation_module_reads_the_sensor():
    for path in HERE.rglob("*.py"):
        if any(word in path.name for word in ("oracle", "evaluation", "observer", "metric")):
            assert not any("motion_sensor" in name for name in _imports(path)), path


def test_topology_carries_motion_evidence_only_to_runtime_and_keeps_the_observer_outside():
    for arm in T.ARMS:
        consumers = {v[2] for v in T.flows_of(arm).values() if v[0] == "motion-sensor-model"}
        assert consumers == {"chassis-zone"}
        assert T.FLOWS["f10-motion-chassis"][3:5] == ("net-u5", "sensor-sampling")
        assert "f10-motion-chassis" not in T.RELAY_ADMITTED  # no fault hook on F10 (§K)
        assert not any("observer" in e or "oracle" in e for e in T.elements_of(arm))
    assert T.ELEMENTS["motion-sensor-model"][1] == "vehicle-loop"  # §J: the U2 sensor-model stage


def test_driver_uses_the_adapter_item_not_the_sensor():  # E-5
    intra = {(p, i, c) for p, i, c, _ in T.INTRA}
    assert ("loop-gateway", "motion-raw", "driver-profile") in intra
    assert not any(p == "motion-sensor-model" and c == "driver-profile" for p, _, c in intra)
    out = sensor().step(item(0))
    assert "flowId" not in out  # WP-03 _motion accepts only flowId == "vehicle-motion"


# ---- finding 4 repairs ---------------------------------------------------------------------------------------

WORLD_A, WORLD_B = 1_000 * 1_000 * MS, 1_600 * 1_000 * MS + 30 * MS  # two world epochs, 30 ms out of phase (test values)


def test_pair1_with_two_different_world_epochs():  # HIGH-1: failed on 329eaf4
    trajectory = [(k * 50 * MS, 10.0 - 0.05 * k) for k in range(12)]
    a, b = sensor(origin_ns=WORLD_A, samplingPeriodNs=100 * MS), sensor(origin_ns=WORLD_B, samplingPeriodNs=100 * MS)
    out_a = [a.step(item(WORLD_A + t, v)) for t, v in trajectory]
    out_b = [b.step(item(WORLD_B + t, v)) for t, v in trajectory]
    strip = lambda o: None if o is None else {k: v for k, v in o.items() if k not in ("originNs", "deliverAtNs")}
    assert [strip(o) for o in out_a] == [strip(o) for o in out_b]  # same frames sampled, same noise, same values
    assert [o["originNs"] - WORLD_A for o in out_a if o] == [o["originNs"] - WORLD_B for o in out_b if o]
    assert [o for o in out_a if o][0]["originNs"] == WORLD_A  # absolute stamps kept


def test_no_sample_before_the_origin_is_bound_and_the_origin_binds_once():
    s = sensor(origin_ns=None)
    assert s.step(item(WORLD_A)) is None and s.refused == {"origin-unbound": 1}
    for bad in (None, 1.5, -1, True):
        with pytest.raises(ValueError):
            s.bind_origin(bad)
    s.bind_origin(WORLD_A)
    s.bind_origin(WORLD_A)
    with pytest.raises(ValueError):
        s.bind_origin(WORLD_A + 1)
    assert s.step(item(WORLD_A))["slot"] == 0
    assert s.step(item(WORLD_A - 1)) is None and s.refused["before-episode"] == 1


def test_sample_is_the_first_frame_in_each_slot():  # LOW-2 wording
    s = sensor(samplingPeriodNs=100 * MS)
    out = [s.step(item(t, v)) for t, v in ((0, 10.0), (50 * MS, 11.0), (100 * MS, 12.0), (150 * MS, 13.0))]
    assert [o["originNs"] if o else None for o in out] == [0, None, 100 * MS, None]


def test_box_muller_transform_is_the_declared_one():  # LOW-1
    import hashlib, math, random
    key = hashlib.sha256(f"{M.PARAMS}|7|3|speed".encode()).digest()
    rng = random.Random(int.from_bytes(key[:8], "big"))
    u1, u2 = 1.0 - rng.random(), rng.random()
    assert M.noise(7, 3, "speed", 0.5) == 0.5 * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    tree = ast.parse((HERE / "assured_aeb" / "motion_sensor.py").read_text())
    assert not any(isinstance(n, ast.Attribute) and n.attr in ("gauss", "normalvariate") for n in ast.walk(tree))


@pytest.mark.parametrize("value, quantum, expected", [(9.95, 0.01, 9.95), (9.9501, 0.05, 9.95), (10.3, 0.5, 10.5),
                                                       (-1.1, 0.25, -1.0), (0.123456, 0.001, 0.123)])
def test_quantisation_has_no_float_artefacts(value, quantum, expected):  # LOW-2
    assert M.quantise(value, quantum) == expected and repr(M.quantise(value, quantum)) == repr(expected)
