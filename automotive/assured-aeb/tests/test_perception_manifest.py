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
from test_perception_labels import entry, observer, params

EVALUATION_SEEDS = [9001, 9002]  # test values standing in for the P-4 evaluation list (TODO)
MAP = "Town10HD_Opt"
EVALUATION_SEGMENT = {"map": MAP, "roadId": 40, "sectionId": 0}  # TEST-ONLY section (not a live map observation)
EVALUATION_SECTIONS = [EVALUATION_SEGMENT]
TEST_SPAWN_POINT, TEST_ALTERNATE_SPAWN_POINT = 7, 3
TEST_BLUEPRINT = "vehicle.test"
TEST_TARGET_DISTANCE_M, TEST_TARGET_HOLD = 30.0, "brake-and-hand-brake"



def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def scenario_bytes(spawn, placement):
    record = {"schema": S.SCHEMA_2, "egoBlueprint": TEST_BLUEPRINT, "spawnPointIndex": spawn, "map": MAP}
    if placement["kind"] != "none":
        record["target"] = {"blueprint": TEST_BLUEPRINT, "roleName": "xverse-lite-target", "distanceAheadM": TEST_TARGET_DISTANCE_M,
                            "hold": TEST_TARGET_HOLD}
        if placement["kind"] == "adjacent-lane":
            record["target"]["adjacentLane"] = {"side": placement["side"], "direction": placement["direction"]}
    return json.dumps(record, sort_keys=True).encode()


class Fixture:
    def __init__(self, root):
        self.root, self.files, self.labels = root, {}, {}

    def run(self, run_id, seed, split, *, spawn=TEST_SPAWN_POINT, segment=None, sections=None, frames=2, placement=None):
        placement = placement or {"kind": "ego-lane"}
        data = scenario_bytes(spawn, placement)
        path = self.root / f"{run_id}.json"
        path.write_bytes(data)
        self.files[run_id] = path
        frame_records = [{"frame": k, "rawSha256": digest(f"{run_id}-{k}")} for k in range(frames)]
        target = placement["kind"] != "none"
        roles = {L.EGO_ROLE: entry(0.0)}
        if target:
            roles[L.TARGET_ROLE] = entry(TEST_TARGET_DISTANCE_M, 4.0 if placement["kind"] == "adjacent-lane" else 0.0)
        source = observer([(k, roles) for k in range(frames)], target=target)
        labels, excluded = L.label_run(source, frame_records, params(), scenario=data,
                                      scenario_sha256=hashlib.sha256(data).hexdigest())
        assert not excluded and len(labels) == frames
        self.labels[run_id] = labels
        return {"runId": run_id, "seed": seed, "spawnPoint": spawn,
                "traversedSections": sections if sections is not None else [segment or {"map": MAP, "roadId": 7, "sectionId": 0}],
                "split": split, "scenarioSha256": hashlib.sha256(data).hexdigest(), "targetPlacement": placement,
                "runParamsSha256": digest("params"), "observerSha256": hashlib.sha256(source).hexdigest(),
                "labelsSha256": L.labels_digest(labels),
                "frames": [{k: label[k] for k in M.FRAME_MEMBERS} for label in labels]}


def manifest(runs, *, code=None):
    return M.build_manifest(params().digest, code or L.LABEL_CODE_SHA256, EVALUATION_SEEDS, EVALUATION_SECTIONS, runs)


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
    assert M.check_manifest(m, fx.files, fx.labels) == ([], [])
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
    (lambda m: m["runs"][0].pop("traversedSections"), "run members"),
    (lambda m: m["runs"][0].update(traversedSections="seg-a"), "traversedSections must be"),
    (lambda m: m["runs"][0]["frames"][0].update(split="training"), "frame entries"),
    (lambda m: m["runs"][0].update(observerSha256="x"), "observerSha256"),
    (lambda m: m["runs"][0].update(labelsSha256="x"), "labelsSha256"),
    (lambda m: m.update(labelCodeSha256="x"), "labelCodeSha256"),
    (lambda m: m["evaluation"].update(seeds=[]), "evaluation must be"),
    (lambda m: m["evaluation"].update(spawnPoint=2), "evaluation must be"),
    (lambda m: m["evaluation"].pop("segmentSections"), "evaluation must be"),
    (lambda m: m["evaluation"].update(segmentSections=[{"map": MAP, "roadId": "40", "sectionId": 0}]), "evaluation must be"),
])
def test_manifest_refusals(fx, mutate, word):
    m = good(fx)
    mutate(m)
    refusals, _ = M.check_manifest(m, fx.files, fx.labels)
    assert any(word in r for r in refusals), refusals


# ---- MEDIUM-3: P-2 by segment ---------------------------------------------------------------------------------

@pytest.mark.parametrize("split", ["training", "calibration"])
def test_spawn_point_2_on_the_evaluation_segment_is_refused(fx, split):
    m = manifest([fx.run("r1", 11, split, spawn=2, segment=dict(EVALUATION_SEGMENT))])
    refusals, _ = M.check_manifest(m, fx.files, fx.labels)
    assert any("evaluation section" in r and "spawn point 2" in r for r in refusals), refusals


def test_test_split_on_the_evaluation_segment_is_reported_not_refused(fx):
    m = manifest([fx.run("r1", 11, "test", spawn=2, segment=dict(EVALUATION_SEGMENT))])
    refusals, reports = M.check_manifest(m, fx.files, fx.labels)
    assert refusals == [] and any("evaluation section" in r for r in reports)


def test_other_section_of_the_evaluation_road_is_admitted(fx):
    m = manifest([fx.run("r1", 11, "training", spawn=2, segment={"map": MAP, "roadId": 40, "sectionId": 1})])
    assert M.check_manifest(m, fx.files, fx.labels) == ([], [])


# ---- MEDIUM-2: scenario verified, placement recorded ------------------------------------------------------------

def test_scenarios_are_required(fx):
    assert M.check_manifest(good(fx), None, fx.labels)[0]
    files = dict(fx.files)
    files.pop("r2")
    assert any("r2: no scenario file" in r for r in M.check_manifest(good(fx), files, fx.labels)[0])


def test_scenario_digest_mismatch_is_refused(fx):
    m = good(fx)
    fx.files["r1"].write_bytes(fx.files["r1"].read_bytes() + b" ")
    assert any("r1: scenario refused" in r and "scenarioSha256" in r for r in M.check_manifest(m, fx.files, fx.labels)[0])


def test_recorded_placement_must_match_the_verified_scenario(fx):
    m = good(fx)
    m["runs"][2]["targetPlacement"] = {"kind": "ego-lane"}
    assert any("r3: recorded targetPlacement" in r for r in M.check_manifest(m, fx.files, fx.labels)[0])
    m["runs"][2]["targetPlacement"] = {"kind": "adjacent-lane", "side": "up", "direction": "opposite"}
    assert any("r3: targetPlacement must be" in r for r in M.check_manifest(m, fx.files, fx.labels)[0])


def test_scenario_spawn_point_and_map_must_match_the_run(fx):
    m = good(fx)
    m["runs"][0]["spawnPoint"] = 8
    m["runs"][1]["traversedSections"] = [{"map": "Town01", "roadId": 8, "sectionId": 0}]
    refusals = M.check_manifest(m, fx.files, fx.labels)[0]
    assert any("r1: scenario spawnPointIndex 7" in r for r in refusals)
    assert any("r2: scenario map" in r for r in refusals)


def test_schema_1_scenario_without_a_map_is_refused(fx):
    m = good(fx)
    data = json.dumps({"schema": S.SCHEMA_1, "egoBlueprint": TEST_BLUEPRINT, "spawnPointIndex": TEST_SPAWN_POINT}).encode()
    fx.files["r1"].write_bytes(data)
    m["runs"][0].update(scenarioSha256=hashlib.sha256(data).hexdigest(), targetPlacement={"kind": "none"})
    assert any("declares no map" in r for r in M.check_manifest(m, fx.files, fx.labels)[0])


@pytest.mark.parametrize("placement", [{"kind": "none"}, {"kind": "ego-lane"},
                                       {"kind": "adjacent-lane", "side": "right", "direction": "same"}])
def test_placement_is_derived_from_the_verified_scenario(placement):
    data = scenario_bytes(TEST_ALTERNATE_SPAWN_POINT, placement)
    assert S.verified_scenario(data, hashlib.sha256(data).hexdigest()) == {"spawnPointIndex": TEST_ALTERNATE_SPAWN_POINT, "map": MAP,
                                                                           "targetPlacement": placement}


@pytest.mark.parametrize("record", [
    {"schema": "xverse-compat.carla-live-scenario/9", "spawnPointIndex": TEST_ALTERNATE_SPAWN_POINT},
    {"schema": S.SCHEMA_1, "spawnPointIndex": TEST_ALTERNATE_SPAWN_POINT, "target": {}},
    {"schema": S.SCHEMA_2, "spawnPointIndex": TEST_ALTERNATE_SPAWN_POINT, "map": MAP, "target": {"adjacentLane": {"side": "left"}}},
    {"schema": S.SCHEMA_2, "spawnPointIndex": TEST_ALTERNATE_SPAWN_POINT, "map": MAP, "target": {"adjacentLane": {"side": "up", "direction": "same"}}},
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
    refusals, reports = M.check_manifest(m, fx.files, fx.labels)
    assert refusals == [] and reports and "7" in reports[0]


def test_manifest_holds_no_pixels_and_no_host_paths(fx):
    m = good(fx)
    text = json.dumps(m)
    assert all(not isinstance(v, (bytes, bytearray)) for v in json.loads(text).values()) and "pixels" not in text
    assert str(fx.root) not in text


# ---- amendment 1: all traversed sections, actual label records and source closure ------------------------------

@pytest.mark.parametrize("split", ["training", "calibration"])
def test_upstream_spawned_run_crossing_into_a_later_evaluation_section_is_refused(fx, split):
    protected = [dict(EVALUATION_SEGMENT), {"map": MAP, "roadId": 40, "sectionId": 1}]
    run = fx.run("crossing", 21, split, spawn=2,
                 sections=[{"map": MAP, "roadId": 7, "sectionId": 0}, dict(protected[1])])
    m = M.build_manifest(params().digest, L.LABEL_CODE_SHA256, EVALUATION_SEEDS, protected, [run])
    refusals, _ = M.check_manifest(m, fx.files, fx.labels)
    assert any("evaluation sections" in text and "refused as a whole" in text and "spawn point 2" in text
               for text in refusals), refusals


def test_test_split_traversing_second_protected_section_is_reported_not_refused(fx):
    protected = [dict(EVALUATION_SEGMENT), {"map": MAP, "roadId": 40, "sectionId": 1}]
    run = fx.run("test-crossing", 22, "test", sections=[dict(protected[1])])
    m = M.build_manifest(params().digest, L.LABEL_CODE_SHA256, EVALUATION_SEEDS, protected, [run])
    refusals, reports = M.check_manifest(m, fx.files, fx.labels)
    assert refusals == [] and any("evaluation sections" in text for text in reports)


@pytest.mark.parametrize("sections", [
    [], "not-a-set", [dict(EVALUATION_SEGMENT), dict(EVALUATION_SEGMENT)],
    [{"map": MAP, "roadId": 40, "sectionId": 1}, dict(EVALUATION_SEGMENT)],
    [{"map": MAP, "roadId": "40", "sectionId": 0}],
])
@pytest.mark.parametrize("owner", ["evaluation", "run"])
def test_section_sets_are_nonempty_typed_unique_and_in_canonical_order(fx, sections, owner):
    m = good(fx)
    if owner == "evaluation":
        m["evaluation"]["segmentSections"] = sections
    else:
        m["runs"][0]["traversedSections"] = sections
    refusals, _ = M.check_manifest(m, fx.files, fx.labels)
    assert any("evaluation must be" in text if owner == "evaluation" else "traversedSections must be" in text
               for text in refusals), refusals


def test_every_traversed_section_map_must_match_the_verified_scenario(fx):
    m = good(fx)
    m["runs"][0]["traversedSections"] = M.section_set([
        {"map": MAP, "roadId": 7, "sectionId": 0}, {"map": "Town01", "roadId": 8, "sectionId": 0}])
    refusals, _ = M.check_manifest(m, fx.files, fx.labels)
    assert any("scenario map" in text and "Town01" in text for text in refusals)


def test_labels_are_required_and_a_missing_run_is_refused(fx):
    m = good(fx)
    assert M.check_manifest(m, fx.files, None)[0]
    labels = dict(fx.labels)
    labels.pop("r2")
    assert any("r2: no label records" in text for text in M.check_manifest(m, fx.files, labels)[0])
    with pytest.raises(TypeError):
        M.check_manifest(m, fx.files)


def test_label_content_must_reproduce_the_run_digest(fx):
    m = good(fx)
    fx.labels["r1"][0]["distanceBin"] = "no-obstacle"
    assert any("r1: label records do not reproduce labelsSha256" in text
               for text in M.check_manifest(m, fx.files, fx.labels)[0])


@pytest.mark.parametrize("member", ["labelCodeSha256", "labelParamsDigest", "observerSha256"])
def test_rehashed_label_list_still_needs_matching_provenance(fx, member):
    m = good(fx)
    fx.labels["r1"][0]["provenance"][member] = digest("foreign " + member)
    m["runs"][0]["labelsSha256"] = L.labels_digest(fx.labels["r1"])
    assert any("carries another " + member in text for text in M.check_manifest(m, fx.files, fx.labels)[0])


def test_a_manifest_must_name_the_current_label_code_closure(fx):
    m = good(fx)
    m["labelCodeSha256"] = digest("older source closure")
    assert any("not the running label code" in text for text in M.check_manifest(m, fx.files, fx.labels)[0])


def test_a_rehashed_foreign_frame_is_not_admitted_as_a_run_label(fx):
    m = good(fx)
    fx.labels["r1"][0]["rawSha256"] = digest("foreign frame")
    m["runs"][0]["labelsSha256"] = L.labels_digest(fx.labels["r1"])
    assert any("the run does not hold" in text for text in M.check_manifest(m, fx.files, fx.labels)[0])


def test_a_frame_cannot_be_labelled_twice_even_after_rehashing(fx):
    m = good(fx)
    fx.labels["r1"].append(copy.deepcopy(fx.labels["r1"][0]))
    m["runs"][0]["labelsSha256"] = L.labels_digest(fx.labels["r1"])
    assert any("labelled twice" in text for text in M.check_manifest(m, fx.files, fx.labels)[0])


def test_two_label_digests_under_one_frame_number_are_also_duplicate_labels(fx):
    m = good(fx)
    fx.labels["r1"][1]["frame"] = fx.labels["r1"][0]["frame"]
    m["runs"][0]["labelsSha256"] = L.labels_digest(fx.labels["r1"])
    assert any("labelled twice" in text for text in M.check_manifest(m, fx.files, fx.labels)[0])


def test_duplicate_frame_numbers_with_distinct_bytes_are_refused(fx):
    m = good(fx)
    m["runs"][0]["frames"][1]["frame"] = m["runs"][0]["frames"][0]["frame"]
    fx.labels["r1"][1]["frame"] = fx.labels["r1"][0]["frame"]
    m["runs"][0]["labelsSha256"] = L.labels_digest(fx.labels["r1"])
    assert any("appears twice in the run frame table" in text for text in M.check_manifest(m, fx.files, fx.labels)[0])


@pytest.mark.parametrize("field,value", [("runId", []), ("runId", ""), ("split", []),
                                          ("frame", []), ("frame", True), ("simElapsedNs", [])])
def test_malformed_unhashable_members_are_refusals_not_exceptions(fx, field, value):
    m = good(fx)
    if field in ("runId", "split"):
        m["runs"][0][field] = value
    else:
        m["runs"][0]["frames"][0][field] = value
    assert M.check_manifest(m, fx.files, fx.labels)[0]


def test_scenario_source_alone_changes_the_label_code_closure(tmp_path):
    from pathlib import Path
    directory = Path(L.__file__).resolve().parent
    for name in L.LABEL_CODE_FILES:
        (tmp_path / name).write_bytes((directory / name).read_bytes())
    before = L.label_code_digest(tmp_path)
    assert before == L.LABEL_CODE_SHA256
    source = tmp_path / "scenario.py"
    source.write_bytes(source.read_bytes() + b"\n# TEST-ONLY source change\n")
    assert L.label_code_digest(tmp_path) != before
