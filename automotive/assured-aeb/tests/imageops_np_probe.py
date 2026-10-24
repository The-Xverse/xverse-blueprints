"""Bit-exactness probe: ``imageops_np`` against the standard-library reference ``imageops`` (review-wp13-imageops-np
finding 1 §1.3).

It runs in the U2/U3 unit pattern: the real CPython 3.13.13 with ``-S -s -B``, ``PYTHONDONTWRITEBYTECODE=1`` and
``PYTHONPATH=<sensor site-packages>:<assured-aeb>``. It needs numpy and the standard library only, with no pytest. It
prints one JSON summary: the comparison count, the failures (which must be empty), the numpy version, and an
informative timing on one 800 x 600 frame. The timing is not a budget; the budget is a D-4c measurement.

Every frame, schedule and parameter value below is TEST-ONLY.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import time

import numpy

from assured_aeb import camera_chain as C
from assured_aeb import imageops as I
from assured_aeb import imageops_np as N

SIZES = [(1, 1), (3, 2), (9, 7), (17, 5), (32, 24)]
MS = 1_000_000
WORLD = 1_000_000 * MS


class Probe:
    def __init__(self):
        self.count, self.failures = 0, []

    def same(self, label, a, b):
        self.count += 1
        if a != b:
            self.failures.append(label)


def frames(rng):
    for w, h in SIZES:
        yield f"{w}x{h}-random", w, h, rng.randbytes(w * h * 4)
        yield f"{w}x{h}-uniform", w, h, bytes([rng.randrange(256)] * 3 + [255]) * (w * h)
    w, h = 32, 24
    textured = bytearray()
    for y in range(h):
        for x in range(w):
            base = 128 + (40 if (x // 2 + y // 2) % 2 else -40)
            textured += bytes([max(0, min(255, base + rng.randint(-10, 10))) for _ in range(3)]) + b"\xff"
    yield "32x24-textured", w, h, bytes(textured)


def operations(p, rng):
    for label, w, h, f in frames(rng):
        for gain, offset in ((1.5, -10), (0.3, 40.5), (2.0, 0), (0.5, 0.5), (1.0, -0.5), (3.7, -200.25)):
            p.same(f"exposure {label} {gain} {offset}", N.exposure(f, gain, offset), I.exposure(f, gain, offset))
        for std in (0.5, 5.0, 20.0, 80.0):
            u = rng.randbytes(len(f))
            p.same(f"noise {label} {std}", N.add_noise(f, u, std), I.add_noise(f, u, std))
        for _ in range(4):
            rw, rh = rng.randint(1, w), rng.randint(1, h)
            x, y, v = rng.randint(0, w - rw), rng.randint(0, h - rh), rng.randrange(256)
            p.same(f"occlusion {label} {x},{y},{rw},{rh}", N.occlusion(f, w, x, y, rw, rh, v), I.occlusion(f, w, x, y, rw, rh, v))
        for log2 in range(1, I.MAX_BOX_LOG2 + 1):
            p.same(f"blur4 {label} {log2}", N.box_blur(f, w, h, log2), I.box_blur(f, w, h, log2))
            plane = I.luma(f)
            p.same(f"blur1 {label} {log2}", N.box_blur(plane, w, h, log2, channels=1), I.box_blur(plane, w, h, log2, channels=1))
        p.same(f"luma {label}", N.luma(f), I.luma(f))
        p.same(f"histogram {label}", N.histogram(f), I.histogram(f))
        p.same(f"moments {label}", N.moments(f), I.moments(f))
        for margin in range(0, 4):
            if 2 * margin < w and 2 * margin < h:
                plane = I.luma(f)
                p.same(f"interior {label} {margin}", N.interior(plane, w, h, margin), I.interior(plane, w, h, margin))
        for stride in (1, 2, 3):
            for sharpness in range(1, I.MAX_BOX_LOG2 + 1):
                margin = 1 << (sharpness - 1)
                if 2 * margin < w and 2 * margin < h:
                    kwargs = dict(stride=stride, dark_level=16, bright_level=239, sharpness_log2=sharpness)
                    p.same(f"statistics {label} {stride} {sharpness}", N.image_statistics(f, w, h, **kwargs),
                           I.image_statistics(f, w, h, **kwargs))


def large(p, rng):
    w, h = 800, 600  # the configured camera size (carla-sensors.json)
    f = rng.randbytes(w * h * 4)
    timing = {}
    for name, args in (("exposure", (f, 1.3, -7.5)), ("add_noise", (f, rng.randbytes(len(f)), 20.0)),
                       ("box_blur", (f, w, h, 3)), ("luma", (f,))):
        t0 = time.perf_counter()
        a = getattr(N, name)(*args)
        t1 = time.perf_counter()
        b = getattr(I, name)(*args)
        t2 = time.perf_counter()
        p.same(f"800x600 {name}", a, b)
        timing[name] = {"numpyMs": round((t1 - t0) * 1e3, 1), "referenceMs": round((t2 - t1) * 1e3, 1)}
    kwargs = dict(stride=4, dark_level=16, bright_level=239, sharpness_log2=2)
    t0 = time.perf_counter()
    a = N.image_statistics(f, w, h, **kwargs)
    t1 = time.perf_counter()
    b = I.image_statistics(f, w, h, **kwargs)
    t2 = time.perf_counter()
    p.same("800x600 statistics", a, b)
    timing["image_statistics"] = {"numpyMs": round((t1 - t0) * 1e3, 1), "referenceMs": round((t2 - t1) * 1e3, 1)}
    return timing


def chain(p, rng):
    """The camera chain end to end with ``ops=imageops_np`` against the default reference."""

    w, h = 32, 24
    fmt = {"schema": C.FRAME_FORMAT, "width": w, "height": h, "encoding": "bgra8"}
    events = [{"id": "e-exp", "kind": "exposure", "startNs": 0, "endNs": 100 * MS, "params": {"gain": 1.7, "offset": -12.5}},
              {"id": "e-occ", "kind": "occlusion", "startNs": 100 * MS, "endNs": 200 * MS,
               "params": {"x": 3, "y": 2, "width": 10, "height": 7, "value": 0}},
              {"id": "e-noise", "kind": "noise", "startNs": 200 * MS, "endNs": 300 * MS, "params": {"stdLevel": 20.0}},
              {"id": "e-blur", "kind": "blur", "startNs": 300 * MS, "endNs": 400 * MS, "params": {"boxLog2": 3}},
              {"id": "e-noise2", "kind": "noise", "startNs": 350 * MS, "endNs": 400 * MS, "params": {"stdLevel": 5.0}}]
    camera_record = {"schema": C.CAMERA_CHECKS, "frameFormat": dict(fmt),
                     "stats": {"statsStride": 1, "darkLevel": 16, "brightLevel": 239, "sharpnessBoxLog2": 1},
                     "thresholds": {"minMeanLuma": 60.0, "maxMeanLuma": 200.0, "minStdLuma": 20.0, "maxStdLuma": 45.0,
                                    "maxDarkFraction": 0.2, "maxBrightFraction": 0.2, "minHighFrequencyVariance": 100.0,
                                    "maxHighFrequencyVariance": 1600.0}}

    def build(ops):
        stage = C.CorruptionStage(C.CorruptionSchedule.from_record({"schema": C.CORRUPTION, "seed": 7, "frameFormat": dict(fmt),
                                                                    "events": events}), ops=ops)
        stage.bind_origin(WORLD)
        return stage, C.SmartCamera(C.SmartCameraParams.from_record(json.loads(json.dumps(camera_record))), ops=ops)

    (s_ref, c_ref), (s_np, c_np) = build(None), build(N)
    for k in range(9):
        pixels = rng.randbytes(w * h * 4)
        item = {"type": "item", "flowId": "camera", "sequence": k + 1, "originNs": WORLD + k * 50 * MS, "frame": k + 1,
                "value": {"width": w, "height": h, "fovDeg": 90.0, "rawSha256": hashlib.sha256(pixels).hexdigest(),
                          "rawLength": len(pixels)}}
        out_ref, f_ref = s_ref.process(item, pixels)
        out_np, f_np = s_np.process(item, pixels)
        p.same(f"chain stage {k}", (out_np, f_np), (out_ref, f_ref))
        p.same(f"chain camera {k}", c_np.step(WORLD + k * 50 * MS + MS, out_np, f_np),
               c_ref.step(WORLD + k * 50 * MS + MS, out_ref, f_ref))
    p.same("chain evidence", s_np.evidence, s_ref.evidence)


def main() -> int:
    rng = random.Random(20261024)
    p = Probe()
    for _ in range(3):  # three independent frame sets (TEST-ONLY seeds from one generator)
        operations(p, rng)
    timing = large(p, rng)
    chain(p, rng)
    print(json.dumps({"comparisons": p.count, "failures": p.failures, "numpy": numpy.__version__,
                      "numpyFile": numpy.__file__, "siteImported": "site" in sys.modules, "timing": timing}))
    return 1 if p.failures else 0


if __name__ == "__main__":
    sys.exit(main())
