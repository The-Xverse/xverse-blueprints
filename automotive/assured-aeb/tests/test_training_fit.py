"""Training4b stdlib contract cases. Genuine framework verification has its own explicit worker driver."""
from __future__ import annotations

import ast
import copy
import json
import math
from pathlib import Path
import struct
import sys
import sysconfig

import pytest

from assured_aeb.perception import training_record as T, training_worker as W, training_weights as S
from assured_aeb.perception.training_io import canonical, record_digest, sha
from assured_aeb.perception.training_loop import checkpoint_is_better, epoch_order, equal_example_mean
from assured_aeb.perception.training_network import parameter_shapes
from training4a_fixture import build


def admitted(tmp_path):
    fixture = build(tmp_path)
    job = T.TrainingJob.from_bytes(canonical(fixture[0]), max_record_bytes=1_000_000)
    stage = {"schema": W.STAGE_SCHEMA, "jobSha256": job.sha256, "sourceClosureSha256": W.code_digest()}
    return fixture, job, stage


def weight_package(job, stage):
    data = {name: struct.pack("<f", 0.25) * math.prod(shape) for name, shape in parameter_shapes(job).items()}
    return S.encode_weights(data, job, sha(canonical(stage)))


def test_stage_binding_is_separate_exact_and_preserves_three_file_job_closure(tmp_path):
    _, job, stage = admitted(tmp_path)
    assert T.CODE_FILES == ("training_record.py", "training_io.py", "dataset_consumer.py")
    assert W.admit_stage(canonical(stage), job, max_record_bytes=1_000_000) == stage
    for changed in ({**stage, "jobSha256": "0" * 64}, {**stage, "sourceClosureSha256": "0" * 64}, {**stage, "extra": 1}):
        with pytest.raises(ValueError):
            W.admit_stage(canonical(changed), job, max_record_bytes=1_000_000)


def test_bad_job_and_stage_refuse_before_any_worker_effect_or_framework(tmp_path, monkeypatch):
    fixture, job, stage = admitted(tmp_path)
    def unexpected(*args, **kwargs):
        raise AssertionError("isolation/effects reached before invalid input refused")
    monkeypatch.setattr(W, "check_worker_isolation", unexpected)
    before = set(sys.modules)
    args = dict(max_record_bytes=1_000_000, identity_path="/TEST-ONLY/identity", lock_path="/TEST-ONLY/lock",
                parent_netns="net:[0]", output_directory=tmp_path / "never-created")
    for bad_job, bad_stage in ((b'{"schema":1}', canonical(stage)),
                                (canonical(fixture[0]), canonical({**stage, "jobSha256": "0" * 64}))):
        with pytest.raises(ValueError):
            W.run_training(bad_job, canonical(fixture[1]), bad_stage, **args)
    assert not (tmp_path / "never-created").exists()
    assert not any(name in set(sys.modules) - before for name in ("torch", "numpy", "onnxruntime"))


def test_data_order_is_a_seeded_identity_permutation_without_mutation():
    values = [{"runId": "fit", "frame": i, "rawSha256": sha(bytes([i]))} for i in range(20)]
    original = copy.deepcopy(values)
    ordered = epoch_order(values, seed=123, epoch=1)
    assert values == original and sorted(x["frame"] for x in ordered) == list(range(20))
    assert ordered == epoch_order(list(reversed(values)), seed=123, epoch=1)
    assert ordered != epoch_order(values, seed=123, epoch=2)
    assert ordered != epoch_order(values, seed=124, epoch=1)


def test_loss_aggregation_weights_examples_and_checkpoint_ties_choose_earliest():
    assert equal_example_mean([1.0, 1.0, 7.0]) == 3.0  # final short batch is one example, not half population
    assert checkpoint_is_better(2.0, 1, None, None)
    assert checkpoint_is_better(1.0, 3, 2.0, 2)
    assert not checkpoint_is_better(1.0, 3, 1.0, 2)
    assert checkpoint_is_better(1.0, 1, 1.0, 2)
    for values in ([], [math.nan], [math.inf]):
        with pytest.raises(ValueError): equal_example_mean(values)


def test_named_float32_weight_roundtrip_is_safe_deterministic_and_job_shaped(tmp_path):
    _, job, stage = admitted(tmp_path)
    first, blob = weight_package(job, stage)
    assert (first, blob) == weight_package(job, stage)
    decoded = S.decode_weights(first, blob, job, stage_sha256=sha(canonical(stage)))
    assert {name: item["shape"] for name, item in decoded.items()} == parameter_shapes(job)
    assert len(blob) == job.parameter_count * 4
    assert all(set(item) == {"shape", "data"} for item in decoded.values())
    decoded.clear()
    assert S.decode_weights(first, blob, job, stage_sha256=sha(canonical(stage)))


@pytest.mark.parametrize("kind", ["name", "dtype", "shape", "bool-shape", "huge-shape", "offset", "length", "tensor-hash", "named-hash", "extra", "trailing", "nonfinite", "blob-hash", "stage", "job"])
def test_weight_reader_refuses_rehashed_structural_and_numeric_corruption(tmp_path, kind):
    _, job, stage = admitted(tmp_path)
    encoded, blob = weight_package(job, stage)
    descriptor = json.loads(encoded)
    tensor = descriptor["tensors"][0]
    if kind == "name": tensor["name"] = "unknown"
    elif kind == "dtype": tensor["dtype"] = "object"
    elif kind == "shape": tensor["shape"][0] += 1
    elif kind == "bool-shape": tensor["shape"][0] = True
    elif kind == "huge-shape": tensor["shape"][0] = 10**100
    elif kind == "offset": tensor["byteOffset"] = 1
    elif kind == "length": tensor["byteLength"] += 4
    elif kind == "tensor-hash": tensor["sha256"] = "0" * 64
    elif kind == "named-hash": descriptor["namedWeightsSha256"] = "0" * 64
    elif kind == "extra": descriptor["extra"] = None
    elif kind == "trailing": blob += b"\0\0\0\0"
    elif kind == "nonfinite":
        blob = struct.pack("<f", math.inf) + blob[4:]
        tensor["sha256"] = sha(blob[:tensor["byteLength"]])
        descriptor["namedWeightsSha256"] = record_digest([{key: t[key] for key in ("name", "dtype", "shape", "sha256")} for t in descriptor["tensors"]])
    elif kind == "blob-hash": blob = bytes([blob[0] ^ 1]) + blob[1:]
    elif kind == "stage": descriptor["stageSha256"] = "0" * 64
    elif kind == "job": descriptor["jobSha256"] = "0" * 64
    if kind != "blob-hash": descriptor["weightsSha256"] = sha(blob)
    with pytest.raises(ValueError):
        S.decode_weights(canonical(descriptor), blob, job, stage_sha256=sha(canonical(stage)))


def test_output_total_limit_and_existing_directory_never_overwrite(tmp_path):
    path = tmp_path / "output"
    with pytest.raises(ValueError): W._write_outputs(path, {"weights.f32": b"123", "weights.json": b"456"}, maximum=5, disk_limit=100)
    assert not path.exists()
    path.mkdir()
    (path / "sentinel").write_bytes(b"preserve")
    with pytest.raises(FileExistsError): W._write_outputs(path, {"weights.f32": b"123"}, maximum=5, disk_limit=100)
    assert (path / "sentinel").read_bytes() == b"preserve"


def test_unsafe_namespace_and_preloaded_framework_refuse_without_framework_import(monkeypatch):
    with pytest.raises(ValueError): W.check_worker_isolation("invented")
    monkeypatch.setitem(sys.modules, "torch", object())
    with pytest.raises(ValueError): W.check_worker_isolation("net:[0]")


def test_only_offline_worker_imports_frameworks_and_no_pickle_format_is_used():
    root = Path(W.__file__).parent
    files = [root / name for name in W.CODE_FILES]
    for path in files:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                assert not any(name.split(".")[0] in {"pickle", "onnxruntime"} for name in names)
    runtime_root = root.parent
    offline = {"training_record", "training_io", "dataset_consumer", *(Path(name).stem for name in W.CODE_FILES)}
    for path in runtime_root.rglob("*.py"):
        if path.parent == root and path.stem in offline:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import): names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom): names = [node.module or "", *(alias.name for alias in node.names)]
            else: continue
            assert not any(offline.intersection(name.split(".")) for name in names), path


def test_import_path_allowlist_refuses_non_site_dependency_shadowing(tmp_path, monkeypatch):
    from xverse_compat.inference import preprocess as shared
    safe = [str(Path(W.__file__).resolve().parents[2]), str(Path(shared.__file__).resolve().parents[2]), sysconfig.get_paths()["stdlib"]]
    monkeypatch.setattr(W.sys, "path", safe)
    W.check_import_paths([])
    for extra in (str(tmp_path), ".", ""):
        monkeypatch.setattr(W.sys, "path", safe + [extra])
        with pytest.raises(ValueError): W.check_import_paths([])


def test_failed_output_write_cleans_only_its_fresh_files(tmp_path, monkeypatch):
    root = tmp_path / "failed-output"
    def fail(fd): raise OSError("TEST-ONLY fsync failure")
    monkeypatch.setattr(W.os, "fsync", fail)
    with pytest.raises(OSError): W._write_outputs(root, {"weights.f32": b"123"}, maximum=10, disk_limit=10)
    assert not root.exists()


def test_public_weight_reader_requires_external_expected_report_pins(tmp_path):
    _, job, stage = admitted(tmp_path / "fixture")
    descriptor, blob = weight_package(job, stage)
    root = tmp_path / "weights"
    root.mkdir()
    (root / "weights.json").write_bytes(descriptor)
    (root / "weights.f32").write_bytes(blob)
    expected = dict(stage_sha256=sha(canonical(stage)), descriptor_sha256=sha(descriptor), weights_sha256=sha(blob))
    assert S.read_weights(root, job, **expected)
    replacement = {name: struct.pack("<f", 0.5) * math.prod(shape) for name, shape in parameter_shapes(job).items()}
    new_descriptor, new_blob = S.encode_weights(replacement, job, sha(canonical(stage)))
    assert S.decode_weights(new_descriptor, new_blob, job, stage_sha256=expected["stage_sha256"])
    (root / "weights.json").write_bytes(new_descriptor)
    (root / "weights.f32").write_bytes(new_blob)
    with pytest.raises(ValueError): S.read_weights(root, job, **expected)
