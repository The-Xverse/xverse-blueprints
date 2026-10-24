"""Small genuine label/store/manifest producers; EVERY numeric value and source is TEST-ONLY."""
from __future__ import annotations

import copy
from pathlib import Path

from assured_aeb.perception import labels as L, manifest as M
from assured_aeb.perception.store import FrameStore
from assured_aeb.perception import dataset_consumer as D, training_record as T
from assured_aeb.perception.training_io import canonical, record_digest, sha
from xverse_compat.inference import preprocess


def refresh_job(record):
    record["identity"]["inputRecordsSha256"] = record_digest({name: record[name] for name in ("dataset", "separation", "preprocessing")})


def build(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    params_record = {"schema": L.LABEL_PARAMS, "corridor": {"halfWidthM": 1.5, "maxRangeM": 80.0},
                     "distanceBinEdgesM": [10.0, 20.0],
                     "camera": {"mountM": [1.5, 0.0, 2.4], "fovDeg": 90.0, "width": 4, "height": 4}}
    params = L.LabelParams.from_record(params_record)
    frame_format = {"schema": "xverse-compat.camera-frame-format/1", "width": 4, "height": 4, "encoding": "bgra8"}
    sections = [{"map": "TEST-ONLY-map", "roadId": 1, "sectionId": 0}]
    separation = {"schema": T.SEPARATION, "categories": {"characterisation": [30], "training": [10, 11], "calibration": [20],
                                                           "pilot": [40], "evaluation": [50]}, "evaluationSections": sections}
    source_paths, runs, labels_by_run, index = {}, [], {}, []
    specs = [("fit", "training", 10, "ego-lane"), ("selection", "training", 11, "none"),
             ("calibration", "calibration", 20, "adjacent-lane"), ("test", "test", 30, "ego-lane")]
    for ordinal, (rid, split, seed, placement) in enumerate(specs):
        directory = root / rid
        directory.mkdir()
        scenario = {"schema": "xverse-compat.carla-live-scenario/2", "map": "TEST-ONLY-map", "spawnPointIndex": 7,
                    "egoBlueprint": "vehicle.test"}
        if placement != "none":
            scenario["target"] = {"blueprint": "vehicle.test", "roleName": L.TARGET_ROLE, "distanceAheadM": 30.0,
                                  "hold": "brake-and-hand-brake"}
            if placement == "adjacent-lane":
                scenario["target"]["adjacentLane"] = {"side": "right", "direction": "same"}
        scenario_data = canonical(scenario)
        header = {"header": True, "schema": L.OBSERVER_SCHEMA, "evaluationOnly": True, "roles": [L.EGO_ROLE, L.TARGET_ROLE]}
        box = {"extentM": [2.0, 0.8, 0.75], "locationM": [0.0, 0.0, 0.7]}
        lines = [header, {"resolution": True, "frame": 0, "role": L.EGO_ROLE, "id": 1,
                          "boundingBoxStatus": "observed", "boundingBox": box}]
        if placement != "none":
            lines.append({"resolution": True, "frame": 0, "role": L.TARGET_ROLE, "id": 2,
                          "boundingBoxStatus": "observed", "boundingBox": box})
        frames = []
        store_root = directory / "store"
        store_root.mkdir()
        store = FrameStore(store_root, free_space_floor_bytes=0, compression_level=1, frame_length=64, writable=True)
        for i in range(4):
            raw = bytes([ordinal * 10 + i]) * 64
            raw_sha = sha(raw)
            store.put(raw, raw_sha)
            frames.append({"frame": 100 + i, "simElapsedNs": 1000 + 50 * i, "rawSha256": raw_sha})
            if i < 3:  # the fourth held frame is genuinely excluded by label_run: no observer record
                roles = {L.EGO_ROLE: {"status": "observed", "id": 1, "location": [0.0, 0.0, 0.0], "rotationDeg": [0.0, 0.0, 0.0]}}
                if placement != "none":
                    roles[L.TARGET_ROLE] = {"status": "observed", "id": 2, "location": [10.0 + i * 10, 4.0 if placement == "adjacent-lane" else 0.0, 0.0],
                                            "rotationDeg": [0.0, 0.0, 0.0]}
                lines.append({"frame": 100 + i, "simElapsedNs": 1000 + 50 * i, "roles": roles})
        lines.append({"footer": True})
        observer = b"\n".join(canonical(line) for line in lines) + b"\n"
        labels, excluded = L.label_run(observer, frames, params, scenario=scenario_data, scenario_sha256=sha(scenario_data))
        run_params = canonical({"schema": "assured-aeb.TEST-ONLY-run-params/1", "seed": seed})
        paths = {}
        for name, data in (("scenario", scenario_data), ("observer", observer), ("runParams", run_params), ("labels", canonical(labels))):
            path = directory / (name + ".json")
            path.write_bytes(data)
            paths[name] = str(path)
        paths["store"] = str(store_root)
        source_paths[rid], labels_by_run[rid] = paths, labels
        traversed = [{"map": "TEST-ONLY-map", "roadId": 7, "sectionId": 0}]
        run = {"runId": rid, "seed": seed, "spawnPoint": 7, "traversedSections": traversed, "split": split,
               "scenarioSha256": sha(scenario_data), "targetPlacement": {"kind": placement}, "runParamsSha256": sha(run_params),
               "observerSha256": sha(observer), "labelsSha256": L.labels_digest(labels), "frames": frames}
        if placement == "adjacent-lane":
            run["targetPlacement"].update(side="right", direction="same")
        runs.append(run)
        index.append({"runId": rid, **{key: run[key] for key in D.PINS}, "exclusions": dict(excluded)})
    manifest = M.build_manifest(params.digest, L.LABEL_CODE_SHA256, [50], sections, runs)
    source_index = {"schema": D.SOURCE_INDEX, "runs": index}
    locations = {"schema": D.LOCATIONS, "runs": source_paths}
    for key, value in (("manifest", manifest), ("labelParams", params_record), ("frameFormat", frame_format),
                       ("separation", separation), ("sourceIndex", source_index)):
        path = root / (key + ".json")
        path.write_bytes(canonical(value))
        locations[key] = str(path)
    pre = {"schema": preprocess.SCHEMA, "input": {"width": 4, "height": 4, "encoding": "bgra8"},
           "crop": {"x": 0, "y": 0, "width": 4, "height": 4}, "resize": {"method": "area-integer", "width": 2, "height": 2},
           "channels": "rgb", "normalize": {"mean": [0.0, 0.0, 0.0], "std": [1.0, 1.0, 1.0]}}
    environment = {"identitySha256": "a" * 64, "lockSha256": "b" * 64, "sourceRevision": "c" * 40,
                   "python": "/TEST-ONLY/python", "sites": ["/TEST-ONLY/site"]}
    classes = ["no-obstacle", "overlap", "bin-0", "bin-1", "beyond"]
    coverage = {name: {"classes": dict.fromkeys(classes, 0), "targetAbsentMin": 0, "adjacentNegativeMin": 0} for name in T.PARTITIONS}
    job = {"schema": T.SCHEMA,
           "identity": {"candidateId": "TEST-ONLY-candidate", "purpose": "synthetic-verification", "codeClosureSha256": T.code_digest(),
                        "inputRecordsSha256": "0" * 64},
           "dataset": {"manifestSha256": M.manifest_digest(manifest), "sourceIndexSha256": record_digest(source_index),
                       "labelParams": params_record, "labelParamsSha256": params.digest,
                       "frameFormat": frame_format, "frameFormatSha256": record_digest(frame_format)},
           "separation": {"record": separation, "sha256": record_digest(separation)},
           "trainingPartition": {"fit": ["fit"], "selection": ["selection"]},
           "preprocessing": {"record": pre, "sha256": record_digest(pre), "codeSha256": preprocess.code_sha256(), "numpyVersion": "2.5.4"},
           "architecture": {"inputName": "image", "occupancyOutput": "occupancy_logits", "binOutput": "bin_logits",
                            "convBlocks": [{"outChannels": 2, "kernel": [1, 1], "stride": [1, 1], "padding": [0, 0], "dilation": [1, 1], "bias": True}],
                            "occupancyBias": True, "binBias": True, "initialization": {"method": "uniform", "low": -0.1, "high": 0.1}},
           "optimisation": {"method": "sgd", "epochs": 2, "batchSize": 2, "learningRate": 0.1, "momentum": 0.0, "dampening": 0.0,
                            "weightDecay": 0.0, "nesterov": False, "lossWeights": {"occupancy": 1.0, "bins": 1.0}, "device": "cpu", "numWorkers": 0,
                            "intraOpThreads": 1, "interOpThreads": 1, "seeds": {"torch": 1, "numpy": 2, "dataOrder": 3, "initialization": 4},
                            "deterministicAlgorithms": True,
                            "selection": {"epochs": [1, 2], "method": "minimum-selection-loss-earliest-epoch", "weighting": "equal-examples"}},
           "calibrationFit": {"method": "temperature-grid-nll", "status": "delegated-design", "reference": "TEST-ONLY-design",
                              "occupancyTemperatures": [0.5, 1.0, 2.0], "binTemperatures": [0.5, 1.0, 2.0],
                              "population": "calibration", "weighting": "equal-examples", "ties": "smallest-temperature"},
           "oodFit": {"method": "max-probability", "fitRule": "nearest-rank", "status": "delegated-design", "reference": "TEST-ONLY-design",
                      "quantile": 1.0, "population": "calibration", "comparison": "strict-greater"},
           "verification": {"rawLogits": {"absolute": 0.001, "relative": 0.001}, "calibratedProbabilities": {"absolute": 0.001, "relative": 0.001},
                            "minimumDecisionAgreement": 1.0, "exactRepeatCount": 2, "sampleSelection": "all-admitted",
                            "independentReference": {"method": "scalar-and-direct-numpy", "maximumSamples": 4}, "coverage": coverage,
                            "metricAcceptance": {key: 1.0 for key in T.METRICS},
                            "occupancyThreshold": {"value": 0.5, "reference": "TEST-ONLY-threshold", "comparison": "greater-or-equal"}},
           "environments": {"training": copy.deepcopy(environment), "u4": copy.deepcopy(environment),
                            "limits": {"recordBytes": 1_000_000, "sourceBytes": 1_000_000, "compressedFrameBytes": 1024,
                                       "rawFrameBytes": 64, "samples": 100, "modelParameters": 1000, "tensorElements": 1000,
                                       "epochs": 10, "batchSize": 10, "memoryBytes": 16_000_000, "diskBytes": 16_000_000,
                                       "outputBytes": 1_000_000, "workerTimeoutS": 10}}}
    refresh_job(job)
    return job, locations, manifest, source_index, labels_by_run


def admit(fixture):
    job, locations = fixture[:2]
    return D.admit_dataset(T.TrainingJob.from_bytes(canonical(job), max_record_bytes=1_000_000),
                           D.SourceLocations.from_bytes(canonical(locations), max_record_bytes=1_000_000))


def rehash(fixture):
    """Reproduce every mutable byte pin after a deliberately malformed TEST-ONLY source; not a validator."""
    job, locations, manifest, index, labels_by_run = fixture
    for run in manifest["runs"]:
        rid = run["runId"]
        labels = labels_by_run[rid]
        Path(locations["runs"][rid]["labels"]).write_bytes(canonical(labels))
        run["labelsSha256"] = L.labels_digest(labels)
        next(entry for entry in index["runs"] if entry["runId"] == rid)["labelsSha256"] = run["labelsSha256"]
    Path(locations["manifest"]).write_bytes(canonical(manifest))
    Path(locations["sourceIndex"]).write_bytes(canonical(index))
    job["dataset"]["manifestSha256"] = M.manifest_digest(manifest)
    job["dataset"]["sourceIndexSha256"] = record_digest(index)
    refresh_job(job)
