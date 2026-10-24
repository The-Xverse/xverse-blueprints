"""Explicit genuine integration driver, NOT executed on collection. Every synthetic numeric value is TEST-ONLY.

Run after coordinator release: python -S -s -B tests/training4b_integration.py --help
This driver is stdlib; each actual framework run is a distinct fresh unshare -rn worker, never ORT.
Identity/lock/interpreter/sites and engineering resource values must be provided; unavailable isolation FAILS.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from assured_aeb.perception import training_record as T, training_worker as W
from assured_aeb.perception.training_io import canonical, sha
from assured_aeb.perception.training_weights import read_weights
from assured_aeb.perception.store import FrameStore
from training4a_fixture import build, refresh_job, rehash


def prepare(root, args, *, mutate_held_out=False, nonfinite_loss=False):
    fixture = build(root)
    record, locations, manifest, _, labels = fixture
    identity = json.loads(Path(args.identity).read_bytes())
    record["environments"]["training"] = {"identitySha256": sha(Path(args.identity).read_bytes()), "lockSha256": sha(Path(args.lock).read_bytes()),
                                              "sourceRevision": identity["lock"]["repositoryRevision"], "python": args.python,
                                              "sites": [identity["sitePackages"]]}
    limits = record["environments"]["limits"]
    limits.update(memoryBytes=args.memory_bytes, diskBytes=args.disk_bytes, workerTimeoutS=args.timeout)
    if mutate_held_out:
        for run in manifest["runs"]:
            if run["split"] not in ("calibration", "test"):
                continue
            rid = run["runId"]
            store = FrameStore(Path(locations["runs"][rid]["store"]), free_space_floor_bytes=0, compression_level=1, frame_length=64, writable=True)
            for index, frame in enumerate(run["frames"]):
                raw = bytes([170 + index + (10 if run["split"] == "test" else 0)]) * 64
                old = frame["rawSha256"]
                frame["rawSha256"] = sha(raw)
                store.put(raw, frame["rawSha256"])
                for label in labels[rid]:
                    if label["rawSha256"] == old: label["rawSha256"] = frame["rawSha256"]
        rehash(fixture)
    if nonfinite_loss:
        record["optimisation"]["lossWeights"]["occupancy"] = 1e308  # TEST-ONLY finite input provoking float32 failure
    refresh_job(record)
    job_bytes, locations_bytes = canonical(record), canonical(locations)
    job = T.TrainingJob.from_bytes(job_bytes, max_record_bytes=1_000_000)
    stage = canonical({"schema": W.STAGE_SCHEMA, "jobSha256": job.sha256, "sourceClosureSha256": W.code_digest()})
    for name, data in (("job.json", job_bytes), ("locations.json", locations_bytes), ("stage.json", stage)):
        (root / name).write_bytes(data)
    return job, stage


def run(root, output, args, *, expect_success=True):
    # The driver is the genuine parent seen by unshare's exec worker. Never synthesize a namespace number.
    parent = os.readlink("/proc/self/ns/net")
    site = json.loads(Path(args.identity).read_bytes())["sitePackages"]
    source = Path(__file__).resolve().parents[1]
    compat_source = Path(args.compat_source).resolve()
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent-training4b-home", "TMPDIR": str(args.scratch),
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": os.pathsep.join((site, str(source), str(compat_source))),
           "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
           "XDG_CACHE_HOME": str(args.scratch / "cache"), "TORCH_HOME": str(args.scratch / "cache/torch"),
           "TORCHINDUCTOR_CACHE_DIR": str(args.scratch / "cache/inductor"), "TRITON_CACHE_DIR": str(args.scratch / "cache/triton")}
    command = ["unshare", "-rn", args.python, "-S", "-s", "-B", "-m", "assured_aeb.perception.training_worker",
               "--job", str(root / "job.json"), "--locations", str(root / "locations.json"), "--stage", str(root / "stage.json"),
               "--identity", args.identity, "--lock", args.lock, "--parent-netns", parent, "--output", str(output), "--max-record-bytes", "1000000"]
    completed = subprocess.run(command, env=env, cwd=source, capture_output=True, text=True, timeout=args.timeout)
    (root / "worker.stdout").write_text(completed.stdout)
    (root / "worker.stderr").write_text(completed.stderr)
    if not expect_success:
        assert completed.returncode != 0 and not output.exists(), "nonfinite training must refuse without output"
        assert "nonfinite" in completed.stderr or "overflow" in completed.stderr, completed.stderr[-3000:]
        return None
    assert completed.returncode == 0, f"worker failed {completed.returncode}: {completed.stderr[-3000:]}"
    return json.loads((output / "training-report.json").read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("identity", "lock", "python", "compat-source", "scratch"):
        parser.add_argument("--" + key, required=True)
    for key in ("memory-bytes", "disk-bytes", "timeout"):
        parser.add_argument("--" + key, required=True, type=int)
    args = parser.parse_args()
    args.scratch = Path(args.scratch).resolve()
    args.scratch.mkdir(parents=False, exist_ok=False)
    # Includes4a's temporary scenario snapshots. The caller must locate scratch on admitted external storage.
    os.environ["TMPDIR"] = str(args.scratch)
    for relative in ("cache", "cache/torch", "cache/inductor", "cache/triton"):
        (args.scratch / relative).mkdir(exist_ok=False)
    jobs, reports = [], []
    for index in range(3):
        root = args.scratch / f"case-{index}"
        job, stage = prepare(root, args, mutate_held_out=index == 2)
        output = root / "trained"
        report = run(root, output, args)
        decoded = read_weights(output, job, stage_sha256=sha(stage), descriptor_sha256=report["weightDescriptorSha256"], weights_sha256=report["weightsSha256"])
        assert decoded["occupancy_head.weight"]["shape"] == (1, 2)
        assert decoded["bin_head.weight"]["shape"] == (5, 2)
        assert decoded["features.conv_0.weight"]["shape"] == (2, 3, 1, 1)
        assert report["updates"] == 4 and report["initialNamedWeightsSha256"] != report["selectedNamedWeightsSha256"]
        expected = min((row["selectionMeanLoss"], row["epoch"]) for row in report["epochs"] if row["selectionMeanLoss"] is not None)
        assert (report["selectedLoss"], report["selectedEpoch"]) == expected
        assert report["classOrder"] == ["no-obstacle", "overlap", "bin-0", "bin-1", "beyond"] == list(job.class_order) and report["state"] == "trained-development-only"
        jobs.append(job)
        reports.append(report)
    # Same immutable identities/data in distinct location roots cannot introduce paths into deterministic bytes.
    assert jobs[0].sha256 == jobs[1].sha256 and reports[0] == reports[1]
    for name in ("weights.f32", "weights.json", "training-report.json"):
        assert (args.scratch / "case-0/trained" / name).read_bytes() == (args.scratch / "case-1/trained" / name).read_bytes()
    # Rebinding genuinely changed calibration/test pixels affects job/report identities, never fit/checkpoint weights.
    assert jobs[0].sha256 != jobs[2].sha256
    for key in ("sampleOrderSha256", "selectedNamedWeightsSha256", "weightsSha256", "selectedEpoch", "selectedLoss", "epochs"):
        assert reports[0][key] == reports[2][key], key
    negative = args.scratch / "nonfinite-loss"
    prepare(negative, args, nonfinite_loss=True)
    run(negative, negative / "must-not-exist", args, expect_success=False)
    print(canonical({"state": "TEST-ONLY-training4b-verified", "successfulCases": 3, "nonfiniteRefusals": 1, "jobSha256": jobs[0].sha256,
                     "stageSourceClosureSha256": W.code_digest(), "weightsSha256": reports[0]["weightsSha256"]}).decode())


if __name__ == "__main__":
    main()
