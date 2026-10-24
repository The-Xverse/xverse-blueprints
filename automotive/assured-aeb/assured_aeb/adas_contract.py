"""Active F11/proposal-basis wire /2 and small source-owned assurance metadata.

No qualification, threshold default, gate authority or offline dependency lives here.
Logical payload URNs and wire records are version 2; /1 is historical and is never upcast.
"""
from __future__ import annotations

import copy
import re

from .checks import is_number

SCHEMA = "assured-aeb.adas-cycle/2"
HISTORICAL_SCHEMA = "assured-aeb.adas-cycle/1"
SOURCE = "fusion-risk-aeb"
INTERFACES = frozenset({"adas-cycle", "proposal-basis"})
STATES = ("NOMINAL", "DEGRADED", "UNCERTAIN", "UNSAFE")
HEX = r"^[0-9a-f]{64}$"
QUALITY_KEYS = ("integrity", "sequence", "fresh", "plausibility", "sensorLogical", "sensorPlausibility", "sensorStatistical")
VERDICTS = ("pass", "fail", "not-evaluated")
SEQUENCES = ("ok", "gap", "duplicate", "regressed", "unknown")


def obj(properties):
    return {"type": "object", "additionalProperties": False, "required": sorted(properties), "properties": properties}


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def enum(values):
    return {"enum": list(values)}


TEXT = {"type": "string", "minLength": 1}
NUMBER = {"type": "number"}
UINT = {"type": "integer", "minimum": 0}
BOOL = {"type": "boolean"}
DIGEST = {"type": "string", "pattern": HEX}
PROBABILITY = {"type": "number", "minimum": 0, "maximum": 1}
STRINGS = {"type": "array", "items": TEXT}
VERDICT = obj({"verdict": enum(VERDICTS), "failed": STRINGS})
QUALITY = obj({name: nullable(BOOL if name == "fresh" else enum(SEQUENCES if name == "sequence" else VERDICTS))
               for name in QUALITY_KEYS})
RADAR_CHECKS = obj({"integrity": VERDICT, "sequence": enum(SEQUENCES), "fresh": BOOL,
                    "plausibility": enum(VERDICTS),
                    "sensorSelfCheck": obj({name: VERDICT for name in ("logical", "plausibility", "statistical")})})
CAMERA = obj({"state": enum(STATES), "failures": STRINGS, "originNs": nullable(UINT),
              "ageNs": nullable({"type": "integer"}), "frameSha256": nullable(DIGEST),
              "occupancyProbability": nullable(PROBABILITY), "predictedBin": nullable(TEXT), "oodFlag": nullable(BOOL),
              "provenance": nullable(obj({key: DIGEST for key in ("modelDigest", "preprocessParamsSha256", "postprocessSha256")})),
              "inputQuality": QUALITY, "occupancyDecisionConfidence": nullable(PROBABILITY),
              "distanceClassConfidence": nullable(PROBABILITY)})
RADAR = obj({"state": enum(STATES), "originNs": nullable(UINT), "ageNs": nullable({"type": "integer"}),
             "sequence": nullable(UINT), "count": nullable(UINT), "failures": STRINGS,
             "selectedDetection": nullable(UINT), "checks": nullable(RADAR_CHECKS)})
HYPOTHESIS = obj({"present": BOOL, "agreement": nullable(enum(("agree", "camera-only", "radar-only", "none"))),
                  **{key: nullable(NUMBER) for key in ("distanceM", "closingSpeedMps", "residualM")},
                  "distanceUncertaintyM": NUMBER, "speedUncertaintyMps": NUMBER})
RECORD = obj({"schema": {"const": SCHEMA}, "source": {"const": SOURCE}, "cycle": UINT, "sequence": UINT,
              "originNs": UINT, "brakeRequest": NUMBER, "fired": BOOL, "latched": BOOL, "reason": nullable(TEXT),
              "hypothesis": HYPOTHESIS, "sources": obj({"camera": CAMERA, "radar": RADAR}),
              "state": enum(STATES), "paramsSha256": DIGEST})
MEMBERS = frozenset(RECORD["properties"])


def _matches(value, schema, *, skip_request=False):
    if "anyOf" in schema:
        return any(_matches(value, item) for item in schema["anyOf"])
    if "const" in schema:
        return type(value) is type(schema["const"]) and value == schema["const"]
    if "enum" in schema:
        return any(type(value) is type(item) and value == item for item in schema["enum"])
    kind = schema["type"]
    if kind == "object":
        return (type(value) is dict and set(value) == set(schema["properties"])
                and all(skip_request and key == "brakeRequest" or _matches(value[key], spec)
                        for key, spec in schema["properties"].items()))
    if kind == "array":
        return type(value) is list and all(_matches(item, schema["items"]) for item in value)
    if kind == "null":
        return value is None
    if kind == "boolean":
        return type(value) is bool
    if kind == "string":
        return (type(value) is str and len(value) >= schema.get("minLength", 0)
                and ("pattern" not in schema or re.fullmatch(r"[0-9a-f]{64}", value) is not None))
    if kind in ("integer", "number"):
        return ((type(value) is int if kind == "integer" else is_number(value))
                and ("minimum" not in schema or value >= schema["minimum"])
                and ("maximum" not in schema or value <= schema["maximum"]))
    return False


def validate(record, *, check_request=True):
    """Detach exact active /2. Arbiter alone retains its historical request-value rejection stage.

    check_request=False validates all envelope/metadata fields, but the existing arbiter code must still reject
    nonfinite/ill-typed request values after consuming their sequence and clamp finite out-of-range values.
    This is never an assurance qualification or a historical /1 adapter.
    """
    try:
        valid = _matches(record, RECORD, skip_request=not check_request)
    except (TypeError, ValueError, OverflowError, RecursionError):
        valid = False
    if not valid:
        raise ValueError("closed active F11 /2 native vocabulary required")
    return copy.deepcopy(record)


def camera_quality(value):
    """Forward only known native categorical fields; unavailable values are null, never favorable defaults."""
    empty = dict.fromkeys(QUALITY_KEYS)
    if type(value) is not dict or not set(value) <= set(QUALITY_KEYS) | {"indicators"}:
        return empty
    return {key: value[key] if key in value and _matches(value[key], QUALITY["properties"][key]) else None
            for key in QUALITY_KEYS}


def radar_checks(value):
    """Keep typed contradictions intact; semantic verdict consistency is a later U5 qualification predicate."""
    return copy.deepcopy(value) if _matches(value, RADAR_CHECKS) else None


def confidences(record, *, threshold, binding):
    """Owner's admitted occupancy decision probability and actual selected calibrated class probability."""
    occupancy, distance = None, None
    if (type(record) is dict and type(record.get("provenance")) is dict
            and record["provenance"].get("postprocessSha256") == binding.postprocess_sha256):
        bin_labels = binding.bin_labels
        probability = record.get("occupancyProbability")
        if _matches(probability, PROBABILITY):
            occupancy = probability if probability >= threshold else 1 - probability
        probabilities, selected = record.get("binProbabilities"), record.get("predictedBin")
        if (type(probabilities) is list and len(probabilities) == len(bin_labels) and selected in bin_labels
                and all(_matches(value, PROBABILITY) for value in probabilities)):
            distance = probabilities[bin_labels.index(selected)]
    return occupancy, distance


def interface_urn(interface):
    if interface not in INTERFACES:
        raise ValueError("F11 owner interface required")
    return "urn:xverse:assured-aeb:" + interface + ":v2"


def schema_document(interface):
    if interface not in ("adas-cycle", "proposal-basis"):
        raise ValueError("F11 owner schema alias required")
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": interface_urn(interface), **copy.deepcopy(RECORD)}
