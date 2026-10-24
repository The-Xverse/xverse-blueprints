"""Actual pinned-loader/preprocessing probe, invoked only in the isolated U4 subprocess pattern.

All fixture values, repetitions and numeric comparison tolerances in this file are TEST-ONLY. No training,
SciPy/onnx/torch dependency, live simulator, scientific model or protocol choice is introduced.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import runpy
import sys
import tempfile

if os.environ.get("ORT_DISABLE_TELEMETRY") != "1":
    raise SystemExit("ORT_DISABLE_TELEMETRY=1 must precede imports")

from assured_aeb import camera_chain as CHAIN
from assured_aeb import camera_inference as C
from assured_aeb import fusion_aeb as F
from assured_aeb import postprocess as P
from assured_aeb import radar_zone as ZONE
from xverse_compat.inference import loader, preprocess as PRE

HERE = Path(__file__).resolve().parent.parent
G = runpy.run_path(str(HERE / "tests/fixtures/make_camera_model.py"))
PIXELS = bytes(range(256)) * 4


def arguments(path, spool, data):
    return dict(model_path=path, model_digest="sha256:" + hashlib.sha256(data).hexdigest(), model_schema=copy.deepcopy(G["SCHEMA"]),
                preprocess_record=copy.deepcopy(G["PREPROCESS"]), frame_format=dict(G["FMT"]), spool=spool)


def real_evidence(pixels, root):
    # The genuine U2 -> smart camera -> front zone path, with explicitly TEST-ONLY broad check thresholds.
    fmt, world = dict(G["FMT"]), 1_000_000_000_000
    stage = CHAIN.CorruptionStage(CHAIN.CorruptionSchedule.from_record(
        {"schema": CHAIN.CORRUPTION, "seed": 7, "frameFormat": fmt, "events": []}))
    stage.bind_origin(world)
    item = {"type": "item", "flowId": "camera", "sequence": 1, "originNs": world, "frame": 7,
            "value": {"width": 16, "height": 16, "fovDeg": 90.0, "rawSha256": hashlib.sha256(pixels).hexdigest(), "rawLength": len(pixels)}}
    delivered, raw = stage.process(item, pixels)
    camera = CHAIN.SmartCamera(CHAIN.SmartCameraParams.from_record({"schema": CHAIN.CAMERA_CHECKS, "frameFormat": fmt,
        "stats": {"statsStride": 1, "darkLevel": 8, "brightLevel": 247, "sharpnessBoxLog2": 1},
        "thresholds": {"minMeanLuma": 0.0, "maxMeanLuma": 255.0, "minStdLuma": 0.0, "maxStdLuma": 255.0,
                       "maxDarkFraction": 1.0, "maxBrightFraction": 1.0,
                       "minHighFrequencyVariance": 0.0, "maxHighFrequencyVariance": 65536.0}}))
    front = ZONE.FrontZone(ZONE.FrontZoneParams.from_record({"schema": ZONE.FRONT_ZONE,
                                                           "cameraFreshnessWindowNs": 1_000_000, "radarFreshnessWindowNs": 1_000_000}))
    evidence = dict(front.step(world, [("smart-camera-evidence", camera.step(world, delivered, raw))]))[C.STREAM]
    sha = hashlib.sha256(raw).hexdigest()
    target = root / sha[:2] / sha
    target.parent.mkdir(); target.write_bytes(raw)
    return evidence


def postprocess_checks():
    import numpy as np
    base = copy.deepcopy(G["POSTPROCESS"])
    logits = {"occupancy_logit": np.array([[0.5]], dtype=np.float32),
              "bin_logits": np.array([[0.0, 1.0, 2.0, 3.0, 4.0, 5.0]], dtype=np.float32)}
    result = P.apply(P.parse_record(base), logits)
    expected_occ = 1.0 / (1.0 + math.exp(-0.5 / 1.25))
    exponents = [math.exp((v - 5.0) / 0.75) for v in range(6)]
    probabilities = [v / sum(exponents) for v in exponents]
    assert abs(result["occupancyProbability"] - expected_occ) <= 1e-15
    assert max(abs(a - b) for a, b in zip(result["binProbabilities"], probabilities)) <= 1e-15
    assert result["predictedBin"] == "beyond"
    base["ood"] = {"method": "entropy", "params": {}, "threshold": 1.0}
    entropy = P.apply(P.parse_record(base), logits)
    assert abs(entropy["oodScore"] - (-sum(p * math.log(p) for p in probabilities))) <= 1e-15
    # Stable at extreme finite logits and a positive subnormal-scale temperature; no inf-inf softmax.
    base["calibration"]["params"] = {"occupancyTemperature": 1e-300, "binTemperature": 1e-300}
    extreme = P.apply(P.parse_record(base), {"occupancy_logit": np.array([[1e308]]),
        "bin_logits": np.array([[1e308, -1e308, 0.0, 1.0, 2.0, 3.0]])})
    assert extreme["occupancyProbability"] == 1.0 and extreme["binProbabilities"] == [1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert extreme["oodScore"] == 0.0
    malformed = [dict(logits, occupancy_logit=np.array([0.5])), dict(logits, bin_logits=np.array([[math.nan] * 6])),
                 dict(logits, bin_logits=np.array([[True] * 6])), dict(logits, extra=np.array([[0.0]]))]
    for item in malformed:
        try:
            P.apply(P.parse_record(G["POSTPROCESS"]), item)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed logits were accepted")
    tie = P.apply(P.parse_record(G["POSTPROCESS"]), {"occupancy_logit": np.zeros((1, 1)), "bin_logits": np.zeros((1, 6))})
    assert tie["predictedBin"] == "no-obstacle"


def main(mode):
    data = (HERE / "tests/fixtures/tiny-camera-model.onnx").read_bytes()
    if mode == "postprocess":
        postprocess_checks()
        return {"passed": True, "mode": mode}
    with tempfile.TemporaryDirectory(prefix="camera-inference-probe-") as tmp:
        root = Path(tmp); model = root / "model.onnx"; model.write_bytes(data)
        with C.SpoolReader(root) as spool:
            kwargs = arguments(model, spool, data)
            if mode.startswith("wrong-") or mode == "telemetry":
                if mode == "wrong-digest":
                    kwargs["model_digest"] = "sha256:" + "0" * 64
                elif mode == "wrong-schema":
                    kwargs["model_schema"]["inputs"][0]["shape"] = [1, 3, 4, 4]
                elif mode == "wrong-binding":
                    data = G["model_bytes"](metadata_override={"xverse.preprocess.paramsSha256": "0" * 64})
                elif mode == "wrong-post-code":
                    data = G["model_bytes"](metadata_override={P.CODE_KEY: "0" * 64})
                elif mode == "wrong-metadata":
                    data = G["model_bytes"](metadata_override={P.META_KEY: "not-json"})
                elif mode == "telemetry":
                    os.environ.pop("ORT_DISABLE_TELEMETRY")
                else:
                    raise ValueError(mode)
                if mode in ("wrong-binding", "wrong-post-code", "wrong-metadata"):
                    model.write_bytes(data); kwargs["model_digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
                calls = []
                original = loader.load_model
                def counted(*args, **kw):
                    calls.append(True)
                    return original(*args, **kw)
                loader.load_model = counted
                try:
                    C.CameraInference.load(**kwargs)
                except (ValueError, loader.ModelRefused):
                    assert not calls and "onnxruntime" not in sys.modules
                    return {"passed": True, "mode": mode, "sessionCalls": len(calls), "ortImported": False}
                raise AssertionError("a refused contract reached readiness")
            import numpy as np
            if mode == "logits":
                loaded = loader.load_model(model, kwargs["model_digest"], expected_inputs=C.parse_model_schema(G["SCHEMA"])[0],
                                           expected_outputs=C.parse_model_schema(G["SCHEMA"])[1])
                tensor = PRE.preprocess(PIXELS, G["FMT"], PRE.load_params(G["PREPROCESS"]))
                names = [item["name"] for item in G["SCHEMA"]["outputs"]]
                actual = dict(zip(names, loaded.session.run(names, {"image": tensor})))
                expected = G["reference"](np, tensor)
                diff = max(float(np.max(np.abs(actual[name] - expected[name]))) for name in names)
                assert diff <= 1e-5  # TEST-ONLY fixture tolerance, not the real-model tolerance
                return {"passed": True, "mode": mode, "maxAbsDiff": diff}
            if mode != "run":
                raise ValueError(mode)
            instance = C.CameraInference.load(**kwargs)
            evidence = real_evidence(PIXELS, root)
            record = instance.step(evidence)
            assert record["state"] in ("NOMINAL", "DEGRADED") and F._perception_ok(record)
            assert set(record["provenance"]) == {"modelDigest", "preprocessParamsSha256", "postprocessSha256"}
            assert instance.loader_record["providers"] == ["CPUExecutionProvider"]
            assert len(instance.audit_sha256) == 64
            assert hashlib.sha256(C._canonical(instance.audit_record)).hexdigest() == instance.audit_sha256
            hashes = [hashlib.sha256(C._canonical(instance.infer(PIXELS))).hexdigest() for _ in range(3)]
            assert len(set(hashes)) == 1
            model.write_bytes(b"replacement is not the loaded model")
            assert hashlib.sha256(C._canonical(instance.infer(PIXELS))).hexdigest() == hashes[0]
            # The environment must stay read-only under the U4 pattern.
            site = Path(np.__file__).resolve().parent.parent
            assert not list(site.rglob("*.pyc")) and not list(site.rglob("__pycache__"))
            return {"passed": True, "mode": mode, "state": record["state"], "auditSha256": instance.audit_sha256}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), allow_nan=False))
