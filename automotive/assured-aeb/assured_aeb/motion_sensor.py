"""Modelled motion sensor (Phase 8 WP-05; FR-004, AD-32 option C; review-wp05 finding 1).

A declared model of a vehicle-motion sensor in the U2 ``vehicle-loop`` sensor-model stage (decisions.md §J). Its only
input is the adapter's snapshot-derived ``vehicle-motion`` item; its only output is the ``motion-evidence`` item of flow
F10 to the chassis zone. It turns the input into a measurement with declared sampling, additive Gaussian noise seeded
per simulation-time slot, quantisation and the AD-30 latency. It refuses evaluation-observer content and any other
flow, and it reads no observer, evaluation or oracle output (FR-021; DYN-002; V14).

Every model value is a protocol value with no default (AD-27; freeze-readiness class J needs a justification source
for each): ``MotionSensorParams.from_record`` refuses a record with a missing, extra or ill-typed member. Only
simulation time (integer nanoseconds) is used.

Time base (decisions.md "AD-30 delivery rule"; review-wp05 findings 3 and 4): the sampling grid and the noise key are
episode-relative, ``originNs - episodeOriginNs``, so the paired arms and repeats of one episode agree whatever the world
clock; the origin is bound once from the first frame (``bind_origin``) and nothing is sampled before it. The ``originNs``
and ``deliverAtNs`` stamps stay on the absolute world clock for the hub, U5 and offline joins. ``latencyNs`` covers the
element's WP-12 ``computeLatency``, so the sensor delay is declared once; the hub delivers at the first step boundary at
or after ``deliverAtNs`` (the latency is rounded up to whole steps).

Noise transform (finding 4, LOW-1): Box-Muller over two ``random()`` draws of a ``random.Random`` seeded with an integer
derived from SHA-256. CPython keeps the Mersenne Twister ``random()`` sequence for an integer seed stable across
versions; ``gauss()`` is not covered by that guarantee, so it is not used.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
import random
from typing import Any

PARAMS = "assured-aeb.motion-sensor/1"
OUTPUT = "assured-aeb.motion-evidence/1"
SOURCE = "motion-sensor-model"
INPUT_FLOW = "vehicle-motion"
NOISE_MODELS = ("gaussian-additive",)
PARAM_MEMBERS = frozenset({"schema", "samplingPeriodNs", "speedQuantumMps", "accelQuantumMps2", "noiseModel",
                           "speedNoiseStdMps", "accelNoiseStdMps2", "seed", "latencyNs"})
OUTPUT_MEMBERS = frozenset({"schema", "source", "sequence", "slot", "originNs", "deliverAtNs", "speedMps",
                            "accelForwardMps2", "modelDigest"})


def _int(value: Any) -> bool:
    return type(value) is int


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def canonical(record: dict[str, Any]) -> str:
    """Digest form of a record: numbers as floats except the integer members, sorted keys, no spaces."""

    ints = {"samplingPeriodNs", "seed", "latencyNs"}
    return json.dumps({k: (v if k in ints or type(v) not in (int, float) else float(v)) for k, v in record.items()},
                      sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class MotionSensorParams:
    """Validated model parameters and the digest of their record (provenance of every output)."""

    sampling_period_ns: int
    speed_quantum_mps: float
    accel_quantum_mps2: float
    noise_model: str
    speed_noise_std_mps: float
    accel_noise_std_mps2: float
    seed: int
    latency_ns: int
    digest: str

    @classmethod
    def from_record(cls, record: Any) -> "MotionSensorParams":
        if not isinstance(record, dict):
            raise ValueError("the motion-sensor record must be an object")
        if set(record) != PARAM_MEMBERS:
            raise ValueError(f"motion-sensor members must be exactly {sorted(PARAM_MEMBERS)}; got {sorted(record)}")
        if record["schema"] != PARAMS:
            raise ValueError(f"schema must be {PARAMS}")
        if not _int(record["samplingPeriodNs"]) or record["samplingPeriodNs"] <= 0:
            raise ValueError("samplingPeriodNs must be a positive integer (no default)")
        for name in ("speedQuantumMps", "accelQuantumMps2"):
            if not _number(record[name]) or record[name] <= 0:
                raise ValueError(f"{name} must be a positive finite number (no default)")
        if record["noiseModel"] not in NOISE_MODELS:
            raise ValueError(f"noiseModel must be one of {NOISE_MODELS}")
        for name in ("speedNoiseStdMps", "accelNoiseStdMps2"):
            if not _number(record[name]) or record[name] < 0:
                raise ValueError(f"{name} must be a non-negative finite number (no default)")
        if not _int(record["seed"]) or record["seed"] < 0:
            raise ValueError("seed must be a non-negative integer (no default; P-4 seed lists)")
        if not _int(record["latencyNs"]) or record["latencyNs"] < 0:
            raise ValueError("latencyNs must be a non-negative integer (no default; AD-30)")
        digest = "sha256:" + hashlib.sha256(canonical(record).encode()).hexdigest()
        return cls(record["samplingPeriodNs"], float(record["speedQuantumMps"]), float(record["accelQuantumMps2"]),
                   record["noiseModel"], float(record["speedNoiseStdMps"]), float(record["accelNoiseStdMps2"]),
                   record["seed"], record["latencyNs"], digest)


def noise(seed: int, slot: int, channel: str, std: float) -> float:
    """The Gaussian draw of ``channel`` at ``slot``: a function of seed and simulation-time slot only."""

    if std == 0.0:
        return 0.0
    key = hashlib.sha256(f"{PARAMS}|{seed}|{slot}|{channel}".encode()).digest()
    rng = random.Random(int.from_bytes(key[:8], "big"))
    u1, u2 = 1.0 - rng.random(), rng.random()  # u1 in (0, 1]: the logarithm is finite
    return std * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)  # Box-Muller, cosine branch


def quantise(value: float, quantum: float) -> float:
    """Round to an integer number of quanta, then to the quantum's decimal precision (no float artefacts)."""

    steps = round(value / quantum)
    places = max(0, -Decimal(repr(quantum)).as_tuple().exponent)
    return round(steps * quantum, places)


def check_output(item: Any) -> list[str]:
    """Closed output vocabulary of ``motion-evidence`` (empty when the item conforms)."""

    if not isinstance(item, dict):
        return ["not an object"]
    problems = []
    if set(item) != OUTPUT_MEMBERS:
        problems.append(f"members {sorted(set(item) ^ OUTPUT_MEMBERS)} outside the declared vocabulary")
    if item.get("schema") != OUTPUT or item.get("source") != SOURCE:
        problems.append("schema or source")
    return problems


class MotionSensor:
    """The modelled sensor: ``step(item)`` returns at most one ``motion-evidence`` item (or ``None``)."""

    def __init__(self, params: MotionSensorParams) -> None:
        if type(params) is not MotionSensorParams:
            raise TypeError("MotionSensorParams.from_record is required (no default parameters)")
        self.params = params
        self.episode_origin_ns: int | None = None
        self.last_slot: int | None = None
        self.last_origin_ns: int | None = None
        self.sequence = 0
        self.refused: dict[str, int] = {}

    def bind_origin(self, episode_origin_ns: int) -> None:
        """Bind the episode origin once, from the first frame; the same value is idempotent, another is refused."""

        if not _int(episode_origin_ns) or episode_origin_ns < 0:
            raise ValueError("the episode origin must be the integer ns world time of the episode's first frame")
        if self.episode_origin_ns is not None and self.episode_origin_ns != episode_origin_ns:
            raise ValueError(f"the episode origin is already bound to {self.episode_origin_ns}")
        self.episode_origin_ns = episode_origin_ns

    def _refuse(self, reason: str) -> None:
        self.refused[reason] = self.refused.get(reason, 0) + 1

    def step(self, item: Any) -> dict[str, Any] | None:
        """Sample one adapter ``vehicle-motion`` item (the first frame in each slot); refuse everything else."""

        if not isinstance(item, dict):
            self._refuse("not-an-item")
            return None
        if item.get("evaluationOnly") or str(item.get("schema", "")).startswith("xverse-compat.evaluation-observer"):
            self._refuse("evaluation-content")
            return None
        if item.get("flowId") != INPUT_FLOW:
            self._refuse("other-flow")
            return None
        value, origin = item.get("value"), item.get("originNs")
        speed = value.get("speedMps") if isinstance(value, dict) else None
        accel = value.get("accelForwardMps2") if isinstance(value, dict) else None
        if not (_int(origin) and origin >= 0 and _number(speed) and speed >= 0 and _number(accel)):
            self._refuse("malformed")
            return None
        if self.episode_origin_ns is None:
            self._refuse("origin-unbound")
            return None
        if origin < self.episode_origin_ns:
            self._refuse("before-episode")
            return None
        if self.last_origin_ns is not None and origin <= self.last_origin_ns:
            self._refuse("not-advancing")
            return None
        self.last_origin_ns = origin
        p = self.params
        slot = (origin - self.episode_origin_ns) // p.sampling_period_ns  # episode-relative grid
        if self.last_slot is not None and slot <= self.last_slot:
            return None  # this slot is already sampled: no sample between grid instants
        self.last_slot = slot
        measured_speed = max(0.0, speed + noise(p.seed, slot, "speed", p.speed_noise_std_mps))
        measured_accel = accel + noise(p.seed, slot, "accel", p.accel_noise_std_mps2)
        self.sequence += 1
        return {"schema": OUTPUT, "source": SOURCE, "sequence": self.sequence, "slot": slot, "originNs": origin,
                "deliverAtNs": origin + p.latency_ns, "speedMps": quantise(measured_speed, p.speed_quantum_mps),
                "accelForwardMps2": quantise(measured_accel, p.accel_quantum_mps2), "modelDigest": p.digest}
