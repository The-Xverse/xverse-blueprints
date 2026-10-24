"""Closed offline training-job admission before any framework import (WP-09 training4a).

All scientific values are explicit inputs. This validates future-stage contracts; it trains/fits nothing.
"""
from __future__ import annotations

import copy
from pathlib import Path
import re
import struct
import sys

from . import labels as L, manifest as M
from .training_io import (absolute, canonical, digest, exact, integer, number, parse_json, record_digest,
                          require, sha, text)

SCHEMA = "assured-aeb.training-job/1"
SEPARATION = "assured-aeb.training-separation/1"
CATEGORIES = ("characterisation", "training", "calibration", "pilot", "evaluation")
PARTITIONS = ("fit", "selection", "calibration", "test")
CODE_FILES = ("training_record.py", "training_io.py", "dataset_consumer.py")
LIMITS = ("recordBytes", "sourceBytes", "compressedFrameBytes", "rawFrameBytes", "samples", "modelParameters",
          "tensorElements", "epochs", "batchSize", "memoryBytes", "diskBytes", "outputBytes", "workerTimeoutS")
METRICS = ("occupancyNllMax", "binNllMax", "occupancyBrierMax", "binBrierMax", "oodFalseAlarmMax")


def code_digest():
    root = Path(__file__).resolve().parent
    return record_digest([{"file": name, "sha256": sha((root / name).read_bytes())} for name in CODE_FILES])


def _ordered(values, name, validator):
    require(type(values) is list and bool(values), f"{name}: nonempty ordered list required")
    for value in values:
        validator(value, name)
    require(all(a < b for a, b in zip(values, values[1:])), f"{name}: sorted unique list required")


def _seed(value, name):
    return integer(value, name, 0, 2**32 - 1)


def _bool(value, name):
    require(type(value) is bool, f"{name}: bool required")


def _pair(value, name, low):
    require(type(value) is list and len(value) == 2, f"{name}: 2-D pair required")
    for part in value:
        integer(part, name, low, sys.maxsize)
    return value


def _tolerance(value, name):
    exact(value, {"absolute", "relative"}, name)
    for item in value.values():
        number(item, name, 0)


def _method(value, expected, name):
    require(value == expected and type(value) is type(expected), f"{name}: supported value is {expected!r}")


def validate_frame_format(record):
    frame = exact(record, {"schema", "width", "height", "encoding"}, "frame format")
    _method(frame["schema"], "xverse-compat.camera-frame-format/1", "frame schema")
    _method(frame["encoding"], "bgra8", "frame encoding")
    for key in ("width", "height"):
        integer(frame[key], "frame " + key, 1, sys.maxsize)
    return frame


def validate_separation(record):
    sep = exact(record, {"schema", "categories", "evaluationSections"}, "separation record")
    _method(sep["schema"], SEPARATION, "separation schema")
    exact(sep["categories"], CATEGORIES, "P4 categories")
    seen = set()
    for name, seeds in sep["categories"].items():
        _ordered(seeds, name + " seeds", _seed)
        require(not seen.intersection(seeds), "P4 seed categories overlap")
        seen.update(seeds)
    require(M.sections_ok(sep["evaluationSections"]), "canonical evaluation section set required")
    return sep


class TrainingJob:
    """Private validated record; obtain through from_bytes, inspect through record() copies."""

    @classmethod
    def from_bytes(cls, data, *, max_record_bytes):
        record = parse_json(data, max_bytes=max_record_bytes, canonical_required=True)
        obj = cls.__new__(cls)
        obj._record = record
        obj._sha256 = sha(data)
        obj._validate(len(data))
        return obj

    def record(self):
        return copy.deepcopy(self._record)

    @property
    def sha256(self):
        return self._sha256

    @property
    def class_order(self):
        return self._class_order

    @property
    def frame_bytes(self):
        return self._frame_bytes

    @property
    def input_shape(self):
        return self._input_shape

    @property
    def parameter_count(self):
        return self._parameter_count

    @property
    def memory_ledger(self):
        """Necessary tensor-storage planning only; not an estimate/guarantee of actual process peak memory."""
        return copy.deepcopy(self._memory_ledger)

    def _validate(self, byte_count):
        r = exact(self._record, {"schema", "identity", "dataset", "separation", "trainingPartition", "preprocessing",
                                "architecture", "optimisation", "calibrationFit", "oodFit", "verification", "environments"}, "job")
        _method(r["schema"], SCHEMA, "schema")
        identity = exact(r["identity"], {"candidateId", "purpose", "codeClosureSha256", "inputRecordsSha256"}, "identity")
        text(identity["candidateId"], "candidateId")
        require(identity["purpose"] in ("synthetic-verification", "development-training"), "unsupported offline purpose")
        require(digest(identity["codeClosureSha256"], "code closure") == code_digest(), "training code closure mismatch")
        inputs = {name: r[name] for name in ("dataset", "separation", "preprocessing")}
        require(digest(identity["inputRecordsSha256"], "input records") == record_digest(inputs), "input-record digest mismatch")
        env = exact(r["environments"], {"training", "u4", "limits"}, "environments")
        limits = exact(env["limits"], LIMITS, "engineering limits")
        for key, value in limits.items():
            integer(value, key, 1, sys.maxsize - 1)
        require(byte_count <= limits["recordBytes"] <= limits["sourceBytes"], "job record/source byte bounds inconsistent")
        for name in ("training", "u4"):
            item = exact(env[name], {"identitySha256", "lockSha256", "sourceRevision", "python", "sites"}, name)
            for key in ("identitySha256", "lockSha256"):
                digest(item[key], key)
            require(type(item["sourceRevision"]) is str and re.fullmatch(r"[0-9a-f]{40}", item["sourceRevision"]) is not None,
                    "sourceRevision: exact Git object id required")
            absolute(item["python"], name + " interpreter")
            require(type(item["sites"]) is list and bool(item["sites"]), "explicit environment sites required")
            for path in item["sites"]:
                absolute(path, name + " site")
            require(len(set(item["sites"])) == len(item["sites"]), "duplicate environment site")
        dataset = exact(r["dataset"], {"manifestSha256", "sourceIndexSha256", "labelParams", "labelParamsSha256",
                                       "frameFormat", "frameFormatSha256"}, "dataset")
        for key in ("manifestSha256", "sourceIndexSha256", "labelParamsSha256", "frameFormatSha256"):
            digest(dataset[key], key)
        require(record_digest(dataset["labelParams"]) == dataset["labelParamsSha256"], "label parameter digest mismatch")
        params = L.LabelParams.from_record(dataset["labelParams"])
        self._class_order = ("no-obstacle", "overlap", *(f"bin-{i}" for i in range(len(params.bin_edges_m))), "beyond")
        frame = validate_frame_format(dataset["frameFormat"])
        require((frame["width"], frame["height"]) == (params.width, params.height), "label camera/frame format mismatch")
        require(record_digest(frame) == dataset["frameFormatSha256"], "frame-format digest mismatch")
        self._frame_bytes = 4 * frame["width"] * frame["height"]
        require(self.frame_bytes <= limits["rawFrameBytes"] <= limits["memoryBytes"], "frame exceeds engineering byte bounds")
        separation = exact(r["separation"], {"record", "sha256"}, "separation")
        require(digest(separation["sha256"], "separation digest") == record_digest(separation["record"]), "separation digest mismatch")
        validate_separation(separation["record"])
        partitions = exact(r["trainingPartition"], {"fit", "selection"}, "training partition")
        for name, values in partitions.items():
            _ordered(values, name + " runs", text)
        require(not set(partitions["fit"]).intersection(partitions["selection"]), "fit/selection runs overlap")
        self._preprocessing(frame)
        self._methods_and_numbers()

    def _preprocessing(self, frame):
        pre = exact(self._record["preprocessing"], {"record", "sha256", "codeSha256", "numpyVersion"}, "preprocessing")
        require(digest(pre["sha256"], "preprocessing digest") == record_digest(pre["record"]), "preprocessing digest mismatch")
        digest(pre["codeSha256"], "preprocess source")
        text(pre["numpyVersion"], "numpyVersion")
        # This accepted module is stdlib-only at import; explicit version prevents binding() importing numpy.
        from xverse_compat.inference import preprocess as shared
        p = shared.load_params(pre["record"])
        require((p.in_w, p.in_h) == (frame["width"], frame["height"]), "preprocess/frame input mismatch")
        expected = {shared.META_PREFIX + "schema": shared.SCHEMA, shared.META_PREFIX + "paramsSha256": pre["sha256"],
                    shared.META_PREFIX + "codeSha256": pre["codeSha256"], shared.META_PREFIX + "numpy": pre["numpyVersion"]}
        require(shared.binding(p, numpy_version=pre["numpyVersion"]) == expected, "shared preprocess source/parameter binding mismatch")
        self._input_shape = (1, 3, p.out_h, p.out_w)

    def _methods_and_numbers(self):
        r = self._record
        limits = r["environments"]["limits"]
        a = exact(r["architecture"], {"inputName", "occupancyOutput", "binOutput", "convBlocks", "occupancyBias", "binBias",
                                       "initialization"}, "architecture")
        names = [text(a[key], key) for key in ("inputName", "occupancyOutput", "binOutput")]
        require(len(set(names)) == 3, "static I/O names must be distinct")
        require(type(a["convBlocks"]) is list and bool(a["convBlocks"]), "nonempty Conv/ReLU block list required")
        for key in ("occupancyBias", "binBias"):
            _bool(a[key], key)
        init = exact(a["initialization"], {"method", "low", "high"}, "initialization")
        _method(init["method"], "uniform", "initialization method")
        for key in ("low", "high"):
            number(init[key], "initialization " + key)
            try:
                struct.pack("<f", init[key])
            except (OverflowError, struct.error) as error:
                raise ValueError("initialization bounds must be float32-representable") from error
        require(init["low"] < init["high"], "ordered uniform bounds required")
        _, channels, height, width = self.input_shape
        parameter_count, activation = 0, channels * height * width
        for block in a["convBlocks"]:
            exact(block, {"outChannels", "kernel", "stride", "padding", "dilation", "bias"}, "Conv/ReLU block")
            out = integer(block["outChannels"], "output channels", 1, sys.maxsize)
            kernel, stride, padding, dilation = (_pair(block[key], key, 0 if key == "padding" else 1)
                                                 for key in ("kernel", "stride", "padding", "dilation"))
            _bool(block["bias"], "Conv bias")
            parameter_count += out * channels * kernel[0] * kernel[1] + (out if block["bias"] else 0)
            height = (height + 2 * padding[0] - dilation[0] * (kernel[0] - 1) - 1) // stride[0] + 1
            width = (width + 2 * padding[1] - dilation[1] * (kernel[1] - 1) - 1) // stride[1] + 1
            require(height > 0 and width > 0, "convolution has nonpositive spatial output")
            channels = out
            activation = max(activation, out * height * width)
        classes = len(self.class_order)
        activation = max(activation, 1 + classes)  # Both required head outputs coexist; flatten aliases GAP storage.
        parameter_count += channels * (1 + classes) + int(a["occupancyBias"]) + (classes if a["binBias"] else 0)
        self._parameter_count = parameter_count
        require(parameter_count <= limits["modelParameters"] and parameter_count * 4 <= limits["outputBytes"],
                "model exceeds declared engineering bounds")
        opt = exact(r["optimisation"], {"method", "epochs", "batchSize", "learningRate", "momentum", "dampening", "weightDecay",
                                       "nesterov", "lossWeights", "device", "numWorkers", "intraOpThreads", "interOpThreads",
                                       "seeds", "deterministicAlgorithms", "selection"}, "optimisation")
        _method(opt["method"], "sgd", "optimizer")
        _method(opt["device"], "cpu", "device")
        _method(opt["numWorkers"], 0, "numWorkers")
        _method(opt["deterministicAlgorithms"], True, "deterministicAlgorithms")
        integer(opt["epochs"], "epochs", 1, limits["epochs"])
        integer(opt["batchSize"], "batchSize", 1, limits["batchSize"])
        for key in ("intraOpThreads", "interOpThreads"):
            integer(opt[key], key, 1, sys.maxsize)
        number(opt["learningRate"], "learningRate", positive=True)
        for key in ("momentum", "dampening", "weightDecay"):
            number(opt[key], key, 0)
        _bool(opt["nesterov"], "nesterov")
        require(not opt["nesterov"] or (opt["momentum"] > 0 and opt["dampening"] == 0), "Nesterov needs momentum>0/dampening=0")
        exact(opt["lossWeights"], {"occupancy", "bins"}, "lossWeights")
        for value in opt["lossWeights"].values():
            number(value, "loss weight", positive=True)
        exact(opt["seeds"], {"torch", "numpy", "dataOrder", "initialization"}, "optimizer seeds")
        for key, value in opt["seeds"].items():
            _seed(value, key + " seed")
        select = exact(opt["selection"], {"epochs", "method", "weighting"}, "selection")
        _ordered(select["epochs"], "selection epochs", lambda v, n: integer(v, n, 1, opt["epochs"]))
        _method(select["method"], "minimum-selection-loss-earliest-epoch", "checkpoint method")
        _method(select["weighting"], "equal-examples", "selection weighting")
        require(activation * opt["batchSize"] <= limits["tensorElements"]
                and activation * opt["batchSize"] * 4 <= limits["memoryBytes"], "activation exceeds declared engineering bounds")
        weights, gradients = parameter_count * 4, parameter_count * 4
        momentum = parameter_count * 4 if opt["momentum"] > 0 else 0
        activation_bytes = activation * opt["batchSize"] * 4
        necessary = max(weights + activation_bytes, weights + gradients + momentum)
        self._memory_ledger = {"dtype": "float32", "bytesPerElement": 4, "trainableParameters": parameter_count,
                               "weightBytes": weights, "gradientBytes": gradients, "momentumBytes": momentum,
                               "maximumBatchActivationBytes": activation_bytes, "necessaryMemoryBytes": necessary}
        require(necessary <= limits["memoryBytes"], "necessary resident float32 tensor storage exceeds memoryBytes")
        require(limits["outputBytes"] <= limits["diskBytes"], "output/disk byte bounds inconsistent")
        calibration = exact(r["calibrationFit"], {"method", "status", "reference", "occupancyTemperatures", "binTemperatures",
                                                  "population", "weighting", "ties"}, "calibrationFit")
        for key, expected in (("method", "temperature-grid-nll"), ("status", "delegated-design"), ("population", "calibration"),
                              ("weighting", "equal-examples"), ("ties", "smallest-temperature")):
            _method(calibration[key], expected, "calibration " + key)
        text(calibration["reference"], "calibration reference")
        for key in ("occupancyTemperatures", "binTemperatures"):
            _ordered(calibration[key], key, lambda v, n: number(v, n, positive=True))
        ood = exact(r["oodFit"], {"method", "fitRule", "status", "reference", "quantile", "population", "comparison"}, "oodFit")
        for key, expected in (("method", "max-probability"), ("fitRule", "nearest-rank"), ("status", "delegated-design"),
                              ("population", "calibration"), ("comparison", "strict-greater")):
            _method(ood[key], expected, "OOD " + key)
        text(ood["reference"], "OOD reference")
        number(ood["quantile"], "OOD quantile", high=1, positive=True)
        self._verification()

    def _verification(self):
        verify = exact(self._record["verification"], {"rawLogits", "calibratedProbabilities", "minimumDecisionAgreement",
                                                       "exactRepeatCount", "sampleSelection", "independentReference",
                                                       "coverage", "metricAcceptance", "occupancyThreshold"}, "verification")
        for key in ("rawLogits", "calibratedProbabilities"):
            _tolerance(verify[key], key)
        number(verify["minimumDecisionAgreement"], "minimumDecisionAgreement", 0, 1)
        integer(verify["exactRepeatCount"], "exactRepeatCount", 2, sys.maxsize)
        _method(verify["sampleSelection"], "all-admitted", "sample selection")
        ref = exact(verify["independentReference"], {"method", "maximumSamples"}, "independentReference")
        _method(ref["method"], "scalar-and-direct-numpy", "independent reference")
        integer(ref["maximumSamples"], "reference samples", 1, self._record["environments"]["limits"]["samples"])
        coverage = exact(verify["coverage"], PARTITIONS, "coverage partitions")
        for name, entry in coverage.items():
            exact(entry, {"classes", "targetAbsentMin", "adjacentNegativeMin"}, name + " coverage")
            exact(entry["classes"], self.class_order, "coverage classes")
            for count in (*entry["classes"].values(), entry["targetAbsentMin"], entry["adjacentNegativeMin"]):
                integer(count, "coverage minimum", 0, self._record["environments"]["limits"]["samples"])
        metrics = exact(verify["metricAcceptance"], METRICS, "metricAcceptance")
        for value in metrics.values():
            number(value, "metric acceptance", 0)
        number(metrics["oodFalseAlarmMax"], "oodFalseAlarmMax", 0, 1)
        threshold = exact(verify["occupancyThreshold"], {"value", "reference", "comparison"}, "occupancyThreshold")
        number(threshold["value"], "occupancy threshold", 0, 1)
        text(threshold["reference"], "occupancy threshold reference")
        _method(threshold["comparison"], "greater-or-equal", "occupancy comparison")
