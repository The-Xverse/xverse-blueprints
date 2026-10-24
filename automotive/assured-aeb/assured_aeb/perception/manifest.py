"""Dataset manifest and split rule (WP-09 increment #1; review-wp09-labels findings 1 §1.5 and 4; P-2, P-4).

Splits are by run, never by frame. ``check_manifest`` refuses:
- the evaluation spawn point and the evaluation seeds;
- any training or calibration run on the evaluation road segment, i.e. the map road and lane section of spawn
  point 1, a declared parameter (finding 4, MEDIUM-3; decisions.md "WP-09 data separation" (2));
- a seed shared between splits, a frame digest in two runs, a duplicate run and malformed members;
- a run whose scenario file is missing, fails its ``scenarioSha256``, or disagrees with the run's spawn point, map or
  recorded ``targetPlacement`` (finding 4, MEDIUM-2).

The SHA-256 of the canonical manifest is the dataset identity. It binds ``labelParamsDigest``, ``labelCodeSha256``
and each run's ``labelsSha256`` (finding 4, MEDIUM-4). Only digests and counts are recorded, never pixels or host
paths.

The refusal of adjacent-lane targets in *evaluation* runs is an obligation of evaluation-run admission (WP-10 #5 /
WP-16), not of this manifest, which holds no evaluation run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .scenario import check_placement, verified_scenario

MANIFEST = "assured-aeb.dataset-manifest/2"
SPLITS = ("training", "calibration", "test")
SEGMENT_REFUSED_SPLITS = ("training", "calibration")  # decisions.md "WP-09 data separation" (2)
#: P-2: evaluation uses only spawn point 1 (Town10HD_Opt; K-9). A sourced rule, not a chosen value.
EVALUATION_SPAWN_POINT = 1
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
TOP_MEMBERS = {"schema", "labelParamsDigest", "labelCodeSha256", "evaluation", "runs"}
EVALUATION_MEMBERS = {"spawnPoint", "seeds", "segment"}
SEGMENT_MEMBERS = {"map", "roadId", "sectionId"}
RUN_MEMBERS = {"runId", "seed", "spawnPoint", "segment", "split", "scenarioSha256", "targetPlacement", "runParamsSha256",
               "observerSha256", "labelsSha256", "frames"}
FRAME_MEMBERS = {"frame", "simElapsedNs", "rawSha256"}


def canonical(record: Any) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def manifest_digest(manifest: dict[str, Any]) -> str:
    """The dataset identity: SHA-256 of the canonical manifest."""

    return hashlib.sha256(canonical(manifest)).hexdigest()


def _segment_ok(segment: Any) -> bool:
    return isinstance(segment, dict) and set(segment) == SEGMENT_MEMBERS and isinstance(segment["map"], str) \
        and bool(segment["map"]) and type(segment["roadId"]) is int and type(segment["sectionId"]) is int


def build_manifest(label_params_digest: str, label_code_sha256: str, evaluation_seeds: list[int],
                   evaluation_segment: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble a manifest. The evaluation seed list (P-4) and the evaluation segment (P-2; the map road and lane
    section of spawn point 1, TODO: engineering verification) are required, with no default."""

    return {"schema": MANIFEST, "labelParamsDigest": label_params_digest, "labelCodeSha256": label_code_sha256,
            "evaluation": {"spawnPoint": EVALUATION_SPAWN_POINT, "seeds": list(evaluation_seeds),
                           "segment": dict(evaluation_segment)},
            "runs": list(runs)}


def check_manifest(manifest: Any, scenarios: Mapping[str, str | Path]) -> tuple[list[str], list[str]]:
    """Return ``(refusals, reports)``; an empty refusal list means the manifest is admissible.

    ``scenarios`` maps each ``runId`` to its live-scenario file. It is required: each file is read and verified
    against the run's ``scenarioSha256``.
    """

    refusals, reports = [], []
    if not isinstance(manifest, dict) or set(manifest) != TOP_MEMBERS or manifest.get("schema") != MANIFEST:
        return [f"manifest must be exactly {sorted(TOP_MEMBERS)} with schema {MANIFEST}"], []
    if not isinstance(scenarios, Mapping):
        return ["scenarios must map each runId to its scenario file (no default)"], []
    for name in ("labelParamsDigest", "labelCodeSha256"):
        if not (isinstance(manifest[name], str) and HEX64.match(manifest[name])):
            refusals.append(f"{name} must be a SHA-256 hex digest")
    evaluation = manifest["evaluation"]
    if not (isinstance(evaluation, dict) and set(evaluation) == EVALUATION_MEMBERS
            and evaluation["spawnPoint"] == EVALUATION_SPAWN_POINT
            and isinstance(evaluation["seeds"], list) and evaluation["seeds"] and all(type(s) is int for s in evaluation["seeds"])
            and _segment_ok(evaluation["segment"])):
        return refusals + ["evaluation must be {spawnPoint: 1, seeds: [the non-empty P-4 evaluation list], "
                           "segment: {map, roadId, sectionId} of spawn point 1 (P-2)}"], reports
    evaluation_seeds, evaluation_segment = set(evaluation["seeds"]), evaluation["segment"]
    runs = manifest["runs"]
    if not isinstance(runs, list) or not runs:
        return refusals + ["runs must be a non-empty list"], reports
    seen_runs, seed_split, frame_run, segment_splits = set(), {}, {}, {}
    for run in runs:
        if not isinstance(run, dict) or set(run) != RUN_MEMBERS:
            refusals.append(f"run members must be exactly {sorted(RUN_MEMBERS)}")
            continue
        rid = run["runId"]
        if rid in seen_runs:
            refusals.append(f"{rid}: duplicate run id")
        seen_runs.add(rid)
        if run["split"] not in SPLITS:
            refusals.append(f"{rid}: split must be one of {SPLITS}")
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
        if not _segment_ok(run["segment"]):
            refusals.append(f"{rid}: segment must be exactly {sorted(SEGMENT_MEMBERS)} (map, int roadId, int sectionId)")
        else:
            segment = run["segment"]
            if segment == evaluation_segment:
                if run["split"] in SEGMENT_REFUSED_SPLITS:
                    refusals.append(f"{rid}: a {run['split']} run on the evaluation segment {segment} is refused "
                                    f"(P-2 by segment; spawn point {run['spawnPoint']})")
                else:
                    reports.append(f"{rid}: a {run['split']} run on the evaluation segment {segment}")
            segment_splits.setdefault((segment["map"], segment["roadId"], segment["sectionId"]), set()).add(run["split"])
        if not check_placement(run["targetPlacement"]):
            refusals.append(f"{rid}: targetPlacement must be none, ego-lane or adjacent-lane{{side, direction}}")
        refusals.extend(_check_scenario(run, scenarios))
        if not isinstance(run["frames"], list):
            refusals.append(f"{rid}: frames must be a list")
            continue
        for frame in run["frames"]:
            if not (isinstance(frame, dict) and set(frame) == FRAME_MEMBERS and isinstance(frame["rawSha256"], str)
                    and HEX64.match(frame["rawSha256"]) and type(frame["frame"]) is int):
                refusals.append(f"{rid}: frame entries must be exactly {sorted(FRAME_MEMBERS)} with a SHA-256 rawSha256")
                break
            other = frame_run.setdefault(frame["rawSha256"], rid)
            if other != rid:
                refusals.append(f"{rid}: frame {frame['rawSha256'][:12]} also appears in run {other} (split by run)")
    for segment, splits in sorted(segment_splits.items(), key=lambda kv: str(kv[0])):
        if len(splits) > 1:
            reports.append(f"segment {segment!r} is shared by splits {sorted(splits)} (allowed where the segment count requires)")
    return refusals, reports


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
    elif _segment_ok(run["segment"]) and scenario["map"] != run["segment"]["map"]:
        refusals.append(f"{rid}: scenario map {scenario['map']!r} differs from the run segment's {run['segment']['map']!r}")
    if scenario["spawnPointIndex"] != run["spawnPoint"]:
        refusals.append(f"{rid}: scenario spawnPointIndex {scenario['spawnPointIndex']} differs from the run's {run['spawnPoint']}")
    if scenario["targetPlacement"] != run["targetPlacement"]:
        refusals.append(f"{rid}: recorded targetPlacement {run['targetPlacement']} differs from the verified "
                        f"{scenario['targetPlacement']}")
    return refusals
