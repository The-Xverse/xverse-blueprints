"""Static ONNX contract inspection before a U4 session exists (WP-13 #3, review finding 2).

This is a deliberately small, fail-closed protobuf reader, not a general ONNX parser. It accepts the local
IR-7/opset-13 float32 V-1 graph subset and rejects external tensors, subgraphs, custom domains, ambiguous identities
and unsupported fields. Field numbers follow the existing compat ``tests/inference/minimal_onnx.py`` writer.
Parsing and allocation are bounded by the exact bytes already checked by the pinned digest-first loader.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import struct
from typing import Any

V1_OPERATORS = frozenset({"Conv", "Relu", "GlobalAveragePool", "Flatten", "Gemm"})
ATTRIBUTES = {
    "Conv": {"kernel_shape": 7, "strides": 7, "pads": 7, "dilations": 7, "group": 2, "auto_pad": 3},
    "Relu": {}, "GlobalAveragePool": {}, "Flatten": {"axis": 2},
    "Gemm": {"alpha": 1, "beta": 1, "transA": 2, "transB": 2},
}


def _varint(data: bytes, offset: int) -> tuple[int, int]:
    start, value = offset, 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("truncated protobuf varint")
        byte = data[offset]
        offset += 1
        if shift == 63 and byte > 1:
            raise ValueError("protobuf varint exceeds 64 bits")
        value |= (byte & 127) << shift
        if byte < 128:
            if offset - start > 1 and byte == 0:
                raise ValueError("non-canonical protobuf varint")
            return value, offset
    raise ValueError("unterminated protobuf varint")


def fields(data: bytes) -> list[tuple[int, int, Any]]:
    if type(data) is not bytes:
        raise TypeError("verified model bytes are required")
    out, offset = [], 0
    while offset < len(data):
        key, offset = _varint(data, offset)
        number, wire = key >> 3, key & 7
        if not 0 < number < 1 << 29:
            raise ValueError("invalid protobuf field number")
        if wire == 0:
            value, offset = _varint(data, offset)
        elif wire in (1, 2, 5):
            if wire == 2:
                length, offset = _varint(data, offset)
            else:
                length = 8 if wire == 1 else 4
            end = offset + length
            if end > len(data):
                raise ValueError("truncated protobuf field")
            value, offset = data[offset:end], end
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        out.append((number, wire, value))
    return out


def _only(parts, allowed, label):
    if any(number not in allowed for number, _, _ in parts):
        raise ValueError(f"unsupported {label} field")


def _values(parts, number, wire):
    selected = [(w, v) for n, w, v in parts if n == number]
    if any(w != wire for w, _ in selected):
        raise ValueError(f"wrong wire type for field {number}")
    return [v for _, v in selected]


def _one(parts, number, wire, *, optional=False):
    values = _values(parts, number, wire)
    if len(values) != 1:
        if optional and not values:
            return None
        raise ValueError(f"field {number} must appear exactly once")
    return values[0]


def _text(value, label):
    try:
        out = value.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ValueError(f"invalid UTF-8 in {label}") from error
    if not out or "\x00" in out:
        raise ValueError(f"empty or invalid {label}")
    return out


def _integers(parts, number):
    out = []
    for n, wire, value in parts:
        if n != number:
            continue
        if wire == 0:
            out.append(value)
        elif wire == 2:
            offset = 0
            while offset < len(value):
                item, offset = _varint(value, offset)
                out.append(item)
        else:
            raise ValueError("unsupported packed integer encoding")
    return out


def _io(value):
    info = fields(value)
    _only(info, {1, 2, 3}, "value-info")
    name = _text(_one(info, 1, 2), "I/O name")
    type_info = fields(_one(info, 2, 2))
    _only(type_info, {1}, "type")
    tensor = fields(_one(type_info, 1, 2))
    _only(tensor, {1, 2}, "tensor type")
    if _one(tensor, 1, 0) != 1:
        raise ValueError("only float32 tensor I/O is supported")
    shape = fields(_one(tensor, 2, 2))
    _only(shape, {1}, "shape")
    dims = []
    for raw in _values(shape, 1, 2):
        dim = fields(raw)
        _only(dim, {1}, "static dimension")
        value = _one(dim, 1, 0)
        if not 0 < value < 1 << 63:
            raise ValueError("model dimensions must be static positive integers")
        dims.append(value)
    if not dims:
        raise ValueError("scalar I/O is unsupported")
    return name, dims, "tensor(float)"


def _tensor(value):
    parts = fields(value)
    if _values(parts, 13, 2) or (_one(parts, 14, 0, optional=True) or 0) != 0:
        raise ValueError("external tensor data is forbidden")
    _only(parts, {1, 2, 4, 8, 9, 12, 14}, "initializer")
    name = _text(_one(parts, 8, 2), "initializer name")
    dims = _integers(parts, 1)
    if not dims or any(not 0 < v < 1 << 63 for v in dims) or _one(parts, 2, 0) != 1:
        raise ValueError("only static float32 initializers are supported")
    raw = _one(parts, 9, 2, optional=True)
    floats = []
    for number, wire, value in parts:
        if number != 4:
            continue
        if wire not in (2, 5) or len(value) % 4:
            raise ValueError("unsupported float initializer encoding")
        floats.extend(v[0] for v in struct.iter_unpack("<f", value))
    if raw is not None:
        if floats or len(raw) % 4:
            raise ValueError("ambiguous float initializer data")
        floats = [v[0] for v in struct.iter_unpack("<f", raw)]
    count = 1
    for dim in dims:
        if dim > len(floats) // count:  # never grow a declared-size product beyond bytes that actually exist
            raise ValueError("initializer shape/data mismatch")
        count *= dim
    if len(floats) != count or not all(math.isfinite(v) for v in floats):
        raise ValueError("initializer shape/data mismatch or non-finite weights")
    return name


def _attribute(value, operator):
    parts = fields(value)
    _only(parts, {1, 2, 3, 4, 8, 13, 20}, "V-1 attribute")
    name = _text(_one(parts, 1, 2), "attribute name")
    kind = _one(parts, 20, 0)
    if ATTRIBUTES[operator].get(name) != kind:
        raise ValueError(f"unsupported {operator} attribute {name}")
    payloads = {n for n, _, _ in parts} & {2, 3, 4, 8}
    expected = {1: 2, 2: 3, 3: 4, 7: 8}[kind]
    if payloads != {expected}:
        raise ValueError("ambiguous attribute value")
    if kind == 1:
        if not math.isfinite(struct.unpack("<f", _one(parts, 2, 5))[0]):
            raise ValueError("non-finite attribute")
    elif kind == 2:
        _one(parts, 3, 0)
    elif kind == 3:
        _text(_one(parts, 4, 2), "attribute string")
    elif not _integers(parts, 8):
        raise ValueError("empty integer attribute")
    return name


@dataclass(frozen=True)
class ModelContract:
    metadata: dict[str, str]
    inputs: list
    outputs: list
    operators: tuple[str, ...]


def inspect(data: bytes) -> ModelContract:
    """Inspect one digest-verified local V-1 graph without importing ONNX Runtime or NumPy."""
    model = fields(data)
    _only(model, {1, 2, 3, 4, 5, 6, 7, 8, 14}, "model")
    if _one(model, 1, 0) != 7:
        raise ValueError("the local V-1 model contract requires IR 7")
    for number, wire in ((2, 2), (3, 2), (4, 2), (5, 0), (6, 2)):
        _one(model, number, wire, optional=True)
    opsets = _values(model, 8, 2)
    if len(opsets) != 1:
        raise ValueError("exactly one default-domain opset is required")
    opset = fields(opsets[0])
    _only(opset, {1, 2}, "opset")
    if (_one(opset, 1, 2, optional=True) or b"") != b"" or _one(opset, 2, 0) != 13:
        raise ValueError("only the default-domain opset 13 is supported")
    metadata = {}
    for item in _values(model, 14, 2):
        entry = fields(item)
        _only(entry, {1, 2}, "metadata")
        key = _text(_one(entry, 1, 2), "metadata key")
        value = _one(entry, 2, 2).decode("utf-8", errors="strict")
        if key in metadata:
            raise ValueError("duplicate metadata identity")
        metadata[key] = value
    graph = fields(_one(model, 7, 2))
    _only(graph, {1, 2, 5, 10, 11, 12, 13}, "graph")
    _one(graph, 2, 2, optional=True)
    _one(graph, 10, 2, optional=True)
    inputs, outputs = [_io(v) for v in _values(graph, 11, 2)], [_io(v) for v in _values(graph, 12, 2)]
    names = [n for n, _, _ in inputs + outputs]
    if len(inputs) != 1 or len(outputs) != 2 or len(set(names)) != len(names):
        raise ValueError("one input, two outputs and unambiguous I/O identities are required")
    available = {inputs[0][0]}
    for value in _values(graph, 5, 2):
        name = _tensor(value)
        if name in available:
            raise ValueError("duplicate initializer or input identity")
        available.add(name)
    operators = []
    for value in _values(graph, 1, 2):
        node = fields(value)
        _only(node, {1, 2, 3, 4, 5, 6, 7}, "V-1 node")
        operator = _text(_one(node, 4, 2), "operator")
        if operator not in V1_OPERATORS or (_one(node, 7, 2, optional=True) or b"") != b"":
            raise ValueError("unsupported operator or custom domain")
        for number in (3, 6):
            _one(node, number, 2, optional=True)
        sources = [_text(v, "node input") for v in _values(node, 1, 2)]
        targets = [_text(v, "node output") for v in _values(node, 2, 2)]
        if not sources or any(n not in available for n in sources) or not targets:
            raise ValueError("graph is not an explicit topologically ordered V-1 graph")
        if len(set(targets)) != len(targets) or any(n in available for n in targets):
            raise ValueError("duplicate graph value identity")
        attributes = [_attribute(v, operator) for v in _values(node, 5, 2)]
        if len(set(attributes)) != len(attributes):
            raise ValueError("duplicate attribute identity")
        available.update(targets)
        operators.append(operator)
    if not operators or any(n not in available for n, _, _ in outputs):
        raise ValueError("model outputs are not produced by the V-1 graph")
    for value in _values(graph, 13, 2):
        _io(value)  # only the same static float32 value-info subset is supported
    return ModelContract(metadata, inputs, outputs, tuple(operators))
