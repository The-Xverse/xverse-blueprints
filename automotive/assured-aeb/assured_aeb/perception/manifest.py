"""Dataset manifest and split rule (WP-09 increment #1; review-wp09-labels finding 1 §1.5; P-2, P-4).

Splits are by run, never by frame. ``check_manifest`` refuses the evaluation spawn point and the evaluation seeds, a
seed shared between splits, a frame digest in two runs, a duplicate run and malformed members. The SHA-256 of the
canonical manifest is the dataset identity. Only digests and counts are recorded: never pixels.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

MANIFEST = "assured-aeb.dataset-manifest/1"
SPLITS = ("training", "calibration", "test")
#: P-2: evaluation uses only spawn point 1 (Town10HD_Opt; K-9). A sourced rule, not a chosen value.
EVALUATION_SPAWN_POINT = 1
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
RUN_MEMBERS = {"runId", "seed", "spawnPoint", "segment", "split", "scenarioSha256", "runParamsSha256", "observerSha256", "frames"}
FRAME_MEMBERS = {"frame", "simElapsedNs", "rawSha256"}


def canonical(record: Any) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def manifest_digest(manifest: dict[str, Any]) -> str:
    """The dataset identity: SHA-256 of the canonical manifest."""

    return hashlib.sha256(canonical(manifest)).hexdigest()


def build_manifest(label_params_digest: str, evaluation_seeds: list[int], runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble a manifest; the evaluation seed list (P-4) is required and has no default."""

    return {"schema": MANIFEST, "labelParamsDigest": label_params_digest,
            "evaluation": {"spawnPoint": EVALUATION_SPAWN_POINT, "seeds": list(evaluation_seeds)}, "runs": list(runs)}


def check_manifest(manifest: Any) -> tuple[list[str], list[str]]:
    """Return ``(refusals, reports)``; an empty refusal list means the manifest is admissible."""

    refusals, reports = [], []
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "labelParamsDigest", "evaluation", "runs"} \
            or manifest.get("schema") != MANIFEST:
        return [f"manifest must be exactly schema, labelParamsDigest, evaluation, runs with schema {MANIFEST}"], []
    if not (isinstance(manifest["labelParamsDigest"], str) and HEX64.match(manifest["labelParamsDigest"])):
        refusals.append("labelParamsDigest must be a SHA-256 hex digest")
    evaluation = manifest["evaluation"]
    if not (isinstance(evaluation, dict) and set(evaluation) == {"spawnPoint", "seeds"} and evaluation["spawnPoint"] == EVALUATION_SPAWN_POINT
            and isinstance(evaluation["seeds"], list) and evaluation["seeds"] and all(type(s) is int for s in evaluation["seeds"])):
        return refusals + ["evaluation must be {spawnPoint: 1, seeds: [the non-empty P-4 evaluation list]}"], reports
    evaluation_seeds = set(evaluation["seeds"])
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
        for name in ("scenarioSha256", "runParamsSha256", "observerSha256"):
            if not (isinstance(run[name], str) and HEX64.match(run[name])):
                refusals.append(f"{rid}: {name} must be a SHA-256 hex digest")
        segment_splits.setdefault(run["segment"], set()).add(run["split"])
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
