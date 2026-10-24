"""Offline tests of the WP-09 dataset manifest and its split rule (P-2, P-4). Seeds and ids are test values."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from assured_aeb.perception import manifest as M

EVALUATION_SEEDS = [9001, 9002]  # test values standing in for the P-4 evaluation list (TODO)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def run(run_id, seed, split, *, spawn=7, segment="seg-a", frames=2):
    return {"runId": run_id, "seed": seed, "spawnPoint": spawn, "segment": segment, "split": split,
            "scenarioSha256": digest("scenario"), "runParamsSha256": digest("params"), "observerSha256": digest(run_id),
            "frames": [{"frame": k, "simElapsedNs": k * 50_000_000, "rawSha256": digest(f"{run_id}-{k}")} for k in range(frames)]}


def manifest(runs):
    return M.build_manifest(digest("label-params"), EVALUATION_SEEDS, runs)


def good():
    return manifest([run("r1", 11, "training"), run("r2", 12, "calibration", segment="seg-b"), run("r3", 13, "test", segment="seg-c")])


def test_good_manifest_is_admissible_and_its_digest_is_the_identity():
    m = good()
    assert M.check_manifest(m) == ([], [])
    assert M.manifest_digest(m) == M.manifest_digest(json.loads(json.dumps(m))) == hashlib.sha256(M.canonical(m)).hexdigest()
    changed = copy.deepcopy(m)
    changed["runs"][0]["frames"][0]["rawSha256"] = digest("other")
    assert M.manifest_digest(changed) != M.manifest_digest(m)


@pytest.mark.parametrize("mutate, word", [
    (lambda m: m["runs"][0].update(spawnPoint=1), "spawn point 1"),
    (lambda m: m["runs"][0].update(seed=9001), "evaluation seed"),
    (lambda m: m["runs"][1].update(seed=11), "both training and calibration"),
    (lambda m: m["runs"][1]["frames"].append(dict(m["runs"][0]["frames"][0])), "also appears in run r1"),
    (lambda m: m["runs"].append(run("r1", 14, "training")), "duplicate run id"),
    (lambda m: m["runs"][0].update(split="validation"), "split must be one of"),
    (lambda m: m["runs"][0].pop("segment"), "run members"),
    (lambda m: m["runs"][0]["frames"][0].update(split="training"), "frame entries"),
    (lambda m: m["runs"][0].update(observerSha256="x"), "observerSha256"),
    (lambda m: m["evaluation"].update(seeds=[]), "evaluation must be"),
    (lambda m: m["evaluation"].update(spawnPoint=2), "evaluation must be"),
])
def test_manifest_refusals(mutate, word):
    m = good()
    mutate(m)
    refusals, _ = M.check_manifest(m)
    assert any(word in r for r in refusals), refusals


def test_splits_are_by_run_and_frames_carry_no_split():
    assert all("split" not in frame for r in good()["runs"] for frame in r["frames"])


def test_shared_segment_is_reported_not_refused():
    m = manifest([run("r1", 11, "training"), run("r2", 12, "test")])  # both on seg-a
    refusals, reports = M.check_manifest(m)
    assert refusals == [] and reports and "seg-a" in reports[0]


def test_manifest_holds_no_pixels():
    text = json.dumps(good())
    assert all(not isinstance(v, (bytes, bytearray)) for v in json.loads(text).values()) and "pixels" not in text
