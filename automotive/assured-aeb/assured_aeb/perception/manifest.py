"""Dataset manifest and split rule (WP-09 increment #1; review-wp09-labels findings 1 §1.5 and 4; P-2, P-4).

Splits are by run, never by frame. ``check_manifest`` refuses:
- the evaluation spawn point and the evaluation seeds;
- as a whole, any training or calibration run whose ego-traversed lane sections (``traversedSections``) meet the
  declared evaluation set (``evaluation.segmentSections``), whatever its spawn point (finding 7, MEDIUM-1 of finding
  6; decisions.md "WP-09 data separation, amendment 1"). The traversed set is filled by the increment #6 recorder from
  the ego waypoint of every recorded frame; its completeness is that recorder's obligation;
- a seed shared between splits, a frame digest in two runs, a duplicate run and malformed members;
- a run whose scenario file is missing, fails its ``scenarioSha256``, or disagrees with the run's spawn point, map or
  recorded ``targetPlacement`` (finding 4, MEDIUM-2);
- a run whose label records do not reproduce its ``labelsSha256``, carry another label code, parameter or observer
  digest, or label a frame the run does not hold (finding 7, LOW-1); and a manifest whose ``labelCodeSha256`` is not
  the running label code's.

The SHA-256 of the canonical manifest is the dataset identity. It binds ``labelParamsDigest``, ``labelCodeSha256``
and each run's ``labelsSha256`` (finding 4, MEDIUM-4). Only digests and counts are recorded, never pixels or host
paths. Binding the scenario map to the loaded world (the observer header) is an obligation of increment #6 (finding
6, LOW-3).

The refusal of adjacent-lane targets in *evaluation* runs is an obligation of evaluation-run admission (WP-10 #5 /
WP-16), not of this manifest, which holds no evaluation run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from . import labels as L
from .scenario import check_placement, verified_scenario

MANIFEST = "assured-aeb.dataset-manifest/3"
SPLITS = ("training", "calibration", "test")
SEGMENT_REFUSED_SPLITS = ("training", "calibration")  # decisions.md "WP-09 data separation" (2), amendment 1
#: P-2: evaluation uses only spawn point 1 (Town10HD_Opt; K-9). A sourced rule, not a chosen value.
EVALUATION_SPAWN_POINT = 1
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
TOP_MEMBERS = {"schema", "labelParamsDigest", "labelCodeSha256", "evaluation", "runs"}
EVALUATION_MEMBERS = {"spawnPoint", "seeds", "segmentSections"}
SECTION_MEMBERS = {"map", "roadId", "sectionId"}
RUN_MEMBERS = {"runId", "seed", "spawnPoint", "traversedSections", "split", "scenarioSha256", "targetPlacement", "runParamsSha256",
               "observerSha256", "labelsSha256", "frames"}
FRAME_MEMBERS = {"frame", "simElapsedNs", "rawSha256"}


def canonical(record: Any) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def manifest_digest(manifest: dict[str, Any]) -> str:
    """The dataset identity: SHA-256 of the canonical manifest."""

    return hashlib.sha256(canonical(manifest)).hexdigest()


def _section_ok(section: Any) -> bool:
    return isinstance(section, dict) and set(section) == SECTION_MEMBERS and isinstance(section["map"], str) \
        and bool(section["map"]) and type(section["roadId"]) is int and type(section["sectionId"]) is int


def _key(section: dict[str, Any]) -> tuple[str, int, int]:
    return section["map"], section["roadId"], section["sectionId"]


def sections_ok(sections: Any) -> bool:
    """A section set: a non-empty list of ``{map, roadId, sectionId}``, unique and in canonical (sorted) order."""

    if not (isinstance(sections, list) and sections and all(_section_ok(x) for x in sections)):
        return False
    keys = [_key(x) for x in sections]
    return all(a < b for a, b in zip(keys, keys[1:]))


def section_set(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return ``sections`` as a canonical section set (unique, sorted); used by producers such as the #6 recorder."""

    unique = {_key(x): x for x in sections}
    return [dict(unique[k]) for k in sorted(unique)]


def build_manifest(label_params_digest: str, label_code_sha256: str, evaluation_seeds: list[int],
                   evaluation_sections: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble a manifest. The evaluation seed list (P-4) and the evaluation section set (P-2 as amended: the lane
    sections the evaluation trajectory covers, TODO: engineering verification) are required, with no default."""

    return {"schema": MANIFEST, "labelParamsDigest": label_params_digest, "labelCodeSha256": label_code_sha256,
            "evaluation": {"spawnPoint": EVALUATION_SPAWN_POINT, "seeds": list(evaluation_seeds),
                           "segmentSections": [dict(x) for x in evaluation_sections]},
            "runs": list(runs)}


def check_manifest(manifest: Any, scenarios: Mapping[str, str | Path],
                   labels: Mapping[str, list[dict[str, Any]]]) -> tuple[list[str], list[str]]:
    """Return ``(refusals, reports)``; an empty refusal list means the manifest is admissible.

    ``scenarios`` maps each ``runId`` to its live-scenario file, and ``labels`` maps each ``runId`` to its label
    records (the ``label_run`` output). Both are required: each file is verified against ``scenarioSha256``, and each
    label list against ``labelsSha256`` and the label provenance.
    """

    refusals, reports = [], []
    if not isinstance(manifest, dict) or set(manifest) != TOP_MEMBERS or manifest.get("schema") != MANIFEST:
        return [f"manifest must be exactly {sorted(TOP_MEMBERS)} with schema {MANIFEST}"], []
    if not isinstance(scenarios, Mapping):
        return ["scenarios must map each runId to its scenario file (no default)"], []
    if not isinstance(labels, Mapping):
        return ["labels must map each runId to its label records (no default)"], []
    for name in ("labelParamsDigest", "labelCodeSha256"):
        if not (isinstance(manifest[name], str) and HEX64.match(manifest[name])):
            refusals.append(f"{name} must be a SHA-256 hex digest")
    if manifest["labelCodeSha256"] != L.LABEL_CODE_SHA256:
        refusals.append("labelCodeSha256 is not the running label code's LABEL_CODE_SHA256 (relabel with this code)")
    evaluation = manifest["evaluation"]
    if not (isinstance(evaluation, dict) and set(evaluation) == EVALUATION_MEMBERS
            and evaluation["spawnPoint"] == EVALUATION_SPAWN_POINT
            and isinstance(evaluation["seeds"], list) and evaluation["seeds"] and all(type(s) is int for s in evaluation["seeds"])
            and sections_ok(evaluation["segmentSections"])):
        return refusals + ["evaluation must be {spawnPoint: 1, seeds: [the non-empty P-4 evaluation list], "
                           "segmentSections: [the non-empty, unique, sorted {map, roadId, sectionId} set (P-2)]}"], reports
    evaluation_seeds = set(evaluation["seeds"])
    evaluation_keys = {_key(x) for x in evaluation["segmentSections"]}
    runs = manifest["runs"]
    if not isinstance(runs, list) or not runs:
        return refusals + ["runs must be a non-empty list"], reports
    seen_runs, seed_split, frame_run, segment_splits = set(), {}, {}, {}
    for run in runs:
        if not isinstance(run, dict) or set(run) != RUN_MEMBERS:
            refusals.append(f"run members must be exactly {sorted(RUN_MEMBERS)}")
            continue
        rid = run["runId"]
        if not isinstance(rid, str) or not rid:
            refusals.append("runId must be a non-empty string")
            continue
        if rid in seen_runs:
            refusals.append(f"{rid}: duplicate run id")
        seen_runs.add(rid)
        if run["split"] not in SPLITS:
            refusals.append(f"{rid}: split must be one of {SPLITS}")
            continue
        if type(run["seed"]) is not int or type(run["spawnPoint"]) is not int:
            refusals.append(f"{rid}: seed and spawnPoint must be integers")
            continue
        if run["spawnPoint"] == EVALUATION_SPAWN_POINT:
            refusals.append(f"{rid}: spawn point {EVALUATION_SPAWN_POINT} is reserved for evaluation (P-2)")
        if run["seed"] in evaluation_seeds:
            refusals.append(f"{rid}: seed {run['seed']} is an evaluation seed (P-4)")
        previous = seed_split.setdefault(run["seed"], run["split"])
        if previous != run["split"]:
            refusals.append(f"{rid}: seed {run['seed']} is used in both {previous} and {run['split']} (P-4 disjoint lists)")
        for name in ("scenarioSha256", "runParamsSha256", "observerSha256", "labelsSha256"):
            if not (isinstance(run[name], str) and HEX64.match(run[name])):
                refusals.append(f"{rid}: {name} must be a SHA-256 hex digest")
        if not sections_ok(run["traversedSections"]):
            refusals.append(f"{rid}: traversedSections must be a non-empty, unique, sorted list of "
                            f"{sorted(SECTION_MEMBERS)} (map, int roadId, int sectionId)")
        else:
            met = sorted({_key(x) for x in run["traversedSections"]} & evaluation_keys)
            if met:
                if run["split"] in SEGMENT_REFUSED_SPLITS:
                    refusals.append(f"{rid}: a {run['split']} run that traverses evaluation sections {met} is refused as "
                                    f"a whole (P-2 by traversed sections; spawn point {run['spawnPoint']})")
                else:
                    reports.append(f"{rid}: a {run['split']} run traverses evaluation sections {met}")
            for section in run["traversedSections"]:
                segment_splits.setdefault(_key(section), set()).add(run["split"])
        if not check_placement(run["targetPlacement"]):
            refusals.append(f"{rid}: targetPlacement must be none, ego-lane or adjacent-lane{{side, direction}}")
        refusals.extend(_check_scenario(run, scenarios))
        if not isinstance(run["frames"], list):
            refusals.append(f"{rid}: frames must be a list")
            continue
        frames_ok, seen_frames = True, set()
        for frame in run["frames"]:
            if not (isinstance(frame, dict) and set(frame) == FRAME_MEMBERS and isinstance(frame["rawSha256"], str)
                    and HEX64.match(frame["rawSha256"]) and type(frame["frame"]) is int and frame["frame"] >= 0
                    and type(frame["simElapsedNs"]) is int):
                refusals.append(f"{rid}: frame entries must be exactly {sorted(FRAME_MEMBERS)} with a SHA-256 rawSha256")
                frames_ok = False
                break
            if frame["frame"] in seen_frames:
                refusals.append(f"{rid}: frame {frame['frame']} appears twice in the run frame table")
                frames_ok = False
            seen_frames.add(frame["frame"])
            other = frame_run.setdefault(frame["rawSha256"], rid)
            if other != rid:
                refusals.append(f"{rid}: frame {frame['rawSha256'][:12]} also appears in run {other} (split by run)")
        if frames_ok:
            refusals.extend(_check_labels(run, manifest, labels))
    for section, splits in sorted(segment_splits.items()):
        if len(splits) > 1:
            reports.append(f"section {section!r} is shared by splits {sorted(splits)} (allowed where the section count requires)")
    return refusals, reports


def _check_labels(run: dict[str, Any], manifest: dict[str, Any], labels: Mapping[str, list[dict[str, Any]]]) -> list[str]:
    """Verify the run's label records against its ``labelsSha256``, the label provenance and its frames (LOW-1)."""

    rid = run["runId"]
    if rid not in labels:
        return [f"{rid}: no label records supplied (labelsSha256 cannot be verified)"]
    records = labels[rid]
    if not (isinstance(records, list) and all(isinstance(r, dict) and isinstance(r.get("provenance"), dict) for r in records)):
        return [f"{rid}: label records must be a list of labels with provenance"]
    try:
        digest = L.labels_digest(records)
    except (TypeError, ValueError) as error:
        return [f"{rid}: label records are not canonical JSON: {error}"]
    refusals = []
    if digest != run["labelsSha256"]:
        refusals.append(f"{rid}: label records do not reproduce labelsSha256")
    held = {(f["frame"], f["rawSha256"]) for f in run["frames"]}
    seen = set()
    for record in records:
        provenance, pair = record["provenance"], (record.get("frame"), record.get("rawSha256"))
        if type(pair[0]) is not int or not isinstance(pair[1], str):
            refusals.append(f"{rid}: a label needs an integer frame and a rawSha256 string")
            continue
        if provenance.get("labelCodeSha256") != manifest["labelCodeSha256"]:
            refusals.append(f"{rid}: label of frame {pair[0]} carries another labelCodeSha256")
        if provenance.get("labelParamsDigest") != manifest["labelParamsDigest"]:
            refusals.append(f"{rid}: label of frame {pair[0]} carries another labelParamsDigest")
        if provenance.get("observerSha256") != run["observerSha256"]:
            refusals.append(f"{rid}: label of frame {pair[0]} carries another observerSha256")
        if pair not in held:
            refusals.append(f"{rid}: label of frame {pair[0]} names a (frame, rawSha256) the run does not hold")
        if pair[0] in seen:
            refusals.append(f"{rid}: frame {pair[0]} is labelled twice")
        seen.add(pair[0])
    return refusals


def _check_scenario(run: dict[str, Any], scenarios: Mapping[str, str | Path]) -> list[str]:
    """Verify the run's scenario file against its digest, spawn point, map and recorded placement (MEDIUM-2)."""

    rid = run["runId"]
    if rid not in scenarios:
        return [f"{rid}: no scenario file supplied (scenarioSha256 cannot be verified)"]
    try:
        data = Path(scenarios[rid]).read_bytes()
        scenario = verified_scenario(data, run["scenarioSha256"])
    except (OSError, ValueError, TypeError) as error:
        return [f"{rid}: scenario refused: {error}"]
    refusals = []
    if scenario["map"] is None:
        refusals.append(f"{rid}: the scenario declares no map (schema 2 is required for a dataset run)")
    elif sections_ok(run["traversedSections"]):
        maps = sorted({x["map"] for x in run["traversedSections"]} - {scenario["map"]})
        if maps:
            refusals.append(f"{rid}: scenario map {scenario['map']!r} differs from traversed-section maps {maps}")
    if scenario["spawnPointIndex"] != run["spawnPoint"]:
        refusals.append(f"{rid}: scenario spawnPointIndex {scenario['spawnPointIndex']} differs from the run's {run['spawnPoint']}")
    if scenario["targetPlacement"] != run["targetPlacement"]:
        refusals.append(f"{rid}: recorded targetPlacement {run['targetPlacement']} differs from the verified "
                        f"{scenario['targetPlacement']}")
    return refusals
