"""WP-13 #3 offline contracts; all model/data/threshold values here are TEST-ONLY.

Standard-library tests do not import an ML package. The genuine pinned-loader tests run only in a separate,
network-isolated U4 process when explicit compat/site paths are supplied. Absence of that environment is a skip,
never a successful runtime verification.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import types

import pytest

from assured_aeb import camera_inference as C
from assured_aeb import fusion_aeb as F
from assured_aeb import model_contract as M
from assured_aeb import postprocess as P

HERE = Path(__file__).resolve().parents[1]
FIXTURE = HERE / "tests/fixtures/tiny-camera-model.onnx"
FIXTURE_SHA256 = "016a737e777968993e6d830cd4ff8a16ebaf6f5e610004eab5e92e87386a1d8a"
G = runpy.run_path(str(HERE / "tests/fixtures/make_camera_model.py"))
POST = G["POSTPROCESS"]
SCHEMA = G["SCHEMA"]
LABELS = tuple(POST["binLabels"])
PIXELS = bytes(range(256)) * 4
SHA = hashlib.sha256(PIXELS).hexdigest()
PROVENANCE = {"modelDigest": "a" * 64, "preprocessParamsSha256": "b" * 64, "postprocessSha256": "c" * 64}
RESULT = {"occupancyProbability": 0.8, "binProbabilities": [0.05, 0.05, 0.7, 0.05, 0.05, 0.1],
          "predictedBin": "bin-0", "oodScore": 0.3, "oodFlag": False}


def _wire(parts):
    out = b""
    for number, wire, value in parts:
        if wire == 0:
            out += G["integer"](number, value)
        elif wire == 2:
            out += G["blob"](number, value)
        else:
            out += G["varint"](number << 3 | wire) + value
    return out


def _replace(data, number, values):
    return _wire([part for part in M.fields(data) if part[0] != number] + values)


def _metadata(data, key, value):
    parts = []
    for number, wire, raw in M.fields(data):
        if number == 14:
            item = M.fields(raw)
            if next(v.decode() for n, _, v in item if n == 1) == key:
                raw = G["text"](1, key) + G["text"](2, value)
        parts.append((number, wire, raw))
    return _wire(parts)


@pytest.mark.parametrize("change", [
    lambda r: r.pop("schema"), lambda r: r.update(extra=True), lambda r: r.update(schema="unknown"),
    lambda r: r.update(outputs={"occupancy": "same", "bins": "same"}),
    lambda r: r.update(binLabels=["bin-0", "bin-0"]), lambda r: r.update(binLabels=["invalid", "beyond"]),
    lambda r: r["calibration"].update(method="unapproved"), lambda r: r["calibration"].update(method=[]),
    lambda r: r["calibration"]["params"].update(occupancyTemperature=0),
    lambda r: r["calibration"]["params"].update(binTemperature=math.nan),
    lambda r: r["calibration"]["params"].update(binTemperature=10 ** 1000),
    lambda r: r["ood"].update(method="unapproved"), lambda r: r["ood"].update(method={}),
    lambda r: r["ood"].update(threshold=math.inf), lambda r: r["ood"].update(threshold=True),
    lambda r: r["ood"]["params"].update(extra=1),
])
def test_postprocess_record_refuses_missing_unknown_or_non_finite_values(change):
    record = copy.deepcopy(POST)
    change(record)
    with pytest.raises(ValueError):
        P.parse_record(record)


def test_postprocess_metadata_is_canonical_and_binds_code_without_numpy():
    metadata = P.metadata_entry(copy.deepcopy(POST))
    parsed = P.parse(metadata)
    assert parsed.bin_labels == LABELS
    assert parsed.sha256 == hashlib.sha256(metadata[P.META_KEY].encode()).hexdigest()
    P.verify_binding(metadata)
    with pytest.raises(ValueError):
        P.parse({**metadata, P.META_KEY: json.dumps(POST, indent=2)})
    with pytest.raises(ValueError):
        P.verify_binding({**metadata, P.CODE_KEY: "0" * 64})
    assert P.parse_record({**copy.deepcopy(POST), "ood": {"method": "entropy", "params": {}, "threshold": 1.0}}).ood == "entropy"


def test_checked_in_fixture_has_fixed_bytes_static_schema_and_only_v1_operators():
    data = FIXTURE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == FIXTURE_SHA256
    contract = M.inspect(data)
    assert (contract.inputs, contract.outputs) == C.parse_model_schema(SCHEMA)
    assert set(contract.operators) == {"Conv", "Relu", "GlobalAveragePool", "Flatten", "Gemm"}
    assert "TEST-ONLY" in contract.metadata["purpose"]
    P.verify_binding(contract.metadata)


@pytest.mark.parametrize("data", [b"", b"\x80", b"\x0b", b"\x00", b"\x0a\x80\x00", b"\x0a\x08x", b"\x08" + b"\x80" * 10])
def test_static_reader_refuses_bad_or_unsupported_protobuf(data):
    with pytest.raises(ValueError):
        M.inspect(data)


def test_static_reader_refuses_duplicate_metadata_and_singular_model_fields():
    data = FIXTURE.read_bytes()
    duplicate = G["blob"](14, G["text"](1, "purpose") + G["text"](2, "duplicate"))
    for invalid in (data + duplicate, data + G["integer"](1, 7), data + G["blob"](7, G["graph_bytes"]())):
        with pytest.raises(ValueError):
            M.inspect(invalid)


@pytest.mark.parametrize("kind", ["ir", "opset", "custom-op", "output-duplicate", "external", "subgraph", "non-finite-weight"])
def test_static_reader_refuses_unsupported_graph_contracts(kind):
    data = FIXTURE.read_bytes()
    graph = next(v for n, _, v in M.fields(data) if n == 7)
    if kind == "ir":
        data = _replace(data, 1, [(1, 0, 8)])
    elif kind == "opset":
        data = _replace(data, 8, [(8, 2, G["text"](1, "") + G["integer"](2, 14))])
    elif kind == "custom-op":
        graph = _replace(graph, 1, [(1, 2, G["node"]("Custom", ["image"], ["new"], "custom"))])
        data = _replace(data, 7, [(7, 2, graph)])
    elif kind == "output-duplicate":
        graph = _replace(graph, 12, [(12, 2, G["value_info"]("same", (1, 1)))] * 2)
        data = _replace(data, 7, [(7, 2, graph)])
    elif kind == "external":
        graph += G["blob"](5, G["tensor"]("external", (1,), [1.0]) + G["blob"](13, b"location"))
        data = _replace(data, 7, [(7, 2, graph)])
    elif kind == "subgraph":
        graph += G["blob"](15, b"unsupported")
        data = _replace(data, 7, [(7, 2, graph)])
    else:
        graph += G["blob"](5, G["tensor"]("nan", (1,), [math.nan]))
        data = _replace(data, 7, [(7, 2, graph)])
    with pytest.raises(ValueError):
        M.inspect(data)


@pytest.mark.parametrize("change", [
    lambda r: r.update(inputs=[]), lambda r: r.update(outputs=[]),
    lambda r: r["inputs"][0].update(shape=[1, True, 8, 8]),
    lambda r: r["outputs"][0].update(shape=[1, "dynamic"]),
    lambda r: r["outputs"][1].update(name="occupancy_logit"),
    lambda r: r["inputs"][0].update(type="tensor(double)"),
])
def test_model_schema_is_mandatory_static_and_unambiguous(change):
    record = copy.deepcopy(SCHEMA)
    change(record)
    with pytest.raises(ValueError):
        C.parse_model_schema(record)
    with pytest.raises(ValueError):
        C.parse_model_schema(None)


def test_before_session_refusals_without_an_ml_import(monkeypatch, tmp_path):
    calls = []
    class Refused(Exception):
        pass
    def verified(path, digest):
        data = Path(path).read_bytes()
        if "sha256:" + hashlib.sha256(data).hexdigest() != digest:
            raise Refused("digest")
        return data
    def forbidden(*args, **kwargs):
        calls.append("session")
        raise AssertionError("a refusal must happen before the loader creates a session")
    loader = types.SimpleNamespace(verified_bytes=verified, load_model=forbidden, ModelRefused=Refused)
    pre = types.SimpleNamespace(load_params=lambda r: types.SimpleNamespace(in_w=16, in_h=16, out_w=8, out_h=8),
                                verify_binding=lambda *args: None)
    root = types.ModuleType("xverse_compat"); root.__path__ = []
    package = types.ModuleType("xverse_compat.inference"); package.loader = loader; package.preprocess = pre
    live = types.ModuleType("xverse_compat.live"); live.__path__ = []
    frames = types.ModuleType("xverse_compat.live.frames"); frames.load_format = lambda r: dict(r)
    for name, module in (("xverse_compat", root), ("xverse_compat.inference", package),
                         ("xverse_compat.live", live), ("xverse_compat.live.frames", frames)):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv("ORT_DISABLE_TELEMETRY", "1")
    data = FIXTURE.read_bytes()
    variants = [(_metadata(data, P.META_KEY, "not-json"), SCHEMA, "1"),
                (_metadata(data, P.CODE_KEY, "0" * 64), SCHEMA, "1"),
                (data, {**SCHEMA, "inputs": [{"name": "image", "shape": [1, 3, 4, 4], "type": "tensor(float)"}]}, "1"),
                (data, SCHEMA, "0")]
    with C.SpoolReader(tmp_path) as spool:
        for index, (value, schema, telemetry) in enumerate(variants):
            path = tmp_path / f"model-{index}"
            path.write_bytes(value)
            monkeypatch.setenv("ORT_DISABLE_TELEMETRY", telemetry)
            with pytest.raises((ValueError, Refused)):
                C.CameraInference.load(model_path=path, model_digest="sha256:" + hashlib.sha256(value).hexdigest(),
                                       model_schema=schema, preprocess_record=G["PREPROCESS"], frame_format=G["FMT"], spool=spool)
        monkeypatch.setenv("ORT_DISABLE_TELEMETRY", "1")
        monkeypatch.setitem(sys.modules, "onnxruntime", types.ModuleType("onnxruntime"))
        path = tmp_path / "already-imported.onnx"; path.write_bytes(data)
        with pytest.raises(Refused):
            C.CameraInference.load(model_path=path, model_digest="sha256:" + hashlib.sha256(data).hexdigest(),
                                   model_schema=SCHEMA, preprocess_record=G["PREPROCESS"], frame_format=G["FMT"], spool=spool)
    assert calls == []


def _spool_file(root, pixels=PIXELS):
    digest = hashlib.sha256(pixels).hexdigest()
    path = root / digest[:2] / digest
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(pixels)
    return path


def test_spool_verifies_length_and_digest_and_pins_the_root(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    path = _spool_file(root)
    with C.SpoolReader(root) as reader:
        assert reader.read(SHA, len(PIXELS)) == (PIXELS, None)
        assert reader.read(SHA, len(PIXELS) + 1) == (None, "length")
        path.write_bytes(b"x" * len(PIXELS))
        assert reader.read(SHA, len(PIXELS)) == (None, "digest")
        path.write_bytes(PIXELS)
        root.rename(tmp_path / "retained-root"); root.mkdir()
        assert reader.read(SHA, len(PIXELS)) == (PIXELS, None)
    assert reader.read(SHA, len(PIXELS)) == (None, "closed")


def test_spool_refuses_symlink_components_non_regular_files_and_bad_inputs(tmp_path):
    outside = tmp_path / "outside"; outside.mkdir()
    _spool_file(outside)
    root = tmp_path / "root"; root.mkdir()
    (root / SHA[:2]).symlink_to(outside / SHA[:2], target_is_directory=True)
    with C.SpoolReader(root) as reader:
        assert reader.read(SHA, len(PIXELS))[0] is None
    (root / SHA[:2]).unlink(); (root / SHA[:2]).mkdir()
    target = root / SHA[:2] / SHA
    target.symlink_to(outside / SHA[:2] / SHA)
    with C.SpoolReader(root) as reader:
        assert reader.read(SHA, len(PIXELS))[0] is None
        assert reader.read("../escape", len(PIXELS)) == (None, "digest-malformed")
        assert reader.read(SHA, -1) == (None, "length-malformed")
        target.unlink(); os.mkfifo(target)
        assert reader.read(SHA, len(PIXELS)) == (None, "not-a-regular-file")
    link = tmp_path / "link"; link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        C.SpoolReader(link)
    with pytest.raises(ValueError):
        C.SpoolReader("relative-root")


def _evidence():
    verdict = {"verdict": "pass", "failed": []}
    return {"schema": C.CAMERA_EVIDENCE, "source": "front-zone", "stream": C.STREAM, "sensor": "smart-camera",
            "originNs": 1000, "receivedNs": 1000, "ageNs": 0, "sequence": 1,
            "checks": {"integrity": copy.deepcopy(verdict), "sequence": "ok", "fresh": True, "plausibility": "pass",
                       "sensorSelfCheck": {key: copy.deepcopy(verdict) for key in ("logical", "plausibility", "statistical")}},
            "payload": {"frameSha256": SHA, "frame": 7, "indicators": {"ageNs": 0, "sequenceGap": 0, "sequenceStatus": "ok",
                        "meanLuma": 128.0, "stdLuma": 32.0, "darkFraction": 0.0, "brightFraction": 0.0,
                        "highFrequencyVariance": 1.0}}}


def _role(spool, infer=None):
    return C.CameraInference(infer=infer or (lambda raw: copy.deepcopy(RESULT)), frame_length=len(PIXELS), spool=spool,
                             provenance=PROVENANCE, bin_labels=LABELS)


def test_nominal_output_is_small_and_matches_fusion_contract(tmp_path):
    _spool_file(tmp_path)
    with C.SpoolReader(tmp_path) as spool:
        role = _role(spool)
        result = role.step(_evidence())
        assert result["state"] == "NOMINAL" and result["reason"] is None
        assert set(result) == F.PERCEPTION_MEMBERS == C.PERCEPTION_MEMBERS
        assert set(result["provenance"]) == {"modelDigest", "preprocessParamsSha256", "postprocessSha256"}
        assert F._perception_ok(result)
        assert len(json.dumps(result, allow_nan=False)) < 65536
        assert role.step(_evidence())["reason"] == "camera-evidence-replayed"


@pytest.mark.parametrize("change", [
    lambda r: r.update(source="proposer"), lambda r: r.update(extra="faultId"),
    lambda r: r["payload"].update(frame=True), lambda r: r["payload"].update(frameSha256="bad"),
    lambda r: r["checks"].update(fresh=False), lambda r: r["checks"].update(sequence="duplicate"),
    lambda r: r["checks"]["sensorSelfCheck"].pop("statistical"),
    lambda r: r["checks"]["sensorSelfCheck"]["statistical"].update(verdict="not-evaluated"),
    lambda r: r["payload"]["indicators"].update(meanLuma=math.nan),
    lambda r: r["payload"]["indicators"].update(faultId="never-forwarded"),
])
def test_invalid_or_unknown_evidence_never_calls_inference(change, tmp_path):
    def forbidden(raw):
        raise AssertionError("inference must not run")
    evidence = _evidence(); change(evidence)
    with C.SpoolReader(tmp_path) as spool:
        result = _role(spool, forbidden).step(evidence)
        assert result["state"] == "UNCERTAIN" and result["reason"]
        assert all(result[key] is None for key in C.RESULT_MEMBERS)
        assert "never-forwarded" not in json.dumps(result, allow_nan=False)


def test_missing_frame_is_unknown_without_fabricated_values(tmp_path):
    with C.SpoolReader(tmp_path) as spool:
        result = _role(spool).step(_evidence())
        assert result["reason"] == "frame-unavailable: missing" and result["state"] == "UNCERTAIN"
        assert not F._perception_ok(result)


@pytest.mark.parametrize("cause", ["sensor", "ood"])
def test_explicit_statistical_or_ood_failure_is_degraded(cause, tmp_path):
    _spool_file(tmp_path)
    evidence, output = _evidence(), copy.deepcopy(RESULT)
    if cause == "sensor":
        evidence["checks"]["sensorSelfCheck"]["statistical"] = {"verdict": "fail", "failed": ["mean-luma"]}
    else:
        output["oodFlag"] = True
    with C.SpoolReader(tmp_path) as spool:
        result = _role(spool, lambda raw: output).step(evidence)
        assert result["state"] == "DEGRADED" and result["reason"] in ("ood", "sensor-statistical")


@pytest.mark.parametrize("bad", [{**RESULT, "oodScore": math.nan}, {**RESULT, "predictedBin": "unknown"},
                                  {**RESULT, "binProbabilities": []}, {**RESULT, "faultId": "private"}])
def test_malformed_inference_results_are_unknown(bad, tmp_path):
    _spool_file(tmp_path)
    with C.SpoolReader(tmp_path) as spool:
        result = _role(spool, lambda raw: bad).step(_evidence())
        assert result["state"] == "UNCERTAIN" and result["reason"] == "inference-failed:ValueError"
        assert all(result[key] is None for key in C.RESULT_MEMBERS)


def test_ml_modules_have_no_training_or_evaluation_dependency():
    for name in ("camera_inference", "model_contract", "postprocess"):
        tree = ast.parse((HERE / "assured_aeb" / f"{name}.py").read_text())
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(any(token in value for token in ("torch", "onnxruntime", "labels", "perception")) for value in names)
    assert not any(hasattr(C.CameraInference, name) for name in ("train", "fit", "update", "learn"))


# ---- actual U4 unit-pattern checks, never in the host process ---------------------------------------
COMPAT = Path(os.environ["XVERSE_COMPAT_SRC"]) if os.environ.get("XVERSE_COMPAT_SRC") else None
SITE = Path(os.environ["XVERSE_AEB_U4_SITE"]) if os.environ.get("XVERSE_AEB_U4_SITE") else None
PY313 = Path("/home/jefferson/.pyenv/versions/3.13.13/bin/python3.13")
NETNS = shutil.which("unshare") is not None and subprocess.run(["unshare", "-rn", "true"], capture_output=True).returncode == 0
ready = bool(COMPAT and (COMPAT / "xverse_compat/inference/unit.py").is_file() and SITE and (SITE / "onnxruntime").is_dir() and PY313.is_file() and NETNS)
needs_runtime = pytest.mark.skipif(not ready, reason="explicit compat/src, pinned U4 site and unshare -rn are required")


@needs_runtime
@pytest.mark.parametrize("mode", ["run", "logits", "postprocess", "wrong-digest", "wrong-schema", "wrong-binding", "wrong-post-code", "wrong-metadata", "telemetry"])
def test_real_pinned_loader_and_shared_preprocess_in_a_network_namespace(mode):
    spec = importlib.util.spec_from_file_location("pinned_u4_unit_template", COMPAT / "xverse_compat/inference/unit.py")
    unit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(unit)  # the real stdlib-only command template, without importing an ML package here
    env = unit.environment(SITE, (COMPAT, HERE, HERE / "tests"), home="/nonexistent-u4-test-home")
    command = ["unshare", "-rn", *unit.command(PY313, "camera_inference_probe", mode)]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["passed"] is True and summary["mode"] == mode


@pytest.mark.skipif(not (COMPAT and (COMPAT / "xverse_compat/inference/preprocess.py").is_file() and PY313.is_file()),
                    reason="explicit compat/src and pinned interpreter are needed for fixture regeneration")
def test_fixture_regenerates_from_the_genuine_shared_preprocessing_binding(tmp_path):
    output = tmp_path / "fixture.onnx"
    env = {"PATH": "/usr/bin", "HOME": "/nonexistent-fixture-home", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": f"{COMPAT}:{HERE}"}
    result = subprocess.run([str(PY313), "-S", "-s", "-B", str(HERE / "tests/fixtures/make_camera_model.py"), str(output)],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == FIXTURE.read_bytes()


# R13ML-1: source check forms, independently reviewed before these repairs.
@pytest.mark.parametrize("check_name", ["logical", "plausibility", "statistical"])
@pytest.mark.parametrize("malformed", [
    {"verdict": "pass", "failed": ["bad-input"]},
    {"verdict": "not-evaluated", "failed": ["bad-input"]},
    {"verdict": "fail", "failed": []}, {"verdict": "fail", "failed": [""]},
    {"verdict": "fail", "failed": [1]}, {"verdict": "unknown", "failed": []},
])
def test_contradictory_sensor_check_never_calls_inference(check_name, malformed, tmp_path):
    calls = []
    evidence = _evidence()
    evidence["checks"]["sensorSelfCheck"][check_name] = copy.deepcopy(malformed)
    with C.SpoolReader(tmp_path) as spool:
        result = _role(spool, lambda raw: calls.append(raw) or copy.deepcopy(RESULT)).step(evidence)
    assert calls == [] and result["state"] == "UNCERTAIN"
    assert all(result[key] is None for key in C.RESULT_MEMBERS)


def test_an_undeclared_fourth_sensor_class_never_calls_inference(tmp_path):
    calls = []
    evidence = _evidence()
    evidence["checks"]["sensorSelfCheck"]["fourth-class"] = {"verdict": "pass", "failed": []}
    with C.SpoolReader(tmp_path) as spool:
        result = _role(spool, lambda raw: calls.append(raw) or copy.deepcopy(RESULT)).step(evidence)
    assert calls == [] and result["state"] == "UNCERTAIN"
    assert "sensor-check-classes" in result["reason"]


def test_front_integrity_pass_with_failed_codes_is_unknown(tmp_path):
    evidence = _evidence()
    evidence["checks"]["integrity"] = {"verdict": "pass", "failed": ["bad-input"]}
    calls = []
    with C.SpoolReader(tmp_path) as spool:
        result = _role(spool, lambda raw: calls.append(raw) or copy.deepcopy(RESULT)).step(evidence)
    assert calls == [] and result["state"] == "UNCERTAIN"


@pytest.mark.parametrize("statistical_failure", [False, True])
def test_genuine_smart_camera_and_front_zone_forms_remain_usable(statistical_failure, tmp_path):
    from assured_aeb import camera_chain as chain, radar_zone as zone
    fmt = dict(G["FMT"])
    stage = chain.CorruptionStage(chain.CorruptionSchedule.from_record(
        {"schema": chain.CORRUPTION, "seed": 7, "frameFormat": fmt, "events": []}))
    stage.bind_origin(1000)
    item = {"type": "item", "flowId": "camera", "sequence": 1, "originNs": 1000, "frame": 7,
            "value": {"width": 16, "height": 16, "fovDeg": 90.0, "rawSha256": SHA, "rawLength": len(PIXELS)}}
    delivered, raw = stage.process(item, PIXELS)
    camera = chain.SmartCamera(chain.SmartCameraParams.from_record({"schema": chain.CAMERA_CHECKS, "frameFormat": fmt,
        "stats": {"statsStride": 1, "darkLevel": 8, "brightLevel": 247, "sharpnessBoxLog2": 1},
        "thresholds": {"minMeanLuma": 255.0 if statistical_failure else 0.0, "maxMeanLuma": 255.0,
                       "minStdLuma": 0.0, "maxStdLuma": 255.0, "maxDarkFraction": 1.0, "maxBrightFraction": 1.0,
                       "minHighFrequencyVariance": 0.0, "maxHighFrequencyVariance": 65536.0}}))
    front = zone.FrontZone(zone.FrontZoneParams.from_record({"schema": zone.FRONT_ZONE,
                                                           "cameraFreshnessWindowNs": 1000, "radarFreshnessWindowNs": 1000}))
    evidence = dict(front.step(1000, [("smart-camera-evidence", camera.step(1000, delivered, raw))]))[C.STREAM]
    assert set(evidence["checks"]["sensorSelfCheck"]) == {"logical", "plausibility", "statistical"}
    _spool_file(tmp_path)
    calls = []
    with C.SpoolReader(tmp_path) as spool:
        result = _role(spool, lambda raw: calls.append(raw) or copy.deepcopy(RESULT)).step(evidence)
    assert calls == [PIXELS]
    assert result["state"] == ("DEGRADED" if statistical_failure else "NOMINAL")
    assert F._perception_ok(result)
