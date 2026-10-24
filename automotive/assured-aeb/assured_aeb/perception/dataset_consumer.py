"""Offline label/source/P4 admission and streaming bounded frame reads (WP-09 training4a)."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile

from . import labels as L, manifest as M
from .scenario import verified_scenario
from .training_io import (absolute, digest, exact, integer, parse_json, read_frame, read_regular,
                          record_digest, require, sha, text)
from .training_record import PARTITIONS, TrainingJob

LOCATIONS = "assured-aeb.training-source-locations/1"
SOURCE_INDEX = "assured-aeb.training-source-index/1"
REPORT = "assured-aeb.training-admission/1"
LABEL_MEMBERS = {"schema", "frame", "simElapsedNs", "rawSha256", "inCorridor", "visible", "obstacle", "distanceM",
                 "distanceBin", "provenance"}
PROVENANCE = {"observerSha256", "observerLine", "labelCodeSha256", "labelParamsDigest"}
RUN_LOCATORS = {"scenario", "labels", "observer", "runParams", "store"}
PINS = {"scenarioSha256", "labelsSha256", "observerSha256", "runParamsSha256"}


class SourceLocations:
    @classmethod
    def from_bytes(cls, data, *, max_record_bytes):
        record = parse_json(data, max_bytes=max_record_bytes, canonical_required=True)
        exact(record, {"schema", "manifest", "labelParams", "frameFormat", "separation", "sourceIndex", "runs"}, "source locations")
        require(record["schema"] == LOCATIONS, "source locations schema mismatch")
        for key in ("manifest", "labelParams", "frameFormat", "separation", "sourceIndex"):
            absolute(record[key], key)
        require(type(record["runs"]) is dict and bool(record["runs"]), "per-run source locators required")
        for rid, locations in record["runs"].items():
            text(rid, "run id")
            exact(locations, RUN_LOCATORS, "run source locators")
            for key, path in locations.items():
                absolute(path, key)
        obj = cls.__new__(cls)
        obj._record = record
        return obj

    def record(self):
        return copy.deepcopy(self._record)


def _manifest_shape(manifest, maximum_samples):
    exact(manifest, M.TOP_MEMBERS, "manifest")
    require(manifest["schema"] == M.MANIFEST, "manifest /3 required")
    for key in ("labelCodeSha256", "labelParamsDigest"):
        digest(manifest[key], key)
    exact(manifest["evaluation"], M.EVALUATION_MEMBERS, "manifest evaluation")
    integer(manifest["evaluation"]["spawnPoint"], "evaluation spawn", 0)
    require(manifest["evaluation"]["spawnPoint"] == M.EVALUATION_SPAWN_POINT, "evaluation spawn mismatch")
    require(M.sections_ok(manifest["evaluation"]["segmentSections"]), "canonical evaluation sections required")
    seeds = manifest["evaluation"]["seeds"]
    require(type(seeds) is list and bool(seeds), "evaluation seeds required")
    for seed in seeds:
        integer(seed, "evaluation seed", 0, 2**32 - 1)
    require(all(a < b for a, b in zip(seeds, seeds[1:])), "ordered unique evaluation seeds required")
    runs = manifest["runs"]
    require(type(runs) is list and 0 < len(runs) <= maximum_samples, "bounded nonempty run list required")
    identities, count = set(), 0
    for run in runs:
        exact(run, M.RUN_MEMBERS, "manifest run")
        rid = text(run["runId"], "runId")
        require(rid not in identities, "duplicate run id")
        identities.add(rid)
        require(run["split"] in M.SPLITS, "unknown manifest split")
        integer(run["seed"], "run seed", 0, 2**32 - 1)
        integer(run["spawnPoint"], "spawnPoint", 0)
        require(M.sections_ok(run["traversedSections"]), "canonical traversed sections required")
        for key in PINS:
            digest(run[key], key)
        frames = run["frames"]
        require(type(frames) is list and bool(frames), "nonempty manifest frame table required")
        prior = None
        for frame in frames:
            exact(frame, M.FRAME_MEMBERS, "manifest frame")
            integer(frame["frame"], "frame", 0)
            integer(frame["simElapsedNs"], "frame simulator time", 0)
            digest(frame["rawSha256"], "frame digest")
            require(prior is None or frame["frame"] > prior, "ordered unique manifest frames required")
            prior = frame["frame"]
        count += len(frames)
        require(count <= maximum_samples, "manifest exceeds sample bound")
    return identities


def _observer_lines(data, maximum):
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise ValueError("observer UTF-8 required") from error
    require(bool(lines), "observer header missing")
    records = [parse_json(line.encode("utf-8"), max_bytes=maximum) for line in lines]
    header = records[0]
    require(type(header) is dict and header.get("header") is True and header.get("schema") == L.OBSERVER_SCHEMA
            and header.get("evaluationOnly") is True, "evaluation-only observer v2 header required")
    frames = set()
    for record in records[1:]:
        require(type(record) is dict, "observer object records required")
        if record.get("header"):
            raise ValueError("duplicate observer header")
        if not record.get("resolution") and not record.get("footer"):
            integer(record.get("frame"), "observer frame", 0)
            integer(record.get("simElapsedNs"), "observer simulator time", 0)
            require(type(record.get("roles")) is dict, "observer roles required")
            require(record["frame"] not in frames, "duplicate observer frame")
            frames.add(record["frame"])
    return records


def _labels(records, run, params, observer, placement):
    require(type(records) is list, "label list required")
    held = {frame["frame"]: frame for frame in run["frames"]}
    seen = set()
    for label in records:
        exact(label, LABEL_MEMBERS, "consumed label")
        require(label["schema"] == L.LABEL, "label schema mismatch")
        integer(label["frame"], "label frame", 0)
        integer(label["simElapsedNs"], "label simulator time", 0)
        digest(label["rawSha256"], "label raw digest")
        require(label["frame"] in held and label["frame"] not in seen, "unknown or duplicate labelled frame")
        seen.add(label["frame"])
        frame = held[label["frame"]]
        require(all(label[key] == frame[key] for key in M.FRAME_MEMBERS), "label frame/time/hash differs from held frame")
        provenance = exact(label["provenance"], PROVENANCE, "label provenance")
        for key in ("observerSha256", "labelCodeSha256", "labelParamsDigest"):
            digest(provenance[key], key)
        require(provenance["observerSha256"] == run["observerSha256"] and provenance["labelCodeSha256"] == L.LABEL_CODE_SHA256
                and provenance["labelParamsDigest"] == params.digest, "label source provenance mismatch")
        line = integer(provenance["observerLine"], "observer line", 2, len(observer))
        actual = observer[line - 1]
        require(not actual.get("resolution") and not actual.get("footer") and type(actual.get("roles")) is dict
                and actual.get("frame") == label["frame"] and actual.get("simElapsedNs") == label["simElapsedNs"],
                "observer line/frame/time mismatch")
        ego = actual["roles"].get(L.EGO_ROLE, {})
        target = actual["roles"].get(L.TARGET_ROLE, {"status": "absent"})
        require(type(ego) is dict and ego.get("status") == "observed", "labelled observer ego is not observed")
        require(type(target) is dict and target.get("status") == ("absent" if placement["kind"] == "none" else "observed"),
                "labelled observer target status disagrees with declared placement")
        for key in ("inCorridor", "visible", "obstacle"):
            require(type(label[key]) is bool, "label flags must be exact booleans")
        require(label["obstacle"] == (label["inCorridor"] and label["visible"]), "incoherent obstacle conjunction")
        from .training_io import number
        if label["distanceM"] is not None:
            number(label["distanceM"], "label distance")
        if placement["kind"] == "none":
            require(not label["inCorridor"] and not label["visible"] and not label["obstacle"] and label["distanceM"] is None,
                    "target-absent label must use actual false/false/false/null form")
        else:
            require(label["distanceM"] is not None, "observed declared target requires finite distance")
        require(not label["obstacle"] or label["distanceM"] is not None, "obstacle requires distance")
        expected = L.distance_bin(label["obstacle"], label["distanceM"], params.bin_edges_m)
        require(type(label["distanceBin"]) is str and label["distanceBin"] == expected, "incoherent distance bin")


def _counts(classes):
    return {"classes": dict.fromkeys(classes, 0), "targetAbsent": 0, "adjacentNegative": 0, "unlabelledFrames": 0}


class AdmittedDataset:
    def report(self):
        return copy.deepcopy(self._report)

    def iter_samples(self, partition):
        require(partition in PARTITIONS, "unknown dataset partition")
        for rid, label in self._samples[partition]:
            raw = read_frame(self._stores[rid], label["rawSha256"], expected_bytes=self._frame_bytes,
                             compressed_limit=self._limits["compressedFrameBytes"], raw_limit=self._limits["rawFrameBytes"])
            yield {"runId": rid, "frame": label["frame"], "raw": raw, "label": copy.deepcopy(label),
                   "occupancyTarget": int(label["obstacle"]), "binIndex": self._classes.index(label["distanceBin"])}


def admit_dataset(job, locations):
    require(type(job) is TrainingJob and type(locations) is SourceLocations, "validated training job and source locations required")
    record, sources = job.record(), locations.record()
    limits = record["environments"]["limits"]
    consumed_bytes = 0
    def read(path):
        nonlocal consumed_bytes
        data = read_regular(path, limits["sourceBytes"])
        consumed_bytes += len(data)
        require(consumed_bytes <= limits["memoryBytes"], "source snapshots exceed declared memory-byte budget")
        return data
    def source_json(path):
        return parse_json(read(path), max_bytes=limits["sourceBytes"])
    manifest = source_json(sources["manifest"])
    run_ids = _manifest_shape(manifest, limits["samples"])
    require(record_digest(manifest) == record["dataset"]["manifestSha256"], "manifest digest mismatch")
    require(set(sources["runs"]) == run_ids, "source locators must cover exactly the manifest runs")
    for name, expected in (("labelParams", record["dataset"]["labelParams"]), ("frameFormat", record["dataset"]["frameFormat"]),
                           ("separation", record["separation"]["record"])):
        require(source_json(sources[name]) == expected, name + " actual source record mismatch")
    params = L.LabelParams.from_record(record["dataset"]["labelParams"])
    require(manifest["labelParamsDigest"] == params.digest and manifest["labelCodeSha256"] == L.LABEL_CODE_SHA256,
            "manifest label parameter/code identity mismatch")
    separation = record["separation"]["record"]
    require(manifest["evaluation"]["seeds"] == separation["categories"]["evaluation"]
            and manifest["evaluation"]["segmentSections"] == separation["evaluationSections"], "manifest/P4 evaluation mismatch")
    index = source_json(sources["sourceIndex"])
    exact(index, {"schema", "runs"}, "source index")
    require(index["schema"] == SOURCE_INDEX and record_digest(index) == record["dataset"]["sourceIndexSha256"], "source index identity mismatch")
    require(type(index["runs"]) is list and len(index["runs"]) == len(run_ids), "source index run list mismatch")
    indexed = {}
    for entry in index["runs"]:
        exact(entry, {"runId", "exclusions"} | PINS, "source-index run")
        rid = text(entry["runId"], "source-index runId")
        require(rid in run_ids and rid not in indexed, "unknown/duplicate source-index run")
        require(type(entry["exclusions"]) is dict, "supplied recorder exclusions required")
        for reason, count in entry["exclusions"].items():
            text(reason, "recorder exclusion reason")
            integer(count, "recorder exclusion count", 0)
        for key in PINS:
            digest(entry[key], key)
        indexed[rid] = entry
    partitions = record["trainingPartition"]
    training = {run["runId"] for run in manifest["runs"] if run["split"] == "training"}
    require(set(partitions["fit"]) | set(partitions["selection"]) == training, "fit/selection must exactly partition training runs")
    fit_seeds, selection_seeds = set(), set()
    samples = {name: [] for name in PARTITIONS}
    counts = {name: _counts(job.class_order) for name in PARTITIONS}
    per_run, supplied_labels, scenario_bytes, stores = {}, {}, {}, {}
    for run in sorted(manifest["runs"], key=lambda value: value["runId"]):
        rid, split = run["runId"], run["split"]
        category = "characterisation" if split == "test" else split
        require(run["seed"] in separation["categories"][category], "run seed outside its admitted P4 category")
        for key in PINS:
            require(indexed[rid][key] == run[key], "source index/manifest pin mismatch")
        paths = sources["runs"][rid]
        scenario = read(paths["scenario"])
        placement = verified_scenario(scenario, run["scenarioSha256"])["targetPlacement"]
        parse_json(scenario, max_bytes=limits["sourceBytes"])  # duplicate keys/nonfinite values cannot hide in owner parser
        scenario_bytes[rid] = scenario
        observer_data, parameter_data = read(paths["observer"]), read(paths["runParams"])
        require(sha(observer_data) == run["observerSha256"] and sha(parameter_data) == run["runParamsSha256"], "observer/run-parameter source digest mismatch")
        require(type(parse_json(parameter_data, max_bytes=limits["sourceBytes"])) is dict, "run-parameter JSON object required")
        observer = _observer_lines(observer_data, limits["sourceBytes"])
        labels = source_json(paths["labels"])
        require(L.labels_digest(labels) == run["labelsSha256"], "actual label digest mismatch")
        _labels(labels, run, params, observer, placement)
        supplied_labels[rid] = labels
        partition = ("fit" if rid in partitions["fit"] else "selection") if split == "training" else split
        if partition == "fit":
            fit_seeds.add(run["seed"])
        elif partition == "selection":
            selection_seeds.add(run["seed"])
        stats = _counts(job.class_order)
        stats["unlabelledFrames"] = len(run["frames"]) - len(labels)
        for label in sorted(labels, key=lambda item: item["frame"]):
            samples[partition].append((rid, label))
            stats["classes"][label["distanceBin"]] += 1
            stats["targetAbsent"] += int(placement["kind"] == "none")
            stats["adjacentNegative"] += int(placement["kind"] == "adjacent-lane" and not label["obstacle"])
        for name in ("targetAbsent", "adjacentNegative", "unlabelledFrames"):
            counts[partition][name] += stats[name]
        for name in job.class_order:
            counts[partition]["classes"][name] += stats["classes"][name]
        per_run[rid] = {"partition": partition, "counts": stats, "recorderExclusions": copy.deepcopy(indexed[rid]["exclusions"])}
        root = Path(paths["store"])
        require(root.is_dir() and not root.is_symlink(), "existing read-only nonsymlink store root required")
        stores[rid] = str(root)
    require(not fit_seeds.intersection(selection_seeds), "fit/selection seeds overlap")
    # Give the unmodified owner validator exact bounded snapshots, never a mutable unbounded reopen of sources.
    require(sum(map(len, scenario_bytes.values())) <= limits["diskBytes"], "scenario snapshots exceed disk budget")
    with tempfile.TemporaryDirectory(prefix="aeb-training4a-verify-") as temporary:
        snapshots = {}
        for ordinal, (rid, data) in enumerate(sorted(scenario_bytes.items())):
            path = Path(temporary) / (str(ordinal) + ".json")
            path.write_bytes(data)
            snapshots[rid] = path
        refusals, reports = M.check_manifest(manifest, snapshots, supplied_labels)
    require(not refusals, "manifest refused: " + "; ".join(refusals))
    for partition in PARTITIONS:
        require(bool(samples[partition]), partition + " has no admitted labelled samples")
        minimum = record["verification"]["coverage"][partition]
        for name, count in minimum["classes"].items():
            require(counts[partition]["classes"][name] >= count, partition + " class coverage below declared minimum")
        for key, member in (("targetAbsentMin", "targetAbsent"), ("adjacentNegativeMin", "adjacentNegative")):
            require(counts[partition][member] >= minimum[key], partition + " negative coverage below declared minimum")
        # Stream a bounded verification pass before admission; keep no corpus of raw bytes. Iteration rechecks.
        for rid, label in samples[partition]:
            read_frame(stores[rid], label["rawSha256"], expected_bytes=job.frame_bytes,
                       compressed_limit=limits["compressedFrameBytes"], raw_limit=limits["rawFrameBytes"])
    obj = AdmittedDataset()
    obj._samples, obj._stores, obj._limits = samples, stores, copy.deepcopy(limits)
    obj._classes, obj._frame_bytes = tuple(job.class_order), job.frame_bytes
    obj._report = {"schema": REPORT, "jobSha256": job.sha256, "manifestSha256": record_digest(manifest),
                   "sourceIndexSha256": record_digest(index), "separationSha256": record["separation"]["sha256"],
                   "classOrder": list(job.class_order), "counts": counts, "runs": per_run, "manifestReports": reports,
                   "trainingUpdates": ((len(samples["fit"]) + record["optimisation"]["batchSize"] - 1)
                                       // record["optimisation"]["batchSize"] * record["optimisation"]["epochs"]),
                   "limits": ["Byte/provenance checks do not prove recorder#6 source/world-map/traversed-section truth.",
                              "Planar label semantics checked; original geometry is not replayed.",
                              "No training/calibration/framework execution, real numeric freeze or scientific acceptance."]}
    return obj
