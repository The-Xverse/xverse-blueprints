"""Reproducible tiny camera logits fixture, TEST-ONLY (WP-13 #3).

Standard-library protobuf helpers adapt compat ``tests/inference/minimal_onnx.py``. No onnx/torch/runtime is
imported. ``model_bytes`` needs compat's shared preprocessing module to bind its real code SHA, but passes the
explicit test NumPy version to avoid importing NumPy. Numeric values below are fixtures, not protocol choices.
"""
from __future__ import annotations

import math
from pathlib import Path
import struct
import sys

FMT = {"schema": "xverse-compat.camera-frame-format/1", "width": 16, "height": 16, "encoding": "bgra8"}
PREPROCESS = {"schema": "xverse-compat.preprocess/1", "input": {"width": 16, "height": 16, "encoding": "bgra8"},
              "crop": {"x": 0, "y": 0, "width": 16, "height": 16},
              "resize": {"method": "area-integer", "width": 8, "height": 8}, "channels": "rgb",
              "normalize": {"mean": [0.0, 0.0, 0.0], "std": [1.0, 1.0, 1.0]}}
POSTPROCESS = {"schema": "assured-aeb.postprocess/1", "outputs": {"occupancy": "occupancy_logit", "bins": "bin_logits"},
               "binLabels": ["no-obstacle", "overlap", "bin-0", "bin-1", "bin-2", "beyond"],
               "calibration": {"method": "temperature-scaling", "params": {"occupancyTemperature": 1.25, "binTemperature": 0.75}},
               "ood": {"method": "max-probability", "params": {}, "threshold": 0.9}}
SCHEMA = {"schema": "assured-aeb.model-schema/1",
          "inputs": [{"name": "image", "shape": [1, 3, 8, 8], "type": "tensor(float)"}],
          "outputs": [{"name": "occupancy_logit", "shape": [1, 1], "type": "tensor(float)"},
                      {"name": "bin_logits", "shape": [1, 6], "type": "tensor(float)"}]}


def varint(value):
    value &= (1 << 64) - 1
    out = bytearray()
    while True:
        byte, value = value & 127, value >> 7
        out.append(byte | (128 if value else 0))
        if not value:
            return bytes(out)


def integer(number, value):
    return varint(number << 3) + varint(value)


def blob(number, value):
    return varint(number << 3 | 2) + varint(len(value)) + value


def text(number, value):
    return blob(number, value.encode())


def weights(count, salt):
    return [struct.unpack("<f", struct.pack("<f", 0.05 * math.sin(salt + 1.37 * i)))[0] for i in range(count)]


W1, B1 = weights(54, 0.1), weights(2, 1.3)
WO, BO = weights(2, 2.1), [0.3]
WB, BB = weights(12, 3.9), [0.0, -0.1, 0.8, 0.0, -0.2, 0.1]


def tensor(name, dims, values):
    return b"".join(integer(1, d) for d in dims) + integer(2, 1) + text(8, name) + blob(9, struct.pack(f"<{len(values)}f", *values))


def value_info(name, dims):
    shape = b"".join(blob(1, integer(1, d)) for d in dims)
    return text(1, name) + blob(2, blob(1, integer(1, 1) + blob(2, shape)))


def node(operator, inputs, outputs, name, attrs=None):
    out = b"".join(text(1, v) for v in inputs) + b"".join(text(2, v) for v in outputs) + text(3, name) + text(4, operator)
    for key, values in (attrs or {}).items():
        out += blob(5, text(1, key) + b"".join(integer(8, v) for v in values) + integer(20, 7))
    return out


def graph_bytes():
    nodes = [node("Conv", ["image", "W1", "B1"], ["conv"], "conv", {"kernel_shape": [3, 3]}),
             node("Relu", ["conv"], ["relu"], "relu"), node("GlobalAveragePool", ["relu"], ["pooled"], "pool"),
             node("Flatten", ["pooled"], ["flat"], "flatten"),
             node("Gemm", ["flat", "WO", "BO"], ["occupancy_logit"], "occupancy"),
             node("Gemm", ["flat", "WB", "BB"], ["bin_logits"], "bins")]
    initializers = [tensor("W1", (2, 3, 3, 3), W1), tensor("B1", (2,), B1), tensor("WO", (2, 1), WO),
                    tensor("BO", (1,), BO), tensor("WB", (2, 6), WB), tensor("BB", (6,), BB)]
    return (b"".join(blob(1, n) for n in nodes) + text(2, "tiny-camera-logits") + b"".join(blob(5, v) for v in initializers)
            + blob(11, value_info("image", (1, 3, 8, 8)))
            + blob(12, value_info("occupancy_logit", (1, 1))) + blob(12, value_info("bin_logits", (1, 6))))


def model_bytes(*, metadata_override=None, graph_override=None):
    from xverse_compat.inference import preprocess as PRE
    from assured_aeb import postprocess as PP

    metadata = {**PRE.binding(PRE.load_params(PREPROCESS), "2.5.4"), **PP.metadata_entry(POSTPROCESS),
                "purpose": "WP-13 TEST-ONLY camera logits fixture; not a thesis model"}
    if metadata_override:
        metadata.update(metadata_override)
    body = (integer(1, 7) + text(2, "xverse-blueprints-test-fixture") + text(3, "1")
            + blob(7, graph_bytes() if graph_override is None else graph_override)
            + blob(8, text(1, "") + integer(2, 13)))
    return body + b"".join(blob(14, text(1, key) + text(2, value)) for key, value in sorted(metadata.items()))


def reference(np, image):
    """Independent float64 NumPy forward calculation of the fixed fixture (not the runtime path)."""
    conv = np.zeros((2, 6, 6), dtype=np.float64)
    kernel = np.asarray(W1, dtype=np.float64).reshape(2, 3, 3, 3)
    for feature in range(2):
        for y in range(6):
            for x in range(6):
                conv[feature, y, x] = float((image[0, :, y:y + 3, x:x + 3] * kernel[feature]).sum()) + B1[feature]
    pooled = np.maximum(conv, 0.0).mean(axis=(1, 2))
    # Round the initializer biases exactly as the float32 ONNX tensors do.
    occupancy = pooled @ np.asarray(WO, dtype=np.float64).reshape(2, 1) + np.asarray(BO, dtype=np.float32).astype(np.float64)
    bins = pooled @ np.asarray(WB, dtype=np.float64).reshape(2, 6) + np.asarray(BB, dtype=np.float32).astype(np.float64)
    return {"occupancy_logit": occupancy.reshape(1, 1), "bin_logits": bins.reshape(1, 6)}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: make_camera_model.py OUT.onnx (put compat/src and assured-aeb on PYTHONPATH)")
    Path(sys.argv[1]).write_bytes(model_bytes())
