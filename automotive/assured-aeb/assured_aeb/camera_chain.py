"""Camera chain: the U2 corruption stage and the U3 smart-camera self-checks (WP-06 blueprint half, GA-36; WP-07;
AD-18 option C, AD-31 option C, AD-36 option B; review-wp07 finding 1 §1.2-1.3).

``CorruptionStage`` (U2 sensor-model stage, decisions.md §J) takes a verified frame from the compat ``FrameReceiver``
with its camera item and applies the scheduled AD-31 corruption (blur, noise, occlusion, exposure, dropout), seeded
and keyed to episode-relative simulation time with the episode origin bound late from the first frame ("AD-30 delivery
rule"). Its F05 item carries only the *delivered* frame's identity and digest: no event, kind, seed, flag or adapter
digest, so no role unit can learn the schedule (FR-028, FR-031). The applied events are evidence only.

``SmartCamera`` (U3) computes its self-checks from the delivered frame only: frame sequence, age and image statistics,
in the three AD-36 classes. Its output carries indicators and verdicts, never pixels.

Every corruption parameter, threshold and statistics parameter is a protocol value with no default. Obligations on the
wiring (review-wp07 finding 4, MEDIUM-1; WP-10/WP-13): the hub delivers F05 at a simulation time independent of this
stage's processing duration, and no role unit derives an indicator from host time; the per-frame host budget of the
stage and the smart camera is a D-4c measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random
from typing import Any

from . import imageops as I
from .checks import CLASSES, HEX64, IDENTIFIER, exact, is_int, is_number, sequence_status, verdict

CORRUPTION = "assured-aeb.camera-corruption/1"
FRAME_FORMAT = "xverse-compat.camera-frame-format/1"
SENSOR_OUT = "assured-aeb.camera-sensor-out/1"
CAMERA_CHECKS = "assured-aeb.smart-camera-checks/1"
SELFCHECK = "assured-aeb.camera-selfcheck/1"
CAMERA_FLOW = "camera"
KINDS = ("blur", "noise", "occlusion", "exposure", "dropout")
KIND_PARAMS = {"blur": {"boxLog2"}, "noise": {"stdLevel"}, "occlusion": {"x", "y", "width", "height", "value"},
               "exposure": {"gain", "offset"}, "dropout": set()}
SENSOR_OUT_MEMBERS = frozenset({"schema", "source", "frame", "sequence", "originNs", "width", "height", "encoding",
                                "frameSha256", "frameLength"})
BYTES_PER_PIXEL = {"bgra8": 4}


def load_frame_format(record: Any) -> dict[str, Any]:
    """The AD-02 frame format, validated as the compat receiver does (``frames.load_format``)."""

    record = exact(record, FRAME_FORMAT, {"schema", "width", "height", "encoding"})
    if not all(is_int(record[k]) and record[k] > 0 for k in ("width", "height")) or record["encoding"] not in BYTES_PER_PIXEL:
        raise ValueError("frame format needs positive integer width and height and a supported encoding")
    return dict(record)


@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    start_ns: int
    end_ns: int
    params: dict[str, Any]


@dataclass(frozen=True)
class CorruptionSchedule:
    seed: int
    frame_format: dict[str, Any]
    events: tuple[Event, ...]

    @classmethod
    def from_record(cls, record: Any) -> "CorruptionSchedule":
        record = exact(record, CORRUPTION, {"schema", "seed", "frameFormat", "events"})
        if not is_int(record["seed"]) or record["seed"] < 0:
            raise ValueError("seed must be a non-negative integer (no default; P-4)")
        fmt = load_frame_format(record["frameFormat"])
        if not isinstance(record["events"], list):
            raise ValueError("events must be a list")
        events, seen = [], set()
        for raw in record["events"]:
            event = exact(dict(raw, schema=CORRUPTION) if isinstance(raw, dict) else raw, CORRUPTION,
                          {"schema", "id", "kind", "startNs", "endNs", "params"})
            if not isinstance(event["id"], str) or not IDENTIFIER.match(event["id"]) or event["id"] in seen:
                raise ValueError(f"event id {event['id']!r} must be a unique identifier")
            seen.add(event["id"])
            if event["kind"] not in KINDS:
                raise ValueError(f"kind must be one of {KINDS} (AD-31)")
            if not (is_int(event["startNs"]) and is_int(event["endNs"]) and 0 <= event["startNs"] < event["endNs"]):
                raise ValueError("startNs and endNs must be integers with 0 <= startNs < endNs (episode-relative)")
            params = event["params"]
            if not isinstance(params, dict) or set(params) != KIND_PARAMS[event["kind"]]:
                raise ValueError(f"{event['kind']} params must be exactly {sorted(KIND_PARAMS[event['kind']])}")
            _check_params(event["kind"], params, fmt)
            events.append(Event(event["id"], event["kind"], event["startNs"], event["endNs"], dict(params)))
        return cls(record["seed"], fmt, tuple(events))


def _check_params(kind: str, p: dict[str, Any], fmt: dict[str, Any]) -> None:
    if kind == "blur" and not (is_int(p["boxLog2"]) and 1 <= p["boxLog2"] <= I.MAX_BOX_LOG2):
        raise ValueError(f"blur boxLog2 must be an integer in [1, {I.MAX_BOX_LOG2}] (tool limit, not a protocol value)")
    if kind == "noise" and not (is_number(p["stdLevel"]) and p["stdLevel"] > 0):
        raise ValueError("noise stdLevel must be a positive number")
    if kind == "exposure" and not (is_number(p["gain"]) and p["gain"] > 0 and is_number(p["offset"])):
        raise ValueError("exposure needs gain > 0 and a finite offset")
    if kind == "occlusion":
        if not all(is_int(p[k]) for k in ("x", "y", "width", "height", "value")):
            raise ValueError("occlusion members must be integers")
        if not (0 <= p["x"] and 0 <= p["y"] and p["width"] > 0 and p["height"] > 0 and p["x"] + p["width"] <= fmt["width"]
                and p["y"] + p["height"] <= fmt["height"] and 0 <= p["value"] <= 255):
            raise ValueError("occlusion rectangle must lie within the frame and value in [0, 255]")


def _uniform(seed: int, event_id: str, relative_ns: int, length: int) -> bytes:
    key = hashlib.sha256(f"{CORRUPTION}|{seed}|{event_id}|{relative_ns}".encode()).digest()
    return random.Random(int.from_bytes(key[:8], "big")).randbytes(length)


class CorruptionStage:
    """U2 sensor-model stage of the smart camera: verified frame in, delivered frame (or dropout) out."""

    def __init__(self, schedule: CorruptionSchedule) -> None:
        if type(schedule) is not CorruptionSchedule:
            raise TypeError("CorruptionSchedule.from_record is required (no default schedule)")
        self.schedule = schedule
        fmt = schedule.frame_format
        self.length = fmt["width"] * fmt["height"] * BYTES_PER_PIXEL[fmt["encoding"]]
        self.episode_origin_ns: int | None = None
        self.evidence: list[dict[str, Any]] = []
        self.refused: dict[str, int] = {}

    def bind_origin(self, episode_origin_ns: int) -> None:
        if not is_int(episode_origin_ns) or episode_origin_ns < 0:
            raise ValueError("the episode origin must be the integer ns world time of the episode's first frame")
        if self.episode_origin_ns is not None and self.episode_origin_ns != episode_origin_ns:
            raise ValueError(f"the episode origin is already bound to {self.episode_origin_ns}")
        self.episode_origin_ns = episode_origin_ns

    def _refuse(self, reason: str) -> tuple[None, None]:
        self.refused[reason] = self.refused.get(reason, 0) + 1
        return None, None

    def process(self, item: Any, pixels: bytes | None) -> tuple[dict[str, Any] | None, bytes | None]:
        """Return ``(F05 item, delivered bytes)``, or ``(None, None)`` for a dropout or a refused input."""

        if self.episode_origin_ns is None:
            return self._refuse("origin-unbound")
        if not isinstance(item, dict) or item.get("flowId") != CAMERA_FLOW or not isinstance(item.get("value"), dict):
            return self._refuse("not-a-camera-item")
        fmt, value = self.schedule.frame_format, item["value"]
        if (not isinstance(pixels, (bytes, bytearray)) or len(pixels) != self.length or value.get("width") != fmt["width"]
                or value.get("height") != fmt["height"] or not is_int(item.get("originNs")) or not is_int(item.get("sequence"))):
            return self._refuse("malformed")
        if hashlib.sha256(pixels).hexdigest() != value.get("rawSha256"):
            return self._refuse("digest-mismatch")
        relative = item["originNs"] - self.episode_origin_ns
        if relative < 0:
            return self._refuse("before-episode")
        active = [e for e in self.schedule.events if e.start_ns <= relative < e.end_ns]
        if active:
            self.evidence.append({"kind": "corruption-applied", "frame": item.get("frame"), "originNs": item["originNs"],
                                  "events": [e.id for e in active], "kinds": [e.kind for e in active]})
        if any(e.kind == "dropout" for e in active):
            return None, None
        frame = bytes(pixels)
        for event in active:
            frame = self._apply(event, frame, relative)
        out = {"schema": SENSOR_OUT, "source": "camera-imaging-stage", "frame": item.get("frame"), "sequence": item["sequence"],
               "originNs": item["originNs"], "width": fmt["width"], "height": fmt["height"], "encoding": fmt["encoding"],
               "frameSha256": hashlib.sha256(frame).hexdigest(), "frameLength": len(frame)}
        return out, frame

    def _apply(self, event: Event, frame: bytes, relative_ns: int) -> bytes:
        fmt, p = self.schedule.frame_format, event.params
        if event.kind == "exposure":
            return I.exposure(frame, p["gain"], p["offset"])
        if event.kind == "occlusion":
            return I.occlusion(frame, fmt["width"], p["x"], p["y"], p["width"], p["height"], p["value"])
        if event.kind == "noise":
            return I.add_noise(frame, _uniform(self.schedule.seed, event.id, relative_ns, len(frame)), p["stdLevel"])
        if event.kind == "blur":
            return I.box_blur(frame, fmt["width"], fmt["height"], p["boxLog2"])
        raise AssertionError(event.kind)


# --------------------------------------------------------------------------------------------------
# U3 smart camera
# --------------------------------------------------------------------------------------------------

#: Class (iii) thresholds (D-2/D-3; no defaults). The age bound is not here: it is the front zone's AD-06 freshness
#: window (review-wp07 finding 4, LOW-1); the age stays an indicator and a logical check (future origin).
THRESHOLDS = {"minMeanLuma", "maxMeanLuma", "minStdLuma", "maxStdLuma", "maxDarkFraction", "maxBrightFraction",
              "minHighFrequencyVariance", "maxHighFrequencyVariance"}
STATS = {"statsStride", "darkLevel", "brightLevel", "sharpnessBoxLog2"}


@dataclass(frozen=True)
class SmartCameraParams:
    frame_format: dict[str, Any]
    stats: dict[str, int]
    thresholds: dict[str, float]

    @classmethod
    def from_record(cls, record: Any) -> "SmartCameraParams":
        record = exact(record, CAMERA_CHECKS, {"schema", "frameFormat", "stats", "thresholds"})
        fmt = load_frame_format(record["frameFormat"])
        stats, thresholds = record["stats"], record["thresholds"]
        if not isinstance(stats, dict) or set(stats) != STATS or not all(is_int(v) for v in stats.values()):
            raise ValueError(f"stats must be exactly {sorted(STATS)} as integers (no defaults)")
        if not (stats["statsStride"] >= 1 and 0 <= stats["darkLevel"] < stats["brightLevel"] <= 255
                and 1 <= stats["sharpnessBoxLog2"] <= I.MAX_BOX_LOG2):
            raise ValueError(f"required: statsStride >= 1, 0 <= darkLevel < brightLevel <= 255, "
                             f"sharpnessBoxLog2 in [1, {I.MAX_BOX_LOG2}] (tool limit)")
        if not isinstance(thresholds, dict) or set(thresholds) != THRESHOLDS or not all(is_number(v) for v in thresholds.values()):
            raise ValueError(f"thresholds must be exactly {sorted(THRESHOLDS)} as finite numbers (no defaults; D-2/D-3)")
        for low, high in (("minMeanLuma", "maxMeanLuma"), ("minStdLuma", "maxStdLuma"),
                          ("minHighFrequencyVariance", "maxHighFrequencyVariance")):
            if thresholds[low] >= thresholds[high]:
                raise ValueError(f"{low} must be below {high}")
        if not all(0 <= thresholds[k] <= 1 for k in ("maxDarkFraction", "maxBrightFraction")):
            raise ValueError("fraction thresholds must lie in [0, 1]")
        return cls(fmt, dict(stats), dict(thresholds))


class SmartCamera:
    """U3 smart-camera diagnostics: self-checks on the delivered frame only (AD-18)."""

    def __init__(self, params: SmartCameraParams) -> None:
        if type(params) is not SmartCameraParams:
            raise TypeError("SmartCameraParams.from_record is required (no default parameters)")
        self.params = params
        self.last_sequence: int | None = None
        self.last_frame: int | None = None

    def step(self, now_ns: int, item: Any, pixels: bytes | None) -> dict[str, Any]:
        if not is_int(now_ns):
            raise ValueError("simulation time must be integer nanoseconds")
        p, fmt = self.params, self.params.frame_format
        logical, plausibility, statistical = [], [], []
        well_formed = isinstance(item, dict) and set(item) == SENSOR_OUT_MEMBERS and item.get("schema") == SENSOR_OUT \
            and is_int(item.get("sequence")) and is_int(item.get("originNs")) and isinstance(item.get("frameSha256"), str) \
            and HEX64.match(item["frameSha256"]) is not None
        if not well_formed:
            return {"schema": SELFCHECK, "source": "smart-camera", "frame": None, "sequence": None, "originNs": None,
                    "frameSha256": None, "indicators": {}, "checks": {"logical": verdict(["malformed"]),
                    "plausibility": verdict([], False), "statistical": verdict([], False)}}
        status, gap = sequence_status(self.last_sequence, item["sequence"])
        if status != "ok":
            logical.append(f"sequence-{status}")
        if status in ("ok", "gap"):
            self.last_sequence = item["sequence"]
        if is_int(item["frame"]):
            if self.last_frame is not None and item["frame"] <= self.last_frame:
                logical.append("frame-not-increasing")
            self.last_frame = max(item["frame"], self.last_frame if self.last_frame is not None else item["frame"])
        age = now_ns - item["originNs"]
        if age < 0:
            logical.append("future-origin")
        digest_ok = isinstance(pixels, (bytes, bytearray)) and hashlib.sha256(pixels).hexdigest() == item["frameSha256"] \
            and len(pixels) == item["frameLength"]
        if not digest_ok:
            logical.append("digest-or-length")
        if (item["width"], item["height"], item["encoding"]) != (fmt["width"], fmt["height"], fmt["encoding"]) or \
                (digest_ok and len(pixels) != fmt["width"] * fmt["height"] * BYTES_PER_PIXEL[fmt["encoding"]]):
            plausibility.append("geometry")
        indicators: dict[str, Any] = {"ageNs": age, "sequenceGap": gap, "sequenceStatus": status}
        stats_evaluated = digest_ok and not plausibility
        if stats_evaluated:
            s = p.stats
            indicators.update(I.image_statistics(bytes(pixels), fmt["width"], fmt["height"], stride=s["statsStride"],
                                                 dark_level=s["darkLevel"], bright_level=s["brightLevel"],
                                                 sharpness_log2=s["sharpnessBoxLog2"]))
            t = p.thresholds
            hf = indicators["highFrequencyVariance"]
            for name, failed in (("mean-luma", not t["minMeanLuma"] <= indicators["meanLuma"] <= t["maxMeanLuma"]),
                                 ("std-luma-low", indicators["stdLuma"] < t["minStdLuma"]),
                                 ("std-luma-high", indicators["stdLuma"] > t["maxStdLuma"]),
                                 ("dark-fraction", indicators["darkFraction"] > t["maxDarkFraction"]),
                                 ("bright-fraction", indicators["brightFraction"] > t["maxBrightFraction"]),
                                 ("high-frequency-low", hf < t["minHighFrequencyVariance"]),
                                 ("high-frequency-high", hf > t["maxHighFrequencyVariance"])):
                if failed:
                    statistical.append(name)
        checks = dict(zip(CLASSES, (verdict(logical), verdict(plausibility), verdict(statistical, stats_evaluated))))
        return {"schema": SELFCHECK, "source": "smart-camera", "frame": item["frame"], "sequence": item["sequence"],
                "originNs": item["originNs"], "frameSha256": item["frameSha256"], "indicators": indicators, "checks": checks}
