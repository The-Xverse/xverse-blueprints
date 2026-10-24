"""Training4a strict stdlib consumer tests; every fixture number/source is TEST-ONLY, no frameworks."""
from __future__ import annotations

import ast
import builtins
import copy
import json
from pathlib import Path
import zlib

import pytest

from assured_aeb.perception import dataset_consumer as D, training_record as T
from assured_aeb.perception import training_io as IO
from assured_aeb.perception.training_io import canonical, parse_json, read_frame, read_regular, record_digest, sha
from training4a_fixture import admit, build, refresh_job, rehash


@pytest.fixture
def fixture(tmp_path):
    return build(tmp_path / "TEST-ONLY-dataset")


def test_genuine_producer_sources_admit_count_and_stream_without_framework_imports(fixture, monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert name.split(".")[0] not in {"torch", "numpy", "onnx", "onnxruntime"}, "framework imported during admission"
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    dataset = admit(fixture)
    report = dataset.report()
    assert report["classOrder"] == ["no-obstacle", "overlap", "bin-0", "bin-1", "beyond"]
    assert report["counts"]["selection"]["targetAbsent"] == 3
    assert report["counts"]["calibration"]["adjacentNegative"] == 3
    assert all(stats["unlabelledFrames"] == 1 for stats in report["counts"].values())
    assert all(run["recorderExclusions"] == {"no-observer-record": 1} for run in report["runs"].values())
    assert any("shared" in message for message in report["manifestReports"])
    assert report["trainingUpdates"] == 4  # final short fit batch is retained, not silently dropped
    for partition in T.PARTITIONS:
        samples = list(dataset.iter_samples(partition))
        assert len(samples) == 3 and all(len(sample["raw"]) == 64 for sample in samples)
        assert all(sample["occupancyTarget"] == int(sample["label"]["obstacle"]) for sample in samples)
        assert [sample["frame"] for sample in samples] == [100, 101, 102]
    report["counts"]["fit"]["classes"]["bin-0"] = 999
    assert dataset.report()["counts"]["fit"]["classes"]["bin-0"] == 1


@pytest.mark.parametrize("data", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}',
                                   b'{"x":'+b'9'*400+b'}', b'\xff', b'{"x":1} trailing'])
def test_strict_json_refuses_duplicate_nonfinite_unrepresentable_and_malformed_bytes(data):
    with pytest.raises(ValueError):
        parse_json(data, max_bytes=1000)


def test_json_limits_canonical_encoding_and_cycles_are_explicit(fixture):
    raw = canonical(fixture[0])
    with pytest.raises(ValueError):
        T.TrainingJob.from_bytes(raw, max_record_bytes=len(raw)-1)
    with pytest.raises(ValueError, match="canonical"):
        T.TrainingJob.from_bytes(raw+b"\n", max_record_bytes=1_000_000)
    cyclic = []; cyclic.append(cyclic)
    with pytest.raises(ValueError):
        canonical(cyclic)


def test_job_and_source_locator_access_returns_private_copies(fixture):
    job = T.TrainingJob.from_bytes(canonical(fixture[0]), max_record_bytes=1_000_000)
    sources = D.SourceLocations.from_bytes(canonical(fixture[1]), max_record_bytes=1_000_000)
    job.record()["optimisation"]["learningRate"] = 999
    sources.record()["runs"]["fit"]["labels"] = "/TEST-ONLY-mutated"
    assert job.record()["optimisation"]["learningRate"] == 0.1
    assert sources.record()["runs"]["fit"]["labels"] == fixture[1]["runs"]["fit"]["labels"]
    for key, value in (("class_order", ("invented",)), ("frame_bytes", 1), ("sha256", "0"*64)):
        with pytest.raises(AttributeError):
            setattr(job, key, value)


JOB_MUTATIONS = [
    ("optimisation", "method", "adam"), ("optimisation", "learningRate", 0), ("optimisation", "batchSize", True),
    ("optimisation", "epochs", 0), ("optimisation", "numWorkers", 1), ("optimisation", "device", "cuda"),
    ("optimisation", "intraOpThreads", 0), ("optimisation", "deterministicAlgorithms", False),
    ("optimisation", "momentum", -1), ("optimisation", "weightDecay", -1), ("optimisation", "nesterov", True),
    ("architecture", "binOutput", "image"), ("architecture", "convBlocks", []), ("architecture", "occupancyBias", 1),
    ("calibrationFit", "method", "iterative"), ("calibrationFit", "occupancyTemperatures", [1.0, 1.0]),
    ("calibrationFit", "binTemperatures", [0]), ("calibrationFit", "population", "test"),
    ("oodFit", "method", "entropy"), ("oodFit", "quantile", 0), ("oodFit", "quantile", 1.1),
    ("oodFit", "comparison", "greater-or-equal"), ("verification", "exactRepeatCount", 1),
    ("verification", "minimumDecisionAgreement", 1.1), ("verification", "sampleSelection", "random"),
]


@pytest.mark.parametrize("section,key,value", JOB_MUTATIONS)
def test_every_future_method_and_numeric_setting_is_checked_before_frameworks(fixture, section, key, value):
    fixture[0][section][key] = value
    with pytest.raises(ValueError):
        T.TrainingJob.from_bytes(canonical(fixture[0]), max_record_bytes=1_000_000)


@pytest.mark.parametrize("kind", ["missing", "extra", "closure", "input-pin", "seed", "conv", "float32", "tensor-bound", "raw-bound", "threshold"])
def test_closed_nested_shapes_source_closure_and_derived_bounds(fixture, kind):
    job = fixture[0]
    if kind == "missing": job["optimisation"].pop("learningRate")
    elif kind == "extra": job["architecture"]["convBlocks"][0]["groups"] = 1
    elif kind == "closure": job["identity"]["codeClosureSha256"] = "0"*64
    elif kind == "input-pin": job["identity"]["inputRecordsSha256"] = "0"*64
    elif kind == "seed": job["optimisation"]["seeds"]["numpy"] = 2**32
    elif kind == "conv": job["architecture"]["convBlocks"][0]["kernel"] = [99, 99]
    elif kind == "float32": job["architecture"]["initialization"]["high"] = 1e100
    elif kind == "tensor-bound": job["environments"]["limits"]["tensorElements"] = 1
    elif kind == "raw-bound": job["environments"]["limits"]["rawFrameBytes"] = 63
    elif kind == "threshold": job["verification"]["occupancyThreshold"]["comparison"] = "strict-greater"
    with pytest.raises(ValueError):
        T.TrainingJob.from_bytes(canonical(job), max_record_bytes=1_000_000)


@pytest.mark.parametrize("key,value", [("obstacle", 1), ("inCorridor", "false"), ("visible", None), ("distanceM", None),
                                       ("distanceM", "10"), ("distanceBin", "unknown"), ("distanceBin", "no-obstacle"),
                                       ("simElapsedNs", 1001), ("frame", True)])
def test_rehashing_malformed_labels_does_not_bypass_consumed_semantics(fixture, key, value):
    fixture[4]["fit"][0][key] = value
    rehash(fixture)
    with pytest.raises(ValueError):
        admit(fixture)


@pytest.mark.parametrize("kind", ["extra", "missing", "duplicate", "unknown", "observer-line", "observer-digest", "absent-distance", "coherence"])
def test_label_structure_source_line_and_declared_target_form_are_checked(fixture, kind):
    label = fixture[4]["fit"][0]
    if kind == "extra": label["ignored"] = True
    elif kind == "missing": label.pop("visible")
    elif kind == "duplicate": fixture[4]["fit"].append(copy.deepcopy(label))
    elif kind == "unknown": label["frame"] = 999
    elif kind == "observer-line": label["provenance"]["observerLine"] += 1
    elif kind == "observer-digest": label["provenance"]["observerSha256"] = "a"*64
    elif kind == "absent-distance": fixture[4]["selection"][0]["distanceM"] = 1.0
    elif kind == "coherence": label["obstacle"] = False
    rehash(fixture)
    with pytest.raises(ValueError):
        admit(fixture)


@pytest.mark.parametrize("source", ["scenario", "observer", "runParams", "labels"])
def test_actual_supplied_source_bytes_are_verified(fixture, source):
    path = Path(fixture[1]["runs"]["fit"][source])
    path.write_bytes(path.read_bytes()+b" ") if source != "labels" else path.write_bytes(b"[]")
    with pytest.raises(ValueError):
        admit(fixture)


@pytest.mark.parametrize("kind", ["target-status", "duplicate-frame", "time"])
def test_even_rebound_observer_source_identity_must_match_consumed_line_status_and_time(fixture, kind):
    job, locations, manifest, index, labels = fixture
    path = Path(locations["runs"]["fit"]["observer"])
    lines = [json.loads(line) for line in path.read_bytes().splitlines()]
    ordinary = next(line for line in lines if "roles" in line and "frame" in line)
    if kind == "target-status": ordinary["roles"]["xverse-lite-target"] = {"status": "absent"}
    elif kind == "duplicate-frame": lines.insert(-1, copy.deepcopy(ordinary))
    else: ordinary["simElapsedNs"] += 1
    data = b"\n".join(canonical(line) for line in lines) + b"\n"
    path.write_bytes(data)
    pin = sha(data)
    next(run for run in manifest["runs"] if run["runId"] == "fit")["observerSha256"] = pin
    next(run for run in index["runs"] if run["runId"] == "fit")["observerSha256"] = pin
    for label in labels["fit"]:
        label["provenance"]["observerSha256"] = pin
    rehash(fixture)
    with pytest.raises(ValueError):
        admit(fixture)


@pytest.mark.parametrize("kind", ["fit-overlap", "missing-training", "fit-seed", "P4-overlap", "pilot-seed", "test-category", "evaluation-set", "coverage", "source-index", "locators"])
def test_partitions_p4_sources_and_explicit_coverage_are_enforced(fixture, kind):
    job, locations, manifest, index, _ = fixture
    if kind == "fit-overlap": job["trainingPartition"]["selection"] = ["fit"]
    elif kind == "missing-training": job["trainingPartition"]["selection"] = ["invented"]
    elif kind == "fit-seed": next(run for run in manifest["runs"] if run["runId"] == "selection")["seed"] = 10
    elif kind == "P4-overlap": job["separation"]["record"]["categories"]["pilot"] = [10]
    elif kind == "pilot-seed": next(run for run in manifest["runs"] if run["runId"] == "fit")["seed"] = 40
    elif kind == "test-category": next(run for run in manifest["runs"] if run["runId"] == "test")["seed"] = 10
    elif kind == "evaluation-set": manifest["evaluation"]["segmentSections"][0]["roadId"] = 999
    elif kind == "coverage": job["verification"]["coverage"]["fit"]["classes"]["overlap"] = 1
    elif kind == "source-index": index["runs"][0]["observerSha256"] = "0"*64
    elif kind == "locators": locations["runs"]["fit"]["ignored"] = "/tmp/TEST-ONLY"
    if kind == "P4-overlap":
        job["separation"]["sha256"] = record_digest(job["separation"]["record"])
    rehash(fixture)
    with pytest.raises(ValueError):
        admit(fixture)


def test_whole_training_run_touching_a_protected_section_is_refused_away_from_evaluation_spawn(fixture):
    run = next(run for run in fixture[2]["runs"] if run["runId"] == "fit")
    assert run["spawnPoint"] == 7
    run["traversedSections"] = copy.deepcopy(fixture[2]["evaluation"]["segmentSections"])
    rehash(fixture)
    with pytest.raises(ValueError, match="as a whole"):
        admit(fixture)


def test_test_section_overlap_remains_a_report_and_is_not_refused(fixture):
    run = next(run for run in fixture[2]["runs"] if run["runId"] == "test")
    run["traversedSections"] = copy.deepcopy(fixture[2]["evaluation"]["segmentSections"])
    rehash(fixture)
    assert any("test run traverses evaluation" in value for value in admit(fixture).report()["manifestReports"])


@pytest.mark.parametrize("kind", ["truncated", "trailing", "concatenated", "bomb", "short", "wrong-digest", "compressed-bound", "missing", "symlink"])
def test_read_only_bounded_zlib_verification_refuses_invalid_stored_frames(fixture, kind, tmp_path):
    _, paths, _, _, labels = fixture
    digest_value = labels["fit"][0]["rawSha256"]
    path = Path(paths["runs"]["fit"]["store"]) / digest_value[:2] / (digest_value+".zlib")
    packed = path.read_bytes()
    if kind == "truncated": path.write_bytes(packed[:-1])
    elif kind == "trailing": path.write_bytes(packed+b"x")
    elif kind == "concatenated": path.write_bytes(packed+packed)
    elif kind == "bomb": path.write_bytes(zlib.compress(b"x"*100_000))
    elif kind == "short": path.write_bytes(zlib.compress(b"x"))
    elif kind == "wrong-digest": path.write_bytes(zlib.compress(b"x"*64))
    elif kind == "compressed-bound": fixture[0]["environments"]["limits"]["compressedFrameBytes"] = len(packed)-1
    elif kind == "missing": path.unlink()
    elif kind == "symlink":
        target = tmp_path / "TEST-ONLY-target"; target.write_bytes(packed); path.unlink(); path.symlink_to(target)
    with pytest.raises((ValueError, OSError)):
        admit(fixture)


def test_every_iteration_rechecks_frames_and_never_sweeps_temporaries_or_mutates_admitted_metadata(fixture):
    dataset = admit(fixture)
    root = Path(fixture[1]["runs"]["fit"]["store"])
    label = fixture[4]["fit"][0]
    path = root / label["rawSha256"][:2] / (label["rawSha256"]+".zlib")
    temporary = path.parent / ".tmp-TEST-ONLY.zlib"; temporary.write_bytes(b"writer in flight")
    sample = next(dataset.iter_samples("fit")); sample["label"]["obstacle"] = "mutated"
    fixture[4]["fit"][0]["obstacle"] = "caller changed"
    assert next(dataset.iter_samples("fit"))["label"]["obstacle"] is True
    assert temporary.read_bytes() == b"writer in flight"
    path.write_bytes(path.read_bytes()+b"changed")
    with pytest.raises(ValueError):
        next(dataset.iter_samples("fit"))


def test_bounded_regular_source_reads_refuse_fifo_without_waiting(tmp_path):
    import os
    path = tmp_path / "TEST-ONLY-fifo"
    os.mkfifo(path)
    with pytest.raises(ValueError, match="regular"):
        read_regular(path, 100)


def test_runtime_never_imports_training_modules():
    root = Path(__file__).resolve().parents[1] / "assured_aeb"
    offline = {"training_record", "training_io", "dataset_consumer"}
    for path in root.rglob("*.py"):
        if "perception" in path.relative_to(root).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import): names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom): names = [node.module or "", *(alias.name for alias in node.names)]
            else: continue
            assert not any(offline.intersection(name.split(".")) for name in names), path


@pytest.mark.parametrize("source,keys,value", [("labelParams", ("camera", "width"), 4.0),
    ("frameFormat", ("width",), 4.0), ("separation", ("categories", "training"), [10.0, 11.0]),
    ("labelParams", ("camera", "mountM"), [1.5, 0, 2.4])])
def test_actual_source_canonical_pin_refuses_python_equal_numeric_reencoding(fixture, source, keys, value):
    path = Path(fixture[1][source]); original = json.loads(path.read_bytes()); changed = copy.deepcopy(original)
    target = changed
    for key in keys[:-1]: target = target[key]
    target[keys[-1]] = value
    assert changed == original and record_digest(changed) != record_digest(original)
    admitted_job_digest = record_digest(fixture[0])
    path.write_bytes(canonical(changed))
    with pytest.raises(ValueError, match="actual canonical source digest mismatch"):
        admit(fixture)
    assert record_digest(fixture[0]) == admitted_job_digest  # never rewrite the expected pins


def test_actual_canonical_record_identity_preserves_whitespace_key_order_and_genuine_types(fixture):
    for source in ("labelParams", "frameFormat", "separation"):
        path = Path(fixture[1][source]); value = dict(reversed(list(json.loads(path.read_bytes()).items())))
        path.write_bytes(json.dumps(value, indent=2, sort_keys=False).encode())
    assert admit(fixture).report()["counts"]["fit"]["classes"]["bin-0"] == 1
    actual = copy.deepcopy(fixture[0]["dataset"]["frameFormat"]); actual["width"] = 4.0
    with pytest.raises(ValueError): T.validate_frame_format(actual)
    actual = copy.deepcopy(fixture[0]["separation"]["record"]); actual["categories"]["training"] = [10.0, 11.0]
    with pytest.raises(ValueError): T.validate_separation(actual)


def test_parameter_dominated_model_cannot_fit_under_a_smaller_admitted_memory_budget(fixture):
    job = fixture[0]
    job["architecture"]["convBlocks"] = [{"outChannels": 1, "kernel": [99, 99], "stride": [1, 1],
                                          "padding": [49, 49], "dilation": [1, 1], "bias": True}]
    job["environments"]["limits"].update(modelParameters=100_000, memoryBytes=50_000)
    # All old parameter/output/activation checks pass: 29416 weights need 117664 bytes, already too many.
    with pytest.raises(ValueError, match="necessary resident float32"):
        T.TrainingJob.from_bytes(canonical(job), max_record_bytes=1_000_000)
    with pytest.raises(ValueError, match="necessary resident float32"):
        admit(fixture)


@pytest.mark.parametrize("momentum,nesterov", [(0.0, False), (0.9, False), (0.9, True)])
def test_necessary_memory_ledger_uses_exact_weights_gradients_and_explicit_sgd_state(fixture, momentum, nesterov):
    record = fixture[0]; record["optimisation"].update(momentum=momentum, nesterov=nesterov)
    job = T.TrainingJob.from_bytes(canonical(record), max_record_bytes=1_000_000)
    ledger = job.memory_ledger
    assert ledger["trainableParameters"] == 26
    assert ledger["dtype"] == "float32" and ledger["bytesPerElement"] == 4
    assert ledger["weightBytes"] == ledger["gradientBytes"] == 104
    assert ledger["momentumBytes"] == (104 if momentum else 0)
    assert ledger["maximumBatchActivationBytes"] == 96
    expected = 208 + (104 if momentum else 0)
    assert ledger["necessaryMemoryBytes"] == expected
    record["environments"]["limits"]["memoryBytes"] = expected
    assert T.TrainingJob.from_bytes(canonical(record), max_record_bytes=1_000_000).memory_ledger == ledger
    record["environments"]["limits"]["memoryBytes"] = expected - 1
    with pytest.raises(ValueError, match="necessary resident float32"):
        T.TrainingJob.from_bytes(canonical(record), max_record_bytes=1_000_000)
    ledger["weightBytes"] = 0
    assert job.memory_ledger["weightBytes"] == 104


def test_two_head_output_storage_can_dominate_maximum_batch_activation(fixture):
    record = fixture[0]
    params = record["dataset"]["labelParams"]; params["distanceBinEdgesM"] = list(range(1, 21))
    record["dataset"]["labelParamsSha256"] = record_digest(params)
    record["preprocessing"]["record"]["resize"].update(width=1, height=1)
    record["preprocessing"]["sha256"] = record_digest(record["preprocessing"]["record"])
    record["architecture"]["convBlocks"][0]["outChannels"] = 1
    record["optimisation"]["batchSize"] = 100
    record["environments"]["limits"].update(batchSize=100, tensorElements=100_000)
    classes = ["no-obstacle", "overlap", *(f"bin-{i}" for i in range(20)), "beyond"]
    for coverage in record["verification"]["coverage"].values(): coverage["classes"] = dict.fromkeys(classes, 0)
    refresh_job(record)
    job = T.TrainingJob.from_bytes(canonical(record), max_record_bytes=1_000_000)
    assert job.parameter_count == 52
    assert job.memory_ledger["maximumBatchActivationBytes"] == 100 * (1 + len(classes)) * 4
    assert job.memory_ledger["necessaryMemoryBytes"] == 208 + 9600


def _small_frame_store(tmp_path):
    root = tmp_path / "store"; root.mkdir()
    raw = b"TEST-ONLY-frame!" * 4
    identity = sha(raw); shard = root / identity[:2]; shard.mkdir()
    path = shard / (identity + ".zlib"); path.write_bytes(zlib.compress(raw))
    return root, raw, identity, shard, path


@pytest.mark.parametrize("swap", ["before-shard-open", "after-shard-open", "after-root-open"])
def test_descriptor_anchoring_refuses_or_survives_deterministic_directory_substitution(tmp_path, monkeypatch, swap):
    import os
    root, raw, identity, shard, path = _small_frame_store(tmp_path)
    outside = tmp_path / "outside"; outside.mkdir()
    (outside / (identity + ".zlib")).write_bytes(b"must never be read via replacement shard")
    outside_shard = outside / identity[:2]; outside_shard.mkdir()
    (outside_shard / (identity + ".zlib")).write_bytes(b"must never be read via replacement root")
    original_open = os.open; changed = []
    def hooked(name, flags, *args, **kwargs):
        assert flags & os.O_NOFOLLOW and flags & os.O_CLOEXEC
        assert flags & os.O_ACCMODE == os.O_RDONLY and not flags & (os.O_CREAT | os.O_TRUNC)
        is_shard = str(name) == identity[:2] and flags & os.O_DIRECTORY
        is_root = str(name) == root.name and flags & os.O_DIRECTORY
        if swap == "before-shard-open" and is_shard and not changed:
            shard.rename(root / "retired"); shard.symlink_to(outside, target_is_directory=True); changed.append(True)
        fd = original_open(name, flags, *args, **kwargs)
        assert not os.get_inheritable(fd)
        if not changed and ((swap == "after-shard-open" and is_shard) or (swap == "after-root-open" and is_root)):
            if is_shard:
                shard.rename(root / "retired"); shard.symlink_to(outside, target_is_directory=True)
            else:
                root.rename(tmp_path / "retired-root"); root.symlink_to(outside, target_is_directory=True)
            changed.append(True)
        return fd
    monkeypatch.setattr(os, "open", hooked)
    if swap == "before-shard-open":
        with pytest.raises(OSError): read_frame(root, identity, expected_bytes=len(raw), compressed_limit=1024, raw_limit=len(raw))
    else:
        assert read_frame(root, identity, expected_bytes=len(raw), compressed_limit=1024, raw_limit=len(raw)) == raw
    assert changed


@pytest.mark.parametrize("scope", ["root", "ancestor", "shard", "file"])
def test_all_frame_directory_components_and_final_files_refuse_symlinks(tmp_path, scope):
    root, raw, identity, shard, path = _small_frame_store(tmp_path)
    if scope == "root":
        root.rename(tmp_path / "real-store"); root.symlink_to(tmp_path / "real-store", target_is_directory=True)
    elif scope == "ancestor":
        alias = tmp_path / "alias"; alias.symlink_to(tmp_path, target_is_directory=True); root = alias / root.name
    elif scope == "shard":
        shard.rename(root / "real-shard"); shard.symlink_to(root / "real-shard", target_is_directory=True)
    else:
        target = tmp_path / "real-frame"; path.rename(target); path.symlink_to(target)
    with pytest.raises(OSError): read_frame(root, identity, expected_bytes=len(raw), compressed_limit=1024, raw_limit=len(raw))


@pytest.mark.parametrize("failure", ["none", "content", "missing", "interrupted", "fifo"])
def test_frame_descriptor_scope_is_read_only_noninheritable_and_always_closed(tmp_path, monkeypatch, failure):
    import os
    root, raw, identity, shard, path = _small_frame_store(tmp_path)
    if failure == "content": path.write_bytes(b"invalid-zlib")
    if failure in ("missing", "fifo"):
        path.unlink()
        if failure == "fifo": os.mkfifo(path)
    original_open = os.open; opened = []
    def tracked(name, flags, *args, **kwargs):
        assert flags & os.O_NOFOLLOW and flags & os.O_CLOEXEC
        assert flags & os.O_ACCMODE == os.O_RDONLY and not flags & (os.O_CREAT | os.O_TRUNC)
        fd = original_open(name, flags, *args, **kwargs); opened.append(fd)
        assert not os.get_inheritable(fd)
        return fd
    monkeypatch.setattr(os, "open", tracked)
    if failure == "interrupted":
        def interrupted(fd, maximum): raise KeyboardInterrupt("TEST-ONLY read interruption")
        monkeypatch.setattr(IO, "_read_descriptor", interrupted)
    if failure == "none":
        assert read_frame(root, identity, expected_bytes=len(raw), compressed_limit=1024, raw_limit=len(raw)) == raw
    else:
        with pytest.raises((ValueError, OSError, KeyboardInterrupt)):
            read_frame(root, identity, expected_bytes=len(raw), compressed_limit=1024, raw_limit=len(raw))
    assert opened
    for fd in set(opened):
        with pytest.raises(OSError): os.fstat(fd)
