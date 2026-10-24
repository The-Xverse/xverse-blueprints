"""Offline tests of the WP-09 perception labels on hand-built observer v2 files (no CARLA, no run).

Extents, corridor, bin edges and the named scenario fixture settings below are TEST VALUES; the protocol values are TODO (AD-02, WP-09; after D-1/D-2).
The camera values are the configured ones (compat scenario.py 31 CAMERA_MOUNT; carla-sensors.json camera).
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from assured_aeb.perception import labels as L

HERE = Path(__file__).resolve().parents[1]
CAMERA = {"mountM": [1.5, 0.0, 2.4], "fovDeg": 90.0, "width": 800, "height": 600}  # configured camera (sourced)
PARAMS_RECORD = {"schema": L.LABEL_PARAMS, "corridor": {"halfWidthM": 1.5, "maxRangeM": 80.0},
                 "distanceBinEdgesM": [10.0, 20.0, 40.0], "camera": dict(CAMERA)}  # corridor and edges: test values
EGO_BOX = {"extentM": [2.4, 1.0, 0.75], "locationM": [0.0, 0.0, 0.7]}  # test values
TARGET_BOX = {"extentM": [2.2, 0.9, 0.75], "locationM": [0.1, 0.0, 0.7]}  # test values
TEST_SPAWN_POINT, TEST_ALTERNATE_SPAWN_POINT = 7, 3
TEST_BLUEPRINT = "vehicle.test"
TEST_TARGET_DISTANCE_M, TEST_TARGET_HOLD = 30.0, "brake-and-hand-brake"



def params():
    return L.LabelParams.from_record(json.loads(json.dumps(PARAMS_RECORD)))


def entry(x, y=0.0, z=0.0, yaw=0.0):
    return {"status": "observed", "id": 1, "location": [x, y, z], "rotationDeg": [0.0, yaw, 0.0]}


def observer(frames, *, target=True, boxes=True, header=None):
    lines = [header or {"header": True, "schema": L.OBSERVER_SCHEMA, "evaluationOnly": True, "roles": [L.EGO_ROLE, L.TARGET_ROLE]}]
    if boxes:
        lines.append({"resolution": True, "frame": 0, "role": L.EGO_ROLE, "id": 1, "boundingBox": EGO_BOX, "boundingBoxStatus": "observed"})
        if target:
            lines.append({"resolution": True, "frame": 0, "role": L.TARGET_ROLE, "id": 2, "boundingBox": TARGET_BOX,
                          "boundingBoxStatus": "observed"})
    for frame, roles in frames:
        lines.append({"frame": frame, "simElapsedNs": 1_000_000_000 + frame * 50_000_000, "roles": roles})
    lines.append({"footer": True})
    return ("\n".join(json.dumps(line) for line in lines) + "\n").encode()


def items(frames):
    return [{"frame": f, "rawSha256": hashlib.sha256(f"frame-{f}".encode()).hexdigest()} for f in frames]


def scenario(declared, adjacent=None):
    """A live-scenario file (compat schema 2) and its digest; the target is declared or not (finding 4 / LOW-1)."""

    record = {"schema": "xverse-compat.carla-live-scenario/2", "egoBlueprint": TEST_BLUEPRINT, "spawnPointIndex": TEST_SPAWN_POINT,
              "map": "Town10HD_Opt"}
    if declared:
        record["target"] = {"blueprint": TEST_BLUEPRINT, "roleName": L.TARGET_ROLE, "distanceAheadM": TEST_TARGET_DISTANCE_M,
                            "hold": TEST_TARGET_HOLD}
        if adjacent:
            record["target"]["adjacentLane"] = adjacent
    data = json.dumps(record, sort_keys=True).encode()
    return data, hashlib.sha256(data).hexdigest()


def run_labels(data, frames, *, declared=True):
    sc, sha = scenario(declared)
    return L.label_run(data, items(frames), params(), scenario=sc, scenario_sha256=sha)


def label_one(target_entry, *, declared=True, ego_entry=None):
    roles = {L.EGO_ROLE: ego_entry or entry(0.0)}
    if target_entry is not None:
        roles[L.TARGET_ROLE] = target_entry
    return run_labels(observer([(5, roles)], target=declared), [5], declared=declared)


# ---- parameters ----------------------------------------------------------------------------------------------

def test_configured_camera_values():
    assert CAMERA == {"mountM": [1.5, 0.0, 2.4], "fovDeg": 90.0, "width": 800, "height": 600}


@pytest.mark.parametrize("mutate", [
    lambda r: r.pop("corridor"), lambda r: r["corridor"].update(halfWidthM=0), lambda r: r.update(distanceBinEdgesM=[]),
    lambda r: r.update(distanceBinEdgesM=[10.0, 10.0]), lambda r: r.update(distanceBinEdgesM=[-1.0, 5.0]),
    lambda r: r["camera"].update(fovDeg=180), lambda r: r["camera"].update(mountM=[1.5, 0.0]), lambda r: r.update(extra=1),
])
def test_label_parameters_are_refused(mutate):
    record = json.loads(json.dumps(PARAMS_RECORD))
    mutate(record)
    with pytest.raises(ValueError):
        L.LabelParams.from_record(record)


def test_label_run_requires_validated_params():
    with pytest.raises(TypeError):
        L.label_run(observer([]), [], None, scenario=scenario(True)[0], scenario_sha256=scenario(True)[1])


# ---- geometry ------------------------------------------------------------------------------------------------

def test_aligned_target_ahead_uses_both_offsets():  # WP-02 R-2: ego front loc.x + ext.x; target rear centre - ext.x
    (label,), _ = label_one(entry(30.0))
    assert label["distanceM"] == pytest.approx((30.0 + 0.1 - 2.2) - (0.0 + 2.4))
    assert label["inCorridor"] and label["visible"] and label["obstacle"] and label["distanceBin"] == "bin-2"


def test_lateral_offset_target_is_outside_the_corridor_but_visible():  # WP-02b negatives
    (label,), _ = label_one(entry(30.0, y=4.0))
    assert not label["inCorridor"] and label["visible"] and not label["obstacle"] and label["distanceBin"] == "no-obstacle"


def test_footprint_partly_in_the_corridor_counts():
    (label,), _ = label_one(entry(30.0, y=2.3))  # footprint y in [1.4, 3.2] touches the 1.5 m half-width
    assert label["inCorridor"]


def test_yawed_target_uses_its_footprint():
    (label,), _ = label_one(entry(30.0, yaw=90.0))
    assert label["distanceM"] == pytest.approx((30.0 - 0.9) - 2.4)  # the half-width becomes the longitudinal half-size


def test_ego_yaw_rotates_the_frame():
    (label,), _ = label_one(entry(0.0, y=30.0, yaw=90.0), ego_entry=entry(0.0, yaw=90.0))  # both face +y, target 30 m ahead
    assert label["distanceM"] == pytest.approx((30.0 + 0.1 - 2.2) - 2.4) and label["obstacle"]


def test_target_behind_is_neither_in_corridor_nor_visible():
    (label,), _ = label_one(entry(-20.0))
    assert not label["inCorridor"] and not label["visible"] and label["distanceBin"] == "no-obstacle"


def test_vertical_field_of_view():
    (label,), _ = label_one(entry(30.0, z=-60.0))
    assert label["inCorridor"] and not label["visible"] and not label["obstacle"]


def test_beyond_the_corridor_range():
    (label,), _ = label_one(entry(120.0))
    assert not label["inCorridor"]


@pytest.mark.parametrize("distance, expected", [(-0.5, "overlap"), (0.0, "overlap"), (9.99, "bin-0"), (10.0, "bin-1"),
                                                (19.99, "bin-1"), (20.0, "bin-2"), (40.0, "beyond"), (55.0, "beyond")])
def test_distance_bins(distance, expected):
    assert L.distance_bin(True, distance, (10.0, 20.0, 40.0)) == expected
    assert L.distance_bin(False, distance, (10.0, 20.0, 40.0)) == "no-obstacle"


def test_yawed_target_visibility_uses_the_footprint_not_a_tied_corner():  # finding 3 MEDIUM-1 probe (reviewer)
    # Yawed 90° at (5.5, 3.0): footprint x in [4.6, 6.4], y in [0.8, 5.2]. The corner (4.6, 0.8) is in the corridor and
    # in the 90° field of view (|y| <= 3.1 at dx = 3.1); the tied corner (4.6, 5.2) is outside it.
    target = entry(5.5, y=2.9, yaw=90.0)  # the box offset locationM.x = 0.1 lies along the yawed target's +y
    (label,), _ = label_one(target)
    assert label["distanceM"] == pytest.approx(2.2)
    assert label["inCorridor"] and label["visible"] and label["obstacle"] and label["distanceBin"] == "bin-0"


def test_corner_order_does_not_change_visibility():  # the mirrored probe ties on the other side
    left, _ = label_one(entry(5.5, y=-3.0 + 0.1, yaw=-90.0))
    right, _ = label_one(entry(5.5, y=3.0 - 0.1, yaw=90.0))
    assert left[0]["visible"] and right[0]["visible"] and left[0]["distanceM"] == pytest.approx(right[0]["distanceM"])


def test_footprint_entirely_outside_the_wedge_is_not_visible():
    (label,), _ = label_one(entry(4.0, y=8.0))  # camera-relative dx <= 4.8 < |y| >= 7.1
    assert not label["visible"] and not label["obstacle"]


def test_clip_half_plane_keeps_the_boundary_and_drops_the_outside():
    square = [(1.0, 1.0), (1.0, -1.0), (-1.0, -1.0), (-1.0, 1.0)]
    assert L.clip_half_plane(square, 1.0, 0.0) and all(x >= -1e-12 for x, _ in L.clip_half_plane(square, 1.0, 0.0))
    assert L.clip_half_plane([(p[0] - 3.0, p[1]) for p in square], 1.0, 0.0) == []
    touching = L.clip_half_plane([(p[0] - 1.0, p[1]) for p in square], 1.0, 0.0)
    assert touching and max(x for x, _ in touching) == 0.0


def test_declared_target_comes_from_the_verified_scenario():  # finding 4 / LOW-1
    data = observer([(5, {L.EGO_ROLE: entry(0.0), L.TARGET_ROLE: entry(30.0)})])
    sc, sha = scenario(True)
    with pytest.raises(ValueError, match="scenarioSha256"):
        L.label_run(data, items([5]), params(), scenario=sc + b" ", scenario_sha256=sha)
    with pytest.raises(TypeError):
        L.label_run(data, items([5]), params(), target_declared=True)  # the caller flag is gone
    labels, excluded = run_labels(data, [5], declared=False)  # no target declared, yet one is present
    assert labels == [] and excluded == {"undeclared-target-present": 1}
    adjacent, sha = scenario(True, {"side": "left", "direction": "opposite"})
    (label,), _ = L.label_run(data, items([5]), params(), scenario=adjacent, scenario_sha256=sha)
    assert label["obstacle"]  # the label is geometric; placement is recorded in the manifest


def test_labels_digest_is_canonical_and_binds_the_code():
    data = observer([(5, {L.EGO_ROLE: entry(0.0), L.TARGET_ROLE: entry(30.0)})])
    labels, _ = run_labels(data, [5])
    assert L.labels_digest(labels) == hashlib.sha256(L.canonical(labels)).hexdigest()
    changed = [dict(labels[0], provenance=dict(labels[0]["provenance"], labelCodeSha256="0" * 64))]
    assert L.labels_digest(changed) != L.labels_digest(labels)


# ---- join, exclusions, provenance ----------------------------------------------------------------------------

def test_run_without_target_gives_negatives():
    labels, excluded = label_one({"status": "absent"}, declared=False)
    assert labels[0]["obstacle"] is False and labels[0]["distanceM"] is None and labels[0]["distanceBin"] == "no-obstacle"


@pytest.mark.parametrize("target, reason", [({"status": "ambiguous", "ids": [2, 3]}, "target-ambiguous"),
                                            ({"status": "non-finite", "id": 2}, "target-non-finite"),
                                            ({"status": "absent"}, "target-absent")])
def test_unusable_target_states_are_excluded_and_counted(target, reason):
    labels, excluded = label_one(target)
    assert labels == [] and excluded == {reason: 1}


def test_missing_observer_record_ego_and_bounding_box_are_excluded():
    data = observer([(5, {L.EGO_ROLE: {"status": "absent"}, L.TARGET_ROLE: entry(30.0)})])
    labels, excluded = run_labels(data, [4, 5])
    assert labels == [] and excluded == {"no-observer-record": 1, "ego-not-observed": 1}
    data = observer([(5, {L.EGO_ROLE: entry(0.0), L.TARGET_ROLE: entry(30.0)})], boxes=False)
    assert run_labels(data, [5])[1] == {"ego-bounding-box": 1}


def test_non_evaluation_observer_file_is_refused():
    with pytest.raises(ValueError):
        run_labels(observer([], header={"header": True, "schema": L.OBSERVER_SCHEMA}), [])


def test_provenance_and_no_pixels():
    data = observer([(5, {L.EGO_ROLE: entry(0.0), L.TARGET_ROLE: entry(30.0)})])
    (label,), _ = run_labels(data, [5])
    provenance = label["provenance"]
    assert provenance["observerSha256"] == hashlib.sha256(data).hexdigest()
    assert data.decode().splitlines()[provenance["observerLine"] - 1].startswith('{"frame": 5')
    closure_files = ("labels.py", "scenario.py")  # delegated LOW-2: named, ordered source closure
    assert L.LABEL_CODE_FILES == closure_files
    closure = [{"file": name, "sha256": hashlib.sha256((HERE / "assured_aeb/perception" / name).read_bytes()).hexdigest()}
               for name in closure_files]
    expected_code = hashlib.sha256(json.dumps(closure, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert provenance["labelCodeSha256"] == expected_code
    assert provenance["labelParamsDigest"] == params().digest
    assert label["rawSha256"] == items([5])[0]["rawSha256"]
    assert all(not isinstance(v, (bytes, bytearray)) for v in label.values())


def _imports(path):
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(("." * node.level) + (node.module or "") + ":" + ",".join(a.name for a in node.names))
    return names


def test_no_runtime_module_imports_the_label_code():  # T-9; FR-021; DYN-002
    scanned = 0
    for path in HERE.rglob("*.py"):
        relative = path.relative_to(HERE).parts
        if relative[0] == "tests" or relative[:2] == ("assured_aeb", "perception"):
            continue
        scanned += 1
        assert not any("perception" in name or "labels" in name for name in _imports(path)), path
    assert scanned >= 5
