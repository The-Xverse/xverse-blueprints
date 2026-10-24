"""U4 camera inference with digest-bound metadata, shared preprocessing and no model-update path.

The only runtime output is ``assured-aeb.perception-output/1``. Pixels/tensors never enter that record. Static
model inspection, mandatory I/O, preprocessing/postprocessing bindings and telemetry are checked before the pinned
compat loader may construct a session. Method implementations are candidates pending AD-03; no threshold defaults
or scientific approval is supplied here (WP-13 #3, review findings 1–2).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Callable

from . import model_contract as MC
from . import postprocess as PP

PERCEPTION_OUTPUT = "assured-aeb.perception-output/1"
CAMERA_EVIDENCE = "assured-aeb.camera-evidence/1"
MODEL_SCHEMA = "assured-aeb.model-schema/1"
STREAM = "f07-camera-adas"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
PERCEPTION_MEMBERS = frozenset({"schema", "source", "frame", "frameSha256", "originNs", "occupancyProbability",
                                "binProbabilities", "predictedBin", "oodScore", "oodFlag", "inputQuality",
                                "provenance", "state", "reason"})
PROVENANCE_MEMBERS = frozenset({"modelDigest", "preprocessParamsSha256", "postprocessSha256"})
RESULT_MEMBERS = frozenset({"occupancyProbability", "binProbabilities", "predictedBin", "oodScore", "oodFlag"})
EVIDENCE_MEMBERS = frozenset({"schema", "source", "stream", "sensor", "originNs", "receivedNs", "ageNs", "sequence",
                             "checks", "payload"})
INDICATORS = frozenset({"ageNs", "sequenceGap", "sequenceStatus", "meanLuma", "stdLuma", "darkFraction", "brightFraction",
                       "highFrequencyVariance"})


def _sha(value):
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _integer(value):
    return type(value) is int and value >= 0


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class SpoolReader:
    """Pin the declared root; follow no digest-directory or file symlink beneath it."""

    def __init__(self, root: str | os.PathLike) -> None:
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError("the frame spool root must be an existing absolute directory")
        try:
            self._fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except OSError as error:
            raise ValueError("the frame spool root must be an existing non-symlink directory") from error

    def read(self, frame_sha256: Any, length: int) -> tuple[bytes | None, str | None]:
        if not _sha(frame_sha256):
            return None, "digest-malformed"
        if type(length) is not int or length <= 0:
            return None, "length-malformed"
        if self._fd is None:
            return None, "closed"
        directory = file_fd = None
        try:
            directory = os.open(frame_sha256[:2], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=self._fd)
            file_fd = os.open(frame_sha256, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode):
                return None, "not-a-regular-file"
            if info.st_size != length:
                return None, "length"
            with os.fdopen(file_fd, "rb") as handle:
                file_fd = None
                data = handle.read(length + 1)
        except FileNotFoundError:
            return None, "missing"
        except OSError as error:
            return None, f"unreadable-{type(error).__name__}"
        finally:
            if file_fd is not None:
                os.close(file_fd)
            if directory is not None:
                os.close(directory)
        if len(data) != length:
            return None, "length"
        if hashlib.sha256(data).hexdigest() != frame_sha256:
            return None, "digest"
        return data, None

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def parse_model_schema(record: Any) -> tuple[list, list]:
    if not (isinstance(record, dict) and set(record) == {"schema", "inputs", "outputs"} and record["schema"] == MODEL_SCHEMA):
        raise ValueError("the mandatory model schema must be exactly schema, inputs, outputs (R-5)")

    def entries(items, count, label):
        if not isinstance(items, list) or len(items) != count:
            raise ValueError(f"{label} must contain exactly {count} static float32 tensor declarations")
        out = []
        for item in items:
            if not (isinstance(item, dict) and set(item) == {"name", "shape", "type"}
                    and isinstance(item["name"], str) and item["name"] and "\x00" not in item["name"]
                    and isinstance(item["shape"], list) and item["shape"]
                    and all(type(d) is int and d > 0 for d in item["shape"]) and item["type"] == "tensor(float)"):
                raise ValueError(f"invalid {label} declaration")
            out.append((item["name"], list(item["shape"]), item["type"]))
        return out

    inputs, outputs = entries(record["inputs"], 1, "inputs"), entries(record["outputs"], 2, "outputs")
    names = [n for n, _, _ in inputs + outputs]
    if len(set(names)) != len(names):
        raise ValueError("model I/O identities must be unique")
    return inputs, outputs


def _verdict(checks, name):
    entry = checks.get(name) if isinstance(checks, dict) else None
    if not isinstance(entry, dict) or set(entry) != {"verdict", "failed"} or not isinstance(entry["failed"], list) \
            or not all(isinstance(v, str) and v.strip() for v in entry["failed"]):
        return None
    value = entry.get("verdict")
    if value == "fail" and entry["failed"]:
        return value
    if value in ("pass", "not-evaluated") and not entry["failed"]:
        return value
    return None


def _result_ok(result, labels):
    return (isinstance(result, dict) and set(result) == RESULT_MEMBERS and PP._finite(result["occupancyProbability"])
            and 0 <= result["occupancyProbability"] <= 1 and isinstance(result["binProbabilities"], list)
            and len(result["binProbabilities"]) == len(labels)
            and all(PP._finite(v) and 0 <= v <= 1 for v in result["binProbabilities"])
            and isinstance(result["predictedBin"], str) and result["predictedBin"] in labels
            and PP._finite(result["oodScore"]) and type(result["oodFlag"]) is bool)


class CameraInference:
    """One advisory perception output for every delivered F07 item; no training or update entry point."""

    def __init__(self, *, infer: Callable[[bytes], dict], frame_length: int, spool: SpoolReader, provenance: dict,
                 bin_labels: tuple[str, ...]) -> None:
        if not callable(infer) or type(frame_length) is not int or frame_length <= 0 or type(spool) is not SpoolReader:
            raise TypeError("infer, a positive frame_length and a SpoolReader are required")
        if not (isinstance(provenance, dict) and set(provenance) == PROVENANCE_MEMBERS
                and all(_sha(value) for value in provenance.values())):
            raise ValueError("runtime provenance must contain exactly the three bare SHA-256 digests")
        if not isinstance(bin_labels, tuple) or len(bin_labels) < 2 \
                or not all(isinstance(label, str) and PP.LABEL.fullmatch(label) for label in bin_labels) \
                or len(set(bin_labels)) != len(bin_labels):
            raise ValueError("explicit unique postprocessing bin labels are required")
        self.infer, self.frame_length, self.spool = infer, frame_length, spool
        self.provenance, self.bin_labels = dict(provenance), bin_labels
        self._sequence = self._frame = None

    @classmethod
    def load(cls, *, model_path, model_digest: str, model_schema: Any, preprocess_record: Any, frame_format: Any,
             spool: SpoolReader) -> "CameraInference":
        expected_inputs, expected_outputs = parse_model_schema(model_schema)
        if not isinstance(model_digest, str) or DIGEST.fullmatch(model_digest) is None:
            raise ValueError("model_digest must be sha256:<64 lowercase hex>")
        from xverse_compat.inference import loader, preprocess as PRE  # noqa: PLC0415 - stdlib-only modules
        from xverse_compat.live.frames import load_format  # noqa: PLC0415 - shared declared-format validator

        data = loader.verified_bytes(model_path, model_digest)
        if os.environ.get("ORT_DISABLE_TELEMETRY") != "1" or any(
                name == "onnxruntime" or name.startswith("onnxruntime.") for name in sys.modules):
            raise loader.ModelRefused("telemetry must be disabled before any ONNX Runtime import")
        actual = MC.inspect(data)
        if actual.inputs != expected_inputs or actual.outputs != expected_outputs:
            raise ValueError("static model I/O differs from the mandatory declared schema")
        pre = PRE.load_params(preprocess_record)
        fmt = load_format(frame_format)
        if (fmt["width"], fmt["height"], fmt["encoding"]) != (pre.in_w, pre.in_h, "bgra8") \
                or expected_inputs[0][1] != [1, 3, pre.out_h, pre.out_w]:
            raise ValueError("frame/preprocessing/model input shapes differ")
        PRE.verify_binding(actual.metadata, pre)
        PP.verify_binding(actual.metadata)
        post = PP.parse(actual.metadata)
        by_name = {name: shape for name, shape, _ in expected_outputs}
        if set(by_name) != {post.occupancy_output, post.bins_output} or by_name[post.occupancy_output] != [1, 1] \
                or by_name[post.bins_output] != [1, len(post.bin_labels)]:
            raise ValueError("postprocessing identities/bin count differ from the model outputs")
        # The pinned loader independently rechecks the same digest and creates a session from verified bytes.
        loaded = loader.load_model(model_path, model_digest, expected_inputs=expected_inputs, expected_outputs=expected_outputs)
        if dict(loaded.session.get_modelmeta().custom_metadata_map) != actual.metadata:
            raise ValueError("runtime metadata differs from the inspected verified model")
        names, input_name = [name for name, _, _ in expected_outputs], expected_inputs[0][0]

        def infer(raw):
            values = loaded.session.run(names, {input_name: PRE.preprocess(raw, fmt, pre)})
            if len(values) != len(names):
                raise ValueError("runtime output count differs from the declared model")
            return PP.apply(post, dict(zip(names, values)))

        length = pre.in_w * pre.in_h * 4
        infer(bytes(length))  # warm-up precedes readiness; only the declared shapes and finite outputs are accepted
        provenance = {"modelDigest": model_digest[len("sha256:"):], "preprocessParamsSha256": pre.sha256,
                      "postprocessSha256": post.sha256}
        instance = cls(infer=infer, frame_length=length, spool=spool, provenance=provenance, bin_labels=post.bin_labels)
        instance.loader_record = dict(loaded.record)
        instance.audit_record = {"schema": "assured-aeb.ml-binding-audit/1", "modelDigest": model_digest,
                                 "runtimeProvenance": provenance, "modelSchema": model_schema, "loader": loaded.record,
                                 "preprocessing": {"record": pre.record, "codeSha256": PRE.code_sha256()},
                                 "postprocessing": {"record": post.record, "codeSha256": PP.code_sha256(),
                                                    "methodStatus": "candidate-pending-AD-03"}}
        instance.audit_record = json.loads(_canonical(instance.audit_record))  # detach caller-owned record containers
        instance.audit_sha256 = hashlib.sha256(_canonical(instance.audit_record)).hexdigest()
        return instance

    def step(self, evidence: Any) -> dict[str, Any]:
        record = {"schema": PERCEPTION_OUTPUT, "source": "perception", "frame": None, "frameSha256": None, "originNs": None,
                  "occupancyProbability": None, "binProbabilities": None, "predictedBin": None, "oodScore": None,
                  "oodFlag": None, "inputQuality": {}, "provenance": dict(self.provenance), "state": "UNCERTAIN", "reason": None}
        payload = evidence.get("payload") if isinstance(evidence, dict) else None
        checks = evidence.get("checks") if isinstance(evidence, dict) else None
        if not (isinstance(evidence, dict) and set(evidence) == EVIDENCE_MEMBERS
                and evidence["schema"] == CAMERA_EVIDENCE and evidence["source"] == "front-zone" and evidence["stream"] == STREAM
                and evidence["sensor"] == "smart-camera" and all(_integer(evidence[k]) for k in ("originNs", "receivedNs", "ageNs", "sequence"))
                and evidence["receivedNs"] - evidence["originNs"] == evidence["ageNs"]
                and isinstance(payload, dict) and set(payload) == {"frameSha256", "frame", "indicators"}
                and _sha(payload["frameSha256"]) and _integer(payload["frame"])
                and isinstance(checks, dict) and set(checks) == {"integrity", "sequence", "fresh", "plausibility", "sensorSelfCheck"}):
            record["reason"] = "camera-evidence-malformed"
            return record
        sensor, indicators = checks["sensorSelfCheck"], payload["indicators"]
        quality = {"integrity": _verdict(checks, "integrity"),
                   "sequence": checks["sequence"] if isinstance(checks["sequence"], str) else None,
                   "fresh": checks["fresh"] if type(checks["fresh"]) is bool else None,
                   "plausibility": checks["plausibility"] if isinstance(checks["plausibility"], str) else None, "sensorLogical": _verdict(sensor, "logical"),
                   "sensorPlausibility": _verdict(sensor, "plausibility"), "sensorStatistical": _verdict(sensor, "statistical")}
        record.update(frame=payload["frame"], frameSha256=payload["frameSha256"], originNs=evidence["originNs"])
        if self._sequence is not None and (evidence["sequence"] <= self._sequence or payload["frame"] <= self._frame):
            record["reason"] = "camera-evidence-replayed"
            return record
        failed = [name for name, value in (("integrity", quality["integrity"]), ("front-zone-plausibility", quality["plausibility"]),
                                          ("sensor-logical", quality["sensorLogical"]), ("sensor-plausibility", quality["sensorPlausibility"]))
                  if value != "pass"]
        if not isinstance(sensor, dict) or set(sensor) != {"logical", "plausibility", "statistical"}:
            failed.append("sensor-check-classes")
        if checks["sequence"] not in ("ok", "gap"):
            failed.append("sequence")
        if checks["fresh"] is not True:
            failed.append("stale")
        if quality["sensorStatistical"] not in ("pass", "fail"):
            failed.append("sensor-statistical-unknown")
        indicator_ok = (isinstance(indicators, dict) and set(indicators) == INDICATORS
                        and indicators["sequenceStatus"] in ("ok", "gap", "duplicate", "regressed")
                        and all(PP._finite(value) for key, value in indicators.items() if key != "sequenceStatus"))
        if not indicator_ok:
            failed.append("quality-indicators")
        else:
            quality["indicators"] = dict(indicators)
        # Only the declared, small diagnostic fields are forwarded, never arbitrary payload members.
        record["inputQuality"] = quality
        if failed:
            record["reason"] = "input-checks: " + ",".join(failed)
            return record
        self._sequence, self._frame = evidence["sequence"], payload["frame"]
        raw, why = self.spool.read(payload["frameSha256"], self.frame_length)
        if raw is None:
            record["reason"] = f"frame-unavailable: {why}"
            return record
        try:
            result = self.infer(raw)
            if not _result_ok(result, self.bin_labels):
                raise ValueError("invalid inference result")
            _canonical(result)
        except Exception as error:  # an unusable model output is unknown evidence, never a fabricated probability
            record["reason"] = f"inference-failed:{type(error).__name__}"
            return record
        record.update(result)
        degraded = [name for name, flag in (("sensor-statistical", quality["sensorStatistical"] == "fail"), ("ood", result["oodFlag"])) if flag]
        record["state"] = "DEGRADED" if degraded else "NOMINAL"
        record["reason"] = ",".join(degraded) or None
        return record
