"""Offline tests of the U2 camera corruption stage and the U3 smart camera (no CARLA, no run).

Every format, schedule, statistics and threshold value below is a TEST VALUE; the protocol values are TODO (AD-02,
AD-31 severities after characterisation, D-2/D-3 thresholds) and have no default.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random

import pytest

from assured_aeb import camera_chain as C

MS = 1_000_000
WIDTH, HEIGHT = 32, 24  # test frame
FMT = {"schema": C.FRAME_FORMAT, "width": WIDTH, "height": HEIGHT, "encoding": "bgra8"}
WORLD = 1_000_000 * MS  # world clock at 1000 s (test value)


def textured(seed=1):
    rng = random.Random(seed)
    out = bytearray()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            base = 128 + (40 if (x // 2 + y // 2) % 2 else -40)
            out += bytes([max(0, min(255, base + rng.randint(-10, 10))) for _ in range(3)]) + b"\xff"
    return bytes(out)


def item(sequence, origin_ns, pixels, frame=None):
    return {"type": "item", "flowId": "camera", "sequence": sequence, "originNs": origin_ns,
            "frame": sequence if frame is None else frame,
            "value": {"width": WIDTH, "height": HEIGHT, "fovDeg": 90.0, "rawSha256": hashlib.sha256(pixels).hexdigest(),
                      "rawLength": len(pixels)}}


def schedule(events, seed=7):
    return C.CorruptionSchedule.from_record({"schema": C.CORRUPTION, "seed": seed, "frameFormat": dict(FMT), "events": events})


def stage(events, seed=7, origin=WORLD):
    s = C.CorruptionStage(schedule(events, seed))
    if origin is not None:
        s.bind_origin(origin)
    return s


def event(id_, kind, start_ms, end_ms, **params):
    return {"id": id_, "kind": kind, "startNs": start_ms * MS, "endNs": end_ms * MS, "params": params}


CAMERA_RECORD = {"schema": C.CAMERA_CHECKS, "frameFormat": dict(FMT),
                 "stats": {"statsStride": 1, "darkLevel": 16, "brightLevel": 239, "sharpnessBoxLog2": 1},
                 "thresholds": {"minMeanLuma": 60.0, "maxMeanLuma": 200.0, "minStdLuma": 20.0, "maxStdLuma": 45.0,
                                "maxDarkFraction": 0.2, "maxBrightFraction": 0.2, "minHighFrequencyVariance": 100.0,
                                "maxHighFrequencyVariance": 1600.0}}  # test values


def camera():
    return C.SmartCamera(C.SmartCameraParams.from_record(copy.deepcopy(CAMERA_RECORD)))


# ---- records: no defaults ------------------------------------------------------------------------------------

@pytest.mark.parametrize("mutate", [
    lambda r: r.pop("seed"), lambda r: r.update(seed=-1), lambda r: r.update(frameFormat={**FMT, "encoding": "rgb8"}),
    lambda r: r.update(events={}), lambda r: r["events"].append(event("b", "fog", 0, 1)),
    lambda r: r["events"].append(event("a", "blur", 0, 1, boxLog2=2)),  # duplicate id
    lambda r: r["events"].append(event("c", "blur", 5, 5, boxLog2=2)),  # empty interval
    lambda r: r["events"].append(event("d", "blur", 0, 1, boxLog2=9)),
    lambda r: r["events"].append(event("d2", "blur", 0, 1, boxLog2=5)),  # above the tool limit
    lambda r: r["events"].append(event("e", "noise", 0, 1, stdLevel=0)),
    lambda r: r["events"].append(event("f", "exposure", 0, 1, gain=0, offset=0)),
    lambda r: r["events"].append(event("g", "occlusion", 0, 1, x=30, y=0, width=5, height=1, value=0)),  # outside
    lambda r: r["events"].append(event("h", "dropout", 0, 1, extra=1)),
    lambda r: r["events"].append(event("i", "noise", 0, 1)),  # missing param
])
def test_corruption_record_is_refused(mutate):
    record = {"schema": C.CORRUPTION, "seed": 7, "frameFormat": dict(FMT), "events": [event("a", "blur", 0, 1, boxLog2=2)]}
    mutate(record)
    with pytest.raises(ValueError):
        C.CorruptionSchedule.from_record(record)


@pytest.mark.parametrize("path, value", [(("stats", "statsStride"), 0), (("stats", "darkLevel"), 250),
                                         (("stats", "sharpnessBoxLog2"), 5), (("thresholds", "minStdLuma"), float("nan")),
                                         (("thresholds", "maxDarkFraction"), 1.5)])
def test_camera_checks_record_is_refused(path, value):
    record = copy.deepcopy(CAMERA_RECORD)
    record[path[0]][path[1]] = value
    with pytest.raises(ValueError):
        C.SmartCameraParams.from_record(record)
    record = copy.deepcopy(CAMERA_RECORD)
    del record[path[0]][path[1]]
    with pytest.raises(ValueError):
        C.SmartCameraParams.from_record(record)


def test_constructors_require_validated_records():
    with pytest.raises(TypeError):
        C.CorruptionStage(None)
    with pytest.raises(TypeError):
        C.SmartCamera(None)


# ---- corruption stage ----------------------------------------------------------------------------------------

def test_no_frame_before_the_origin_is_bound_and_binding_is_once():
    s, px = stage([], origin=None), textured()
    assert s.process(item(0, WORLD, px), px) == (None, None) and s.refused == {"origin-unbound": 1}
    s.bind_origin(WORLD)
    s.bind_origin(WORLD)
    with pytest.raises(ValueError):
        s.bind_origin(WORLD + 1)
    out, delivered = s.process(item(0, WORLD, px), px)
    assert delivered == px and out["frameSha256"] == hashlib.sha256(px).hexdigest()


def test_schedule_is_keyed_to_episode_relative_time():
    px = textured()
    s = stage([event("dark", "exposure", 100, 200, gain=0.5, offset=0)])
    outputs = [s.process(item(k, WORLD + k * 50 * MS, px), px)[1] for k in range(6)]
    changed = [o != px for o in outputs]
    assert changed == [False, False, True, True, False, False]  # active for 100 <= t < 200 ms of the episode


def test_two_world_epochs_give_identical_delivered_frames():  # PAIR-1 for the corruption
    px, events = textured(), [event("n", "noise", 0, 1000, stdLevel=12.0), event("b", "blur", 100, 300, boxLog2=1)]
    a, b = stage(events, origin=WORLD), stage(events, origin=WORLD + 600_000 * MS + 30 * MS)
    for k in range(8):
        da = a.process(item(k, WORLD + k * 50 * MS, px), px)[1]
        db = b.process(item(k, WORLD + 600_000 * MS + 30 * MS + k * 50 * MS, px), px)[1]
        assert da == db


def test_noise_is_seeded_and_reproducible():
    px, events = textured(), [event("n", "noise", 0, 1000, stdLevel=12.0)]
    first = stage(events).process(item(0, WORLD, px), px)[1]
    again = stage(events).process(item(0, WORLD, px), px)[1]
    other_seed = stage(events, seed=8).process(item(0, WORLD, px), px)[1]
    assert first == again and first != other_seed and first != px


def test_dropout_delivers_nothing_and_the_smart_camera_sees_a_gap():
    px = textured()
    s, cam = stage([event("drop", "dropout", 50, 100)]), camera()
    seen = []
    for k in range(3):
        out, delivered = s.process(item(k, WORLD + k * 50 * MS, px), px)
        if out is not None:
            seen.append(cam.step(out["originNs"] + 10 * MS, out, delivered))
    assert len(seen) == 2 and seen[1]["indicators"]["sequenceGap"] == 1
    assert "sequence-gap" in seen[1]["checks"]["logical"]["failed"]


def test_f05_item_carries_no_schedule_information_and_evidence_no_pixels():  # FR-028; never pixels in evidence
    px = textured()
    s = stage([event("occ", "occlusion", 0, 1000, x=0, y=0, width=8, height=8, value=0)])
    out, delivered = s.process(item(0, WORLD, px), px)
    assert set(out) == C.SENSOR_OUT_MEMBERS
    text = json.dumps(out)
    for word in ("occ", "occlusion", "event", "seed", "corrupt", "rawSha256", hashlib.sha256(px).hexdigest()):
        assert word not in text
    assert out["frameSha256"] == hashlib.sha256(delivered).hexdigest() != hashlib.sha256(px).hexdigest()
    assert s.evidence == [{"kind": "corruption-applied", "frame": 0, "originNs": WORLD, "events": ["occ"], "kinds": ["occlusion"]}]
    assert all(not isinstance(v, (bytes, bytearray)) for record in s.evidence for v in record.values())


def test_stage_refuses_a_frame_whose_bytes_do_not_match_the_item():
    px = textured()
    s = stage([])
    assert s.process(item(0, WORLD, px), px[:-1] + b"\x00") == (None, None) and s.refused == {"digest-mismatch": 1}
    assert s.process({"flowId": "radar-adas"}, px) == (None, None)


# ---- smart camera sees the corruption -------------------------------------------------------------------------

def _check(events, k=0):
    px = textured()
    out, delivered = stage(events).process(item(k, WORLD + k * 50 * MS, px), px)
    return camera().step(out["originNs"] + 10 * MS, out, delivered)


def test_clean_frame_passes_every_class():
    result = _check([])
    assert {c: result["checks"][c]["verdict"] for c in ("logical", "plausibility", "statistical")} == \
           {"logical": "pass", "plausibility": "pass", "statistical": "pass"}
    assert "pixels" not in json.dumps(result) and all(not isinstance(v, bytes) for v in result["indicators"].values())


@pytest.mark.parametrize("events, failed", [  # each AD-31 kind against its check (finding 4, MEDIUM-3)
    ([event("b", "blur", 0, 1000, boxLog2=3)], "high-frequency-low"),
    ([event("x", "exposure", 0, 1000, gain=0.1, offset=0)], "mean-luma"),
    ([event("o", "occlusion", 0, 1000, x=0, y=0, width=32, height=12, value=0)], "dark-fraction"),
    ([event("x", "exposure", 0, 1000, gain=3.0, offset=60)], "bright-fraction"),
    ([event("n", "noise", 0, 1000, stdLevel=60.0)], "std-luma-high"),
    ([event("n", "noise", 0, 1000, stdLevel=60.0)], "high-frequency-high"),
])
def test_each_corruption_kind_trips_its_check(events, failed):
    assert failed in _check(events)["checks"]["statistical"]["failed"]


def test_noise_raises_the_luma_spread():
    clean, noisy = _check([]), _check([event("n", "noise", 0, 1000, stdLevel=60.0)])
    assert noisy["indicators"]["stdLuma"] > clean["indicators"]["stdLuma"]


@pytest.mark.parametrize("minimum, maximum", [("minMeanLuma", "maxMeanLuma"), ("minStdLuma", "maxStdLuma"),
                                              ("minHighFrequencyVariance", "maxHighFrequencyVariance")])
def test_min_at_or_above_max_is_refused(minimum, maximum):  # finding 4, LOW-1
    record = copy.deepcopy(CAMERA_RECORD)
    record["thresholds"][minimum] = record["thresholds"][maximum]
    with pytest.raises(ValueError):
        C.SmartCameraParams.from_record(record)


def test_no_age_threshold_in_the_camera_checks():  # the age bound is the front zone's AD-06 window
    assert "maxAgeNs" not in C.THRESHOLDS


def test_logical_and_plausibility_classes():
    px = textured()
    s, cam = stage([]), camera()
    out, delivered = s.process(item(5, WORLD, px), px)
    assert cam.step(WORLD - 1, out, delivered)["checks"]["logical"]["failed"] == ["future-origin"]
    assert "sequence-duplicate" in cam.step(WORLD, out, delivered)["checks"]["logical"]["failed"]
    bad = camera().step(WORLD, out, delivered[:-1])
    assert "digest-or-length" in bad["checks"]["logical"]["failed"] and bad["checks"]["statistical"]["verdict"] == "not-evaluated"
    wrong = camera().step(WORLD, dict(out, width=WIDTH + 1), delivered)
    assert wrong["checks"]["plausibility"]["failed"] == ["geometry"]
    late = camera().step(WORLD + 200 * MS, out, delivered)
    assert late["indicators"]["ageNs"] == 200 * MS and late["checks"]["statistical"]["verdict"] == "pass"  # age is an indicator
    assert camera().step(WORLD, {"schema": "other"}, delivered)["checks"]["logical"]["failed"] == ["malformed"]
