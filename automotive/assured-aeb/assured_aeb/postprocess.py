"""Owned NumPy post-processing of the logits-only U4 model (WP-13 #3; review-wp13-ml-path finding 1 §1.2).

The record ``assured-aeb.postprocess/1`` lives in the model's ``metadata_props`` under ``META_KEY`` as canonical JSON, so
the model digest binds it (decisions.md "WP-09 training pipeline"). It names the two logit outputs, the bin labels, the
calibration method and the OOD method with its threshold. There is no default.

**The methods are CANDIDATE implementations, pending AD-03** (thesis wp09 §6 names them as examples; method choice is
``TODO: author decision``, ``TODO: citation needed``). Any other method is refused. ``code_sha256`` binds this file
into the perception provenance.

The standard library is used at import; numpy is imported only inside ``apply``.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

SCHEMA = "assured-aeb.postprocess/1"
META_KEY = "assured-aeb.postprocess"
CODE_KEY = "assured-aeb.postprocess.codeSha256"
MEMBERS = {"schema", "outputs", "binLabels", "calibration", "ood"}
LABEL = re.compile(r"(no-obstacle|overlap|beyond|bin-(0|[1-9][0-9]*))\Z")  # the WP-09 label vocabulary
#: CANDIDATE methods (AD-03 pending) and their exact parameter members.
CALIBRATION_METHODS = {"temperature-scaling": {"occupancyTemperature", "binTemperature"}}
OOD_METHODS = {"max-probability": set(), "entropy": set()}


def _canonical(record: Any) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _finite(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _positive(value: Any) -> bool:
    return _finite(value) and value > 0


@dataclass(frozen=True)
class PostprocessParams:
    record: dict
    sha256: str
    occupancy_output: str
    bins_output: str
    bin_labels: tuple[str, ...]
    calibration: str
    calibration_params: dict
    ood: str
    ood_threshold: float


def parse_record(record: Any) -> PostprocessParams:
    """Validate an ``assured-aeb.postprocess/1`` record (fail-closed, no defaults)."""

    if not isinstance(record, dict) or set(record) != MEMBERS or record.get("schema") != SCHEMA:
        raise ValueError(f"{SCHEMA} members must be exactly {sorted(MEMBERS)}")
    outputs = record["outputs"]
    if not (isinstance(outputs, dict) and set(outputs) == {"occupancy", "bins"} and all(isinstance(v, str) and v for v in outputs.values())
            and outputs["occupancy"] != outputs["bins"]):
        raise ValueError("outputs must be exactly {occupancy, bins}: two distinct output names")
    labels = record["binLabels"]
    if not (isinstance(labels, list) and len(labels) >= 2 and all(isinstance(x, str) and LABEL.match(x) for x in labels)
            and len(set(labels)) == len(labels)):
        raise ValueError("binLabels must be at least two unique WP-09 labels (no-obstacle, overlap, bin-<i>, beyond)")
    calibration = record["calibration"]
    if not (isinstance(calibration, dict) and set(calibration) == {"method", "params"}
            and isinstance(calibration["method"], str) and calibration["method"] in CALIBRATION_METHODS and isinstance(calibration["params"], dict)
            and set(calibration["params"]) == CALIBRATION_METHODS[calibration["method"]]
            and all(_positive(v) for v in calibration["params"].values())):
        raise ValueError(f"calibration must be {{method, params}} with a method in {sorted(CALIBRATION_METHODS)} "
                         "(CANDIDATE, AD-03) and exactly its positive params")
    ood = record["ood"]
    if not (isinstance(ood, dict) and set(ood) == {"method", "params", "threshold"} and isinstance(ood["method"], str) and ood["method"] in OOD_METHODS
            and isinstance(ood["params"], dict) and set(ood["params"]) == OOD_METHODS[ood["method"]]
            and _finite(ood["threshold"])):
        raise ValueError(f"ood must be {{method, params, threshold}} with a method in {sorted(OOD_METHODS)} (CANDIDATE, AD-03)")
    return PostprocessParams(json.loads(_canonical(record)), hashlib.sha256(_canonical(record)).hexdigest(), outputs["occupancy"],
                             outputs["bins"], tuple(labels), calibration["method"], dict(calibration["params"]), ood["method"],
                             float(ood["threshold"]))


def parse(metadata: Mapping[str, str]) -> PostprocessParams:
    """Read and validate the record from the model's ``custom_metadata_map``."""

    if not isinstance(metadata, Mapping) or META_KEY not in metadata:
        raise ValueError(f"the model metadata has no {META_KEY!r} record")
    try:
        record = json.loads(metadata[META_KEY])
    except (TypeError, ValueError) as error:
        raise ValueError(f"{META_KEY} is not JSON: {error}") from error
    params = parse_record(record)
    if _canonical(record).decode() != metadata[META_KEY]:
        raise ValueError(f"{META_KEY} must be the canonical JSON of its record")
    return params


def metadata_entry(record: dict) -> dict[str, str]:
    """The ``metadata_props`` entry for a record (used by the model writer)."""

    parse_record(record)
    return {META_KEY: _canonical(record).decode(), CODE_KEY: code_sha256()}


def verify_binding(metadata: Mapping[str, str]) -> None:
    """The frozen model must bind the owned postprocessing code as well as its explicit parameter record."""

    if metadata.get(CODE_KEY) != code_sha256():
        raise ValueError("the model's postprocessing code binding differs")


def code_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def apply(params: PostprocessParams, outputs: Mapping[str, Any]) -> dict[str, Any]:
    """Calibrated probabilities, the predicted bin and the OOD score and flag, from the two logit outputs."""

    if type(params) is not PostprocessParams:
        raise TypeError("params must come from parse")
    import numpy as np  # noqa: PLC0415 - lazy: only after the parameter contract
    if not isinstance(outputs, Mapping) or set(outputs) != {params.occupancy_output, params.bins_output}:
        raise ValueError("the two declared logit outputs are required, with no extra outputs")
    occupancy = np.asarray(outputs[params.occupancy_output])
    bins = np.asarray(outputs[params.bins_output])
    if occupancy.dtype.kind != "f" or bins.dtype.kind != "f":
        raise ValueError("logits must be floating-point tensors")
    occupancy, bins = occupancy.astype(np.float64), bins.astype(np.float64)
    if occupancy.shape != (1, 1) or bins.shape != (1, len(params.bin_labels)):
        raise ValueError(f"logit shapes {occupancy.shape}, {bins.shape} differ from [1,1] and [1,{len(params.bin_labels)}]")
    if not (np.all(np.isfinite(occupancy)) and np.all(np.isfinite(bins))):
        raise ValueError("non-finite logits")
    if params.calibration == "temperature-scaling":
        z = float(occupancy[0, 0]) / params.calibration_params["occupancyTemperature"]
        p_occ = 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))
        # Shift before temperature division: finite logits at very small positive temperatures must not
        # become inf - inf. Negative infinity after a subtract/divide overflow contributes exactly zero.
        with np.errstate(over="ignore", under="ignore", invalid="raise", divide="raise"):
            scaled = (bins[0] - bins.max()) / params.calibration_params["binTemperature"]
            e = np.exp(scaled)
            p_bins = e / e.sum()
    else:  # unreachable: parse refuses other methods
        raise ValueError(params.calibration)
    if params.ood == "max-probability":
        score = 1.0 - float(p_bins.max())
    elif params.ood == "entropy":
        positive = p_bins[p_bins > 0]
        score = float(-(positive * np.log(positive)).sum())
    else:  # unreachable
        raise ValueError(params.ood)
    if not (math.isfinite(float(p_occ)) and np.all(np.isfinite(p_bins)) and math.isfinite(score)):
        raise ValueError("non-finite postprocessing result")
    index = int(np.argmax(p_bins))  # the first maximum
    return {"occupancyProbability": float(p_occ), "binProbabilities": [float(v) for v in p_bins],
            "predictedBin": params.bin_labels[index], "oodScore": score, "oodFlag": bool(score > params.ood_threshold)}
