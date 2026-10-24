"""Non-executable deterministic float32 development weight format; no pickle or framework import."""
from __future__ import annotations

import math
from pathlib import Path
import struct

from .training_io import canonical, digest, exact, integer, parse_json, read_regular, record_digest, require, sha
from .training_network import parameter_shapes

SCHEMA = "assured-aeb.training-weights/1"
DTYPE = "float32-le"


def _finite(data):
    require(len(data) % 4 == 0 and all(math.isfinite(value[0]) for value in struct.iter_unpack("<f", data)),
            "weights must contain only finite little-endian float32 values")


def encode_weights(named_bytes, job, stage_sha256):
    """Each trusted tensor extraction supplies bytes; shapes/names come only from admitted architecture."""
    digest(stage_sha256, "stage identity")
    shapes = parameter_shapes(job)
    require(type(named_bytes) is dict and set(named_bytes) == set(shapes), "exact named parameter bytes required")
    tensors, pieces, offset = [], [], 0
    maximum = job.record()["environments"]["limits"]["outputBytes"]
    for name, shape in shapes.items():
        data = named_bytes[name]
        count = math.prod(shape)
        require(type(data) is bytes and len(data) == count * 4, "parameter byte length differs from admitted shape")
        require(offset + len(data) <= maximum, "weight blob exceeds output limit")
        _finite(data)
        tensors.append({"name": name, "dtype": DTYPE, "shape": list(shape), "byteOffset": offset,
                        "byteLength": len(data), "sha256": sha(data)})
        pieces.append(data)
        offset += len(data)
    blob = b"".join(pieces)
    named = [{key: tensor[key] for key in ("name", "dtype", "shape", "sha256")} for tensor in tensors]
    descriptor = {"schema": SCHEMA, "jobSha256": job.sha256, "stageSha256": stage_sha256,
                  "weightsSha256": sha(blob), "namedWeightsSha256": record_digest(named), "tensors": tensors}
    encoded = canonical(descriptor)
    require(len(encoded) + len(blob) <= maximum, "weight descriptor/blob exceed output limit")
    return encoded, blob


def decode_weights(descriptor_bytes, blob, job, *, stage_sha256):
    """Validate before any tensor creation. Returns private names/shapes/bytes, never executable objects."""
    limits = job.record()["environments"]["limits"]
    require(type(blob) is bytes and len(blob) <= limits["outputBytes"], "bounded weight bytes required")
    descriptor = parse_json(descriptor_bytes, max_bytes=limits["outputBytes"], canonical_required=True)
    require(len(blob) + len(descriptor_bytes) <= limits["outputBytes"], "weight package exceeds output limit")
    exact(descriptor, {"schema", "jobSha256", "stageSha256", "weightsSha256", "namedWeightsSha256", "tensors"}, "weights")
    require(descriptor["schema"] == SCHEMA and descriptor["jobSha256"] == job.sha256, "weight schema/job mismatch")
    require(descriptor["stageSha256"] == digest(stage_sha256, "stage identity"), "weight stage mismatch")
    require(digest(descriptor["weightsSha256"], "weight blob digest") == sha(blob), "weight blob digest mismatch")
    shapes = parameter_shapes(job)
    tensors = descriptor["tensors"]
    require(type(tensors) is list and len(tensors) == len(shapes), "exact tensor table required")
    result, named, offset = {}, [], 0
    for tensor, (name, shape) in zip(tensors, shapes.items()):
        exact(tensor, {"name", "dtype", "shape", "byteOffset", "byteLength", "sha256"}, "tensor descriptor")
        require(tensor["name"] == name and tensor["dtype"] == DTYPE, "tensor name/order/dtype mismatch")
        require(type(tensor["shape"]) is list and len(tensor["shape"]) == len(shape), "exact tensor rank required")
        for actual, expected in zip(tensor["shape"], shape):
            require(integer(actual, "tensor dimension", 1, expected) == expected, "tensor shape mismatch")
        size = math.prod(shape) * 4
        require(integer(tensor["byteOffset"], "tensor offset", 0, len(blob)) == offset, "noncontiguous tensor offset")
        require(integer(tensor["byteLength"], "tensor length", 1, len(blob)) == size and offset + size <= len(blob),
                "tensor byte range mismatch")
        data = blob[offset:offset + size]
        require(digest(tensor["sha256"], "tensor digest") == sha(data), "tensor digest mismatch")
        _finite(data)
        result[name] = {"shape": shape, "data": data}
        named.append({key: tensor[key] for key in ("name", "dtype", "shape", "sha256")})
        offset += size
    require(offset == len(blob) == job.parameter_count * 4, "trailing or missing weight bytes")
    require(digest(descriptor["namedWeightsSha256"], "named weight digest") == record_digest(named), "named weight digest mismatch")
    return result


def read_weights(directory, job, *, stage_sha256, descriptor_sha256, weights_sha256):
    root = Path(directory)
    maximum = job.record()["environments"]["limits"]["outputBytes"]
    descriptor = read_regular(root / "weights.json", maximum)
    require(sha(descriptor) == digest(descriptor_sha256, "expected descriptor digest"), "expected weight descriptor digest mismatch")
    blob = read_regular(root / "weights.f32", maximum)
    require(sha(blob) == digest(weights_sha256, "expected weights digest"), "expected weight blob digest mismatch")
    return decode_weights(descriptor, blob, job, stage_sha256=stage_sha256)
