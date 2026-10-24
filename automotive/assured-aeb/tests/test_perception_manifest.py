"""Offline tests of the WP-09 dataset manifest and its split rule (P-2, P-4; review-wp09-labels finding 4).

Seeds, ids, maps, road and section ids are TEST VALUES. The evaluation segment of spawn point 1 is a declared
parameter (P-2 map verification, TODO: engineering verification).
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from assured_aeb.perception import labels as L
from assured_aeb.perception import manifest as M
from assured_aeb.perception import scenario as S

EVALUATION_SEEDS = [9001, 9002]  # test values standing in for the P-4 evaluation list (TODO)
MAP = "Town10HD_Opt"
EVALUATION_SEGMENT = {"map": MAP, "roadId": 40, "sectionId": 0}  # test value (TODO: engineering verification)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def scenario_bytes(spawn, placement):
    record = {"schema": S.SCHEMA_2, "egoBlueprint": "vehicle.test", "spawnPointIndex": spawn, "map": MAP}
    if placement["kind"] != "none":
        record["target"] = {"blueprint": "vehicle.test", "roleName": "xverse-lite-target", "distanceAheadM": 30.0,
                            "hold": "brake-and-hand-brake"}
        if placement["kind"] == "adjacent-lane":
            record["target"]["adjacentLane"] = {"side": placement["side"], "direction": placement["direction"]}
    return json.dumps(record, sort_keys=True).encode()


class Fixture:
    def __init__(self, root):
        self.root, self.files = root, {}

    def run(self, run_id, seed, split, *, spawn=7, segment=None, frames=2, placement=None):
        placement = placement or {"kind": "ego-lane"}
        data = scenario_bytes(spawn, placement)
        path = self.root / f"{run_id}.json"
        path.write_bytes(data)
        self.files[run_id] = path
        return {"runId": run_id, "seed": seed, "spawnPoint": spawn,
                "segment": segment or {"map": MAP, "roadId": 7, "sectionId": 0}, "split": split,
                "scenarioSha256": hashlib.sha256(data).hexdigest(), "targetPlacement": placement,
                "runParamsSha256": digest("params"), "observerSha256": digest(run_id), "labelsSha256": digest(f"labels-{run_id}"),
                "frames": [{"frame": k, "simElapsedNs": k * 50_000_000, "rawSha256": digest(f"{run_id}-{k}")} for k in range(frames)]}


def manifest(runs, *, code=None):
    return M.build_manifest(digest("label-params"), code or digest("label-code"), EVALUATION_SEEDS, EVALUATION_SEGMENT, runs)


@pytest.fixture
def fx(tmp_path):
    return Fixture(tmp_path)


def good(fx):
    return manifest([fx.run("r1", 11, "training"),
                     fx.run("r2", 12, "calibration", segment={"map": MAP, "roadId": 8, "sectionId": 0}),
                     fx.run("r3", 13, "test", segment={"map": MAP, "roadId": 9, "sectionId": 1},
                            placement={"kind": "adjacent-lane", "side": "left", "direction": "opposite"})])


def test_good_manifest_is_admissible_and_its_digest_is_the_identity(fx):
    m = good(fx)
    assert M.check_manifest(m, fx.files) == ([], [])
    assert M.manifest_digest(m) == M.manifest_digest(json.loads(json.dumps(m))) == hashlib.sha256(M.canonical(m)).hexdigest()
    changed = copy.deepcopy(m)
    changed["runs"][0]["frames"][0]["rawSha256"] = digest("other")
    assert M.manifest_digest(changed) != M.manifest_digest(m)


@pytest.mark.parametrize("mutate, word", [
    (lambda m: m["runs"][0].update(spawnPoint=1), "spawn point 1"),
    (lambda m: m["runs"][0].update(seed=9001), "evaluation seed"),
    (lambda m: m["runs"][1].update(seed=11), "both training and calibration"),
    (lambda m: m["runs"][1]["frames"].append(dict(m["runs"][0]["frames"][0])), "also appears in run r1"),
    (lambda m: m["runs"].append(dict(m["runs"][0], seed=14)), "duplicate run id"),
    (lambda m: m["runs"][0].update(split="validation"), "split must be one of"),
    (lambda m: m["runs"][0].pop("segment"), "run members"),
    (lambda m: m["runs"][0].update(segment="seg-a"), "segment must be exactly"),
    (lambda m: m["runs"][0]["frames"][0].update(split="training"), "frame entries"),
    (lambda m: m["runs"][0].update(observerSha256="x"), "observerSha256"),
    (lambda m: m["runs"][0].update(labelsSha256="x"), "labelsSha256"),
    (lambda m: m.update(labelCodeSha256="x"), "labelCodeSha256"),
    (lambda m: m["evaluation"].update(seeds=[]), "evaluation must be"),
    (lambda m: m["evaluation"].update(spawnPoint=2), "evaluation must be"),
    (lambda m: m["evaluation"].pop("segment"), "evaluation must be"),
    (lambda m: m["evaluation"].update(segment={"map": MAP, "roadId": "40", "sectionId": 0}), "evaluation must be"),
])
def test_manifest_refusals(fx, mutate, word):
    m = good(fx)
    mutate(m)
    refusals, _ = M.check_manifest(m, fx.files)
    assert any(word in r for r in refusals), refusals


# ---- MEDIUM-3: P-2 by segment ---------------------------------------------------------------------------------

@pytest.mark.parametrize("split", ["training", "calibration"])
def test_spawn_point_2_on_the_evaluation_segment_is_refused(fx, split):
    m = manifest([fx.run("r1", 11, split, spawn=2, segment=dict(EVALUATION_SEGMENT))])
    refusals, _ = M.check_manifest(m, fx.files)
    assert any("evaluation segment" in r and "spawn point 2" in r for r in refusals), refusals


def test_test_split_on_the_evaluation_segment_is_reported_not_refused(fx):
    m = manifest([fx.run("r1", 11, "test", spawn=2, segment=dict(EVALUATION_SEGMENT))])
    refusals, reports = M.check_manifest(m, fx.files)
    assert refusals == [] and any("evaluation segment" in r for r in reports)


def test_other_section_of_the_evaluation_road_is_admitted(fx):
    m = manifest([fx.run("r1", 11, "training", spawn=2, segment={"map": MAP, "roadId": 40, "sectionId": 1})])
    assert M.check_manifest(m, fx.files) == ([], [])


# ---- MEDIUM-2: scenario verified, placement recorded ------------------------------------------------------------

def test_scenarios_are_required(fx):
    assert M.check_manifest(good(fx), None)[0]
    files = dict(fx.files)
    files.pop("r2")
    assert any("r2: no scenario file" in r for r in M.check_manifest(good(fx), files)[0])


def test_scenario_digest_mismatch_is_refused(fx):
    m = good(fx)
    fx.files["r1"].write_bytes(fx.files["r1"].read_bytes() + b" ")
    assert any("r1: scenario refused" in r and "scenarioSha256" in r for r in M.check_manifest(m, fx.files)[0])


def test_recorded_placement_must_match_the_verified_scenario(fx):
    m = good(fx)
    m["runs"][2]["targetPlacement"] = {"kind": "ego-lane"}
    assert any("r3: recorded targetPlacement" in r for r in M.check_manifest(m, fx.files)[0])
    m["runs"][2]["targetPlacement"] = {"kind": "adjacent-lane", "side": "up", "direction": "opposite"}
    assert any("r3: targetPlacement must be" in r for r in M.check_manifest(m, fx.files)[0])


def test_scenario_spawn_point_and_map_must_match_the_run(fx):
    m = good(fx)
    m["runs"][0]["spawnPoint"] = 8
    m["runs"][1]["segment"] = {"map": "Town01", "roadId": 8, "sectionId": 0}
    refusals = M.check_manifest(m, fx.files)[0]
    assert any("r1: scenario spawnPointIndex 7" in r for r in refusals)
    assert any("r2: scenario map" in r for r in refusals)


def test_schema_1_scenario_without_a_map_is_refused(fx):
    m = good(fx)
    data = json.dumps({"schema": S.SCHEMA_1, "egoBlueprint": "vehicle.test", "spawnPointIndex": 7}).encode()
    fx.files["r1"].write_bytes(data)
    m["runs"][0].update(scenarioSha256=hashlib.sha256(data).hexdigest(), targetPlacement={"kind": "none"})
    assert any("declares no map" in r for r in M.check_manifest(m, fx.files)[0])


@pytest.mark.parametrize("placement", [{"kind": "none"}, {"kind": "ego-lane"},
                                       {"kind": "adjacent-lane", "side": "right", "direction": "same"}])
def test_placement_is_derived_from_the_verified_scenario(placement):
    data = scenario_bytes(3, placement)
    assert S.verified_scenario(data, hashlib.sha256(data).hexdigest()) == {"spawnPointIndex": 3, "map": MAP,
                                                                           "targetPlacement": placement}


@pytest.mark.parametrize("record", [
    {"schema": "xverse-compat.carla-live-scenario/9", "spawnPointIndex": 3},
    {"schema": S.SCHEMA_1, "spawnPointIndex": 3, "target": {}},
    {"schema": S.SCHEMA_2, "spawnPointIndex": 3, "map": MAP, "target": {"adjacentLane": {"side": "left"}}},
    {"schema": S.SCHEMA_2, "spawnPointIndex": 3, "map": MAP, "target": {"adjacentLane": {"side": "up", "direction": "same"}}},
    {"schema": S.SCHEMA_2, "spawnPointIndex": -1, "map": MAP},
])
def test_malformed_scenarios_are_refused(record):
    data = json.dumps(record).encode()
    with pytest.raises(ValueError):
        S.verified_scenario(data, hashlib.sha256(data).hexdigest())


# ---- MEDIUM-4: the identity binds the labels --------------------------------------------------------------------

def test_label_code_change_changes_the_identity(fx, monkeypatch):
    from test_perception_labels import entry, items, observer, params, scenario as label_scenario

    data = observer([(5, {L.EGO_ROLE: entry(0.0), L.TARGET_ROLE: entry(30.0)})])
    scenario, sha = label_scenario(True)

    def identity():
        labels, _ = L.label_run(data, items([5]), params(), scenario=scenario, scenario_sha256=sha)
        r = fx.run("r1", 11, "training")
        r["labelsSha256"] = L.labels_digest(labels)
        return M.manifest_digest(manifest([r], code=L.LABEL_CODE_SHA256)), r["labelsSha256"]

    before, labels_before = identity()
    monkeypatch.setattr(L, "LABEL_CODE_SHA256", digest("a changed labels.py"))
    after, labels_after = identity()
    assert labels_before != labels_after and before != after


def test_splits_are_by_run_and_frames_carry_no_split(fx):
    assert all("split" not in frame for r in good(fx)["runs"] for frame in r["frames"])


def test_shared_segment_is_reported_not_refused(fx):
    m = manifest([fx.run("r1", 11, "training"), fx.run("r2", 12, "test")])  # both on road 7 section 0
    refusals, reports = M.check_manifest(m, fx.files)
    assert refusals == [] and reports and "7" in reports[0]


def test_manifest_holds_no_pixels_and_no_host_paths(fx):
    m = good(fx)
    text = json.dumps(m)
    assert all(not isinstance(v, (bytes, bytearray)) for v in json.loads(text).values()) and "pixels" not in text
    assert str(fx.root) not in text
