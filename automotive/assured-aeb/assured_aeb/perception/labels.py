"""Offline perception labels from observer v2 records (WP-09 increment #1; review-wp09-labels finding 1 §1.1-1.4).

Labels are computed per CARLA frame from the evaluation-only observer v2 stream (``xverse-compat.evaluation-observer/2``)
and the declared camera mount, joined to the run's camera items by frame. They are used offline only, for training,
calibration and characterisation (FR-005, FR-021, DYN-002): no runtime module imports this one (a test asserts it).

Planar model on the AD-04 flat straight road: pitch and roll are ignored. CARLA's frame: x forward, y right, z up; an
actor's forward vector is ``(cos yaw, sin yaw)`` and its right vector ``(-sin yaw, cos yaw)``. Every corridor, bin and
range value is a protocol value from ``LabelParams`` with no default.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

LABEL_PARAMS = "assured-aeb.perception-label-params/1"
LABEL = "assured-aeb.perception-label/1"
OBSERVER_SCHEMA = "xverse-compat.evaluation-observer/2"
EGO_ROLE, TARGET_ROLE = "xverse-lite-ego", "xverse-lite-target"
LABEL_CODE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def canonical(record: Any) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True)
class LabelParams:
    half_width_m: float
    max_range_m: float
    bin_edges_m: tuple[float, ...]
    camera_mount_m: tuple[float, float, float]
    fov_deg: float
    width: int
    height: int
    digest: str

    @classmethod
    def from_record(cls, record: Any) -> "LabelParams":
        if not isinstance(record, dict) or set(record) != {"schema", "corridor", "distanceBinEdgesM", "camera"}:
            raise ValueError(f"{LABEL_PARAMS} members must be exactly schema, corridor, distanceBinEdgesM, camera")
        if record["schema"] != LABEL_PARAMS:
            raise ValueError(f"schema must be {LABEL_PARAMS}")
        corridor, edges, camera = record["corridor"], record["distanceBinEdgesM"], record["camera"]
        if not isinstance(corridor, dict) or set(corridor) != {"halfWidthM", "maxRangeM"} or \
                not all(_number(v) and v > 0 for v in corridor.values()):
            raise ValueError("corridor must be exactly {halfWidthM, maxRangeM}, both > 0 (TODO: author decision)")
        if not isinstance(edges, list) or not edges or not all(_number(e) and e > 0 for e in edges) or \
                any(b <= a for a, b in zip(edges, edges[1:])):
            raise ValueError("distanceBinEdgesM must be a non-empty strictly increasing list of positive numbers (TODO)")
        if not isinstance(camera, dict) or set(camera) != {"mountM", "fovDeg", "width", "height"}:
            raise ValueError("camera must be exactly {mountM, fovDeg, width, height} (the configured camera)")
        mount = camera["mountM"]
        if not (isinstance(mount, list) and len(mount) == 3 and all(_number(v) for v in mount)) or \
                not (_number(camera["fovDeg"]) and 0 < camera["fovDeg"] < 180) or \
                not all(type(camera[k]) is int and camera[k] > 0 for k in ("width", "height")):
            raise ValueError("camera needs a 3-vector mountM, 0 < fovDeg < 180 and positive integer width and height")
        return cls(float(corridor["halfWidthM"]), float(corridor["maxRangeM"]), tuple(float(e) for e in edges),
                   tuple(float(v) for v in mount), float(camera["fovDeg"]), camera["width"], camera["height"],
                   hashlib.sha256(canonical(record)).hexdigest())


# --------------------------------------------------------------------------------------------------
# Observer v2 parsing
# --------------------------------------------------------------------------------------------------

@dataclass
class ObserverData:
    sha256: str
    frames: dict[int, tuple[int, dict[str, Any]]]  # frame -> (1-based line, record)
    resolutions: dict[str, list[tuple[int, dict[str, Any] | None]]]  # role -> [(frame, boundingBox or None)]
    duplicates: int


def parse_observer(data: bytes) -> ObserverData:
    """Parse an observer v2 file; refuse anything that is not an evaluation-only v2 stream."""

    lines = data.decode("utf-8").splitlines()
    if not lines:
        raise ValueError("empty observer file")
    header = json.loads(lines[0])
    if not (isinstance(header, dict) and header.get("header") is True and header.get("schema") == OBSERVER_SCHEMA
            and header.get("evaluationOnly") is True):
        raise ValueError(f"the observer file must start with an evaluation-only {OBSERVER_SCHEMA} header")
    frames: dict[int, tuple[int, dict[str, Any]]] = {}
    resolutions: dict[str, list[tuple[int, dict[str, Any] | None]]] = {}
    duplicates = 0
    for number, line in enumerate(lines[1:], start=2):
        record = json.loads(line)
        if record.get("footer"):
            continue
        if record.get("resolution"):
            box = record.get("boundingBox") if record.get("boundingBoxStatus") == "observed" else None
            resolutions.setdefault(record["role"], []).append((record["frame"], box))
        elif type(record.get("frame")) is int:
            if record["frame"] in frames:
                duplicates += 1
            else:
                frames[record["frame"]] = (number, record)
    for entries in resolutions.values():
        entries.sort(key=lambda item: item[0])
    return ObserverData(hashlib.sha256(data).hexdigest(), frames, resolutions, duplicates)


def _box_at(data: ObserverData, role: str, frame: int) -> dict[str, Any] | None:
    box = None
    for resolved_at, candidate in data.resolutions.get(role, []):
        if resolved_at > frame:
            break
        box = candidate
    if box is None:
        return None
    extent, offset = box.get("extentM"), box.get("locationM")
    if not (isinstance(extent, list) and isinstance(offset, list) and len(extent) == 3 and len(offset) == 3
            and all(_number(v) for v in extent + offset)):
        return None
    return box


# --------------------------------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------------------------------

def _axes(yaw_deg: float) -> tuple[tuple[float, float], tuple[float, float]]:
    yaw = math.radians(yaw_deg)
    return (math.cos(yaw), math.sin(yaw)), (-math.sin(yaw), math.cos(yaw))


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _project(points, axis) -> tuple[float, float]:
    values = [_dot(p, axis) for p in points]
    return min(values), max(values)


def rectangles_intersect(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool:
    """Separating-axis test for two rectangles given by their four corners in order (touching counts)."""

    for poly in (a, b):
        for i in range(2):
            edge = (poly[i + 1][0] - poly[i][0], poly[i + 1][1] - poly[i][1])
            axis = (-edge[1], edge[0])
            (a0, a1), (b0, b1) = _project(a, axis), _project(b, axis)
            if a1 < b0 or b1 < a0:
                return False
    return True


def geometry(ego: dict[str, Any], ego_box: dict[str, Any], target: dict[str, Any], target_box: dict[str, Any],
             params: LabelParams) -> dict[str, Any]:
    """Distance, corridor and visibility of the target in the ego frame (finding 1 §1.2)."""

    f_e, r_e = _axes(ego["rotationDeg"][1])
    f_t, r_t = _axes(target["rotationDeg"][1])
    ex, ey, ez = ego["location"]
    loc_t, ext_t = target_box["locationM"], target_box["extentM"]
    cx = target["location"][0] + loc_t[0] * f_t[0] + loc_t[1] * r_t[0]
    cy = target["location"][1] + loc_t[0] * f_t[1] + loc_t[1] * r_t[1]
    corners_world = [(cx + sx * ext_t[0] * f_t[0] + sy * ext_t[1] * r_t[0], cy + sx * ext_t[0] * f_t[1] + sy * ext_t[1] * r_t[1])
                     for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
    corners = [(_dot((x - ex, y - ey), f_e), _dot((x - ex, y - ey), r_e)) for x, y in corners_world]
    x_front = ego_box["locationM"][0] + ego_box["extentM"][0]
    nearest = min(corners, key=lambda c: c[0])
    distance = nearest[0] - x_front
    corridor = [(x_front, -params.half_width_m), (x_front + params.max_range_m, -params.half_width_m),
                (x_front + params.max_range_m, params.half_width_m), (x_front, params.half_width_m)]
    in_corridor = rectangles_intersect(corridor, corners)
    mx, my, mz = params.camera_mount_m
    dx, dy = nearest[0] - mx, nearest[1] - my
    half_h = math.radians(params.fov_deg) / 2
    half_v = math.atan(math.tan(half_h) * params.height / params.width)  # pinhole vertical half field of view
    z_centre = (target["location"][2] + loc_t[2]) - (ez + mz)
    visible = dx > 0 and abs(math.atan2(dy, dx)) <= half_h and \
        z_centre - ext_t[2] <= dx * math.tan(half_v) and z_centre + ext_t[2] >= -dx * math.tan(half_v)
    return {"distanceM": distance, "inCorridor": in_corridor, "visible": visible}


def distance_bin(obstacle: bool, distance: float | None, edges: tuple[float, ...]) -> str:
    if not obstacle or distance is None:
        return "no-obstacle"
    if distance <= 0:
        return "overlap"
    for index, edge in enumerate(edges):
        if distance < edge:
            return f"bin-{index}"
    return "beyond"


# --------------------------------------------------------------------------------------------------
# Join
# --------------------------------------------------------------------------------------------------

def label_run(observer: bytes, camera_items: Iterable[dict[str, Any]], params: LabelParams, *,
              target_declared: bool) -> tuple[list[dict[str, Any]], Counter]:
    """Label every camera frame of one run; return ``(labels, exclusions by reason)``. No pixels are read."""

    if type(params) is not LabelParams:
        raise TypeError("LabelParams.from_record is required (no default parameters)")
    data = parse_observer(observer)
    labels, excluded = [], Counter()
    for item in camera_items:
        frame, raw = item.get("frame"), item.get("rawSha256")
        if frame not in data.frames:
            excluded["no-observer-record"] += 1
            continue
        line, record = data.frames[frame]
        roles = record.get("roles", {})
        ego, target = roles.get(EGO_ROLE, {}), roles.get(TARGET_ROLE, {"status": "absent"})
        if ego.get("status") != "observed":
            excluded["ego-not-observed"] += 1
            continue
        ego_box = _box_at(data, EGO_ROLE, frame)
        if ego_box is None:
            excluded["ego-bounding-box"] += 1
            continue
        if not target_declared:
            if target.get("status") != "absent":
                excluded["undeclared-target-present"] += 1
                continue
            result = {"distanceM": None, "inCorridor": False, "visible": False}
        else:
            if target.get("status") != "observed":
                excluded[f"target-{target.get('status', 'missing')}"] += 1
                continue
            target_box = _box_at(data, TARGET_ROLE, frame)
            if target_box is None:
                excluded["target-bounding-box"] += 1
                continue
            result = geometry(ego, ego_box, target, target_box, params)
        obstacle = result["inCorridor"] and result["visible"]
        labels.append({"schema": LABEL, "frame": frame, "simElapsedNs": record.get("simElapsedNs"), "rawSha256": raw,
                       "inCorridor": result["inCorridor"], "visible": result["visible"], "obstacle": obstacle,
                       "distanceM": result["distanceM"], "distanceBin": distance_bin(obstacle, result["distanceM"], params.bin_edges_m),
                       "provenance": {"observerSha256": data.sha256, "observerLine": line, "labelCodeSha256": LABEL_CODE_SHA256,
                                      "labelParamsDigest": params.digest}})
    excluded["duplicate-observer-frames"] += data.duplicates
    return labels, +excluded
