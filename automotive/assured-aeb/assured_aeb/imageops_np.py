"""numpy image operations on BGRA8 frames for the U2 corruption stage and the U3 smart camera (WP-13 #4b;
review-wp13-imageops-np finding 1 §1.1).

This module is a bit-exact port of ``imageops.py``, which stays the reference. It has the same functions, signatures
and declared semantics, with ``bytes`` in and ``bytes`` out. It runs only in the pinned U2/U3 sensor venv (numpy
2.5.4; compat ``tools/sensor``). It is used only when bit-exact with the reference (decisions.md "WP-13 R-1 to R-7",
R-7), which the probe ``tests/imageops_np_probe.py`` establishes.

Three things carry over from the reference unchanged:
- the exposure and noise tables are built by the reference's own code;
- the box blur reproduces the reference's flat lane semantics, wrap and zero edges included;
- the moments use the same exact-integer expressions on Python ints.
"""

from __future__ import annotations

import math

import numpy as np

from . import imageops as _reference

MAX_BOX_LOG2 = _reference.MAX_BOX_LOG2


def _array(frame: bytes) -> np.ndarray:
    return np.frombuffer(frame, dtype=np.uint8)


def _restore_alpha(out: np.ndarray, original: np.ndarray) -> bytes:
    out[3::4] = original[3::4]
    return out.tobytes()


def exposure(frame: bytes, gain: float, offset: float) -> bytes:
    """``clamp(round(gain * v + offset))`` for every B, G and R byte (the reference's table)."""

    table = np.array([_reference._clamp8(round(gain * v + offset)) for v in range(256)], dtype=np.uint8)
    original = _array(frame)
    return _restore_alpha(np.take(table, original), original)


def occlusion(frame: bytes, width: int, x: int, y: int, w: int, h: int, value: int) -> bytes:
    """Set B, G and R of the rectangle ``[x, x + w) × [y, y + h)`` to ``value``. The rectangle must lie inside the frame,
    the only domain the camera chain admits."""

    original = _array(frame)
    if len(original) % (4 * width):
        raise ValueError("frame length is not a whole number of rows")
    height = len(original) // (4 * width)
    if not (0 <= x and 0 <= y and w > 0 and h > 0 and x + w <= width and y + h <= height and 0 <= value <= 255):
        raise ValueError("occlusion rectangle must lie within the frame and value in [0, 255]")
    out = original.copy().reshape(height, width, 4)
    out[y:y + h, x:x + w, 0:3] = value
    return out.reshape(-1).tobytes()


def noise_tables(std_level: float):
    return _reference.noise_tables(std_level)


def add_noise(frame: bytes, uniform: bytes, std_level: float) -> bytes:
    """Add the reference's Gaussian offset (selected by ``uniform``) to every B, G and R byte, clamped to [0, 255]."""

    if len(uniform) != len(frame):
        raise ValueError("one uniform byte per frame byte")
    _, _, offsets = _reference.noise_tables(std_level)
    original = _array(frame)
    noisy = original.astype(np.int16) + np.asarray(offsets, dtype=np.int16)[_array(uniform)]
    return _restore_alpha(np.clip(noisy, 0, 255).astype(np.uint8), original)


def _box_pass(values: np.ndarray, stride: int, log2_width: int) -> np.ndarray:
    """The reference's centred box pass on the flat array: out-of-range terms are 0, then floor division."""

    width = 1 << log2_width
    n = len(values)
    total = np.zeros(n, dtype=np.int32)
    for j in range(-(width // 2), width - width // 2):
        s = j * stride
        if s >= 0:
            if s < n:
                total[:n - s] += values[s:]
        elif -s < n:
            total[-s:] += values[:n + s]
    return total >> log2_width


def box_blur(frame: bytes, width: int, height: int, log2_width: int, channels: int = 4) -> bytes:
    """Separable centred box filter of width ``2**log2_width`` (1..MAX_BOX_LOG2), with the reference's declared edges."""

    if not 1 <= log2_width <= MAX_BOX_LOG2:
        raise ValueError(f"log2_width must be in [1, {MAX_BOX_LOG2}] (tool limit)")
    original = _array(frame)
    values = _box_pass(original.astype(np.int32), channels, log2_width)
    values = _box_pass(values, channels * width, log2_width)
    out = values.astype(np.uint8)
    return _restore_alpha(out, original) if channels == 4 else out.tobytes()


def luma(frame: bytes) -> bytes:
    """8-bit luma ``(77 R + 150 G + 29 B) >> 8`` of a BGRA8 frame."""

    pixels = _array(frame).reshape(-1, 4).astype(np.int32)
    return ((29 * pixels[:, 0] + 150 * pixels[:, 1] + 77 * pixels[:, 2]) >> 8).astype(np.uint8).tobytes()


def histogram(values: bytes) -> list[int]:
    return [int(c) for c in np.bincount(_array(values), minlength=256)]


def _moments_of(counts: list[int], n: int) -> tuple[int, float, float]:
    if n == 0:
        raise ValueError("no values")
    total = sum(v * c for v, c in enumerate(counts))
    squares = sum(v * v * c for v, c in enumerate(counts))
    return n, total / n, (squares * n - total * total) / (n * n)


def moments(values: bytes) -> tuple[int, float, float]:
    """``(n, mean, variance)`` of a byte string, from its exact integer histogram (the reference's expressions)."""

    return _moments_of(histogram(values), len(values))


def interior(plane: bytes, width: int, height: int, margin: int) -> bytes:
    if 2 * margin >= width or 2 * margin >= height:
        raise ValueError("the margin leaves no interior")
    return _array(plane).reshape(height, width)[margin:height - margin, margin:width - margin].tobytes()


def image_statistics(frame: bytes, width: int, height: int, *, stride: int, dark_level: int, bright_level: int,
                     sharpness_log2: int) -> dict[str, float]:
    """The smart-camera image statistics, composed as in the reference."""

    y = luma(frame)
    sample = y[::stride]
    counts = histogram(sample)
    n, mean, variance = _moments_of(counts, len(sample))
    margin = 1 << (sharpness_log2 - 1)
    y_inner = interior(y, width, height, margin)[::stride]
    blurred = interior(box_blur(y, width, height, sharpness_log2, channels=1), width, height, margin)[::stride]
    _, _, inner_variance = moments(y_inner)
    _, _, blurred_variance = moments(blurred)
    return {"meanLuma": mean, "stdLuma": math.sqrt(max(variance, 0.0)),
            "darkFraction": sum(counts[: dark_level + 1]) / n, "brightFraction": sum(counts[bright_level:]) / n,
            "highFrequencyVariance": inner_variance - blurred_variance}
