"""Standard-library image operations on BGRA8 frames for the U2 corruption stage and the U3 smart camera (WP-06/WP-07;
review-wp07 finding 1 §1.1).

No per-pixel Python loop: every operation is a C-level byte operation (``bytes.translate`` tables, extended-slice
assignment, ``bytes.count``) or arithmetic on *lane-packed* integers. A frame of N bytes is spread to N little-endian
16-bit lanes (``spread``); integer addition, shifts and masks then act on every lane at once, because each lane value is
kept below 2**16 so no carry crosses a lane. Alpha (every fourth byte) is preserved by every transform.
"""

from __future__ import annotations

from functools import lru_cache
import math
from statistics import NormalDist

LANE_BITS = 16
#: Tool limit on box widths (2**4 = 16 pixels): finding 3 measured 49 ms at 2**2, 151 ms at 2**5 and 913 ms at 2**8 on
#: 800 x 600 BGRA against a 50 ms simulator step. An engineering bound of this tool, not a protocol value; the per-frame
#: host budget is a D-4c measurement (review-wp07 finding 4, MEDIUM-1).
MAX_BOX_LOG2 = 4


def spread(data: bytes) -> int:
    """``data`` as an integer with one little-endian 16-bit lane per byte (the byte in the low half)."""

    lanes = bytearray(2 * len(data))
    lanes[0::2] = data
    return int.from_bytes(lanes, "little")


def low_bytes(value: int, count: int) -> bytes:
    """The low byte of each of ``count`` lanes of ``value``."""

    return value.to_bytes(2 * count, "little")[0::2]


@lru_cache(maxsize=16)
def lane_low_mask(count: int) -> int:
    return int.from_bytes(b"\xff\x00" * count, "little")


@lru_cache(maxsize=16)
def lane_full_mask(count: int) -> int:
    return (1 << (LANE_BITS * count)) - 1


def _restore_alpha(out: bytearray, original: bytes) -> bytes:
    out[3::4] = original[3::4]
    return bytes(out)


def _clamp8(value: int) -> int:
    return 0 if value < 0 else 255 if value > 255 else value


def exposure(frame: bytes, gain: float, offset: float) -> bytes:
    """``clamp(round(gain * v + offset))`` for every B, G and R byte (Python ``round``: ties to even)."""

    table = bytes(_clamp8(round(gain * v + offset)) for v in range(256))
    return _restore_alpha(bytearray(frame.translate(table)), frame)


def occlusion(frame: bytes, width: int, x: int, y: int, w: int, h: int, value: int) -> bytes:
    """Set B, G and R of the rectangle ``[x, x + w) × [y, y + h)`` to ``value``."""

    out = bytearray(frame)
    fill = bytes([value]) * w
    for row in range(y, y + h):
        start = (row * width + x) * 4
        segment = out[start:start + 4 * w]
        segment[0::4] = fill
        segment[1::4] = fill
        segment[2::4] = fill
        out[start:start + 4 * w] = segment
    return bytes(out)


@lru_cache(maxsize=64)
def noise_tables(std_level: float) -> tuple[bytes, bytes, tuple[int, ...]]:
    """The 256-entry inverse-CDF table of a Gaussian of ``std_level`` (8-bit levels), clamped to ±255, as the low and
    high bytes of ``offset + 256`` (the lane bias that keeps every lane non-negative).

    Declared fidelity: 256 equiprobable levels, so the noise is truncated at about ±2.9 sigma (``inv_cdf(0.5 / 256)``)
    and rounded to whole levels (for example extremes ±58 at sigma 20, spread 19.95). Reproducibility depends on the
    interpreter pin and the host libm (``math.log``, ``math.sqrt`` in ``NormalDist.inv_cdf``)."""

    dist = NormalDist(0.0, std_level)
    offsets = tuple(max(-255, min(255, round(dist.inv_cdf((k + 0.5) / 256)))) for k in range(256))
    low = bytes((o + 256) & 0xFF for o in offsets)
    high = bytes((o + 256) >> 8 for o in offsets)
    return low, high, offsets


_KEEP = bytes(0xFF if i == 1 else 0 for i in range(256))  # lane high byte 1: value in [0, 255]
_SATURATE = bytes(0xFF if i >= 2 else 0 for i in range(256))  # lane high byte >= 2: value above 255


def add_noise(frame: bytes, uniform: bytes, std_level: float) -> bytes:
    """Add a Gaussian offset to every B, G and R byte: ``uniform`` (one seeded byte per frame byte) selects the offset
    through ``noise_tables``; the sum ``v + offset + 256`` lies in [1, 766] (no carry), then is clamped to [0, 255]."""

    if len(uniform) != len(frame):
        raise ValueError("one uniform byte per frame byte")
    low_table, high_table, _ = noise_tables(std_level)
    n = len(frame)
    noise_lanes = bytearray(2 * n)
    noise_lanes[0::2] = uniform.translate(low_table)
    noise_lanes[1::2] = uniform.translate(high_table)
    total = (spread(frame) + int.from_bytes(noise_lanes, "little")).to_bytes(2 * n, "little")
    low, high = total[0::2], total[1::2]
    keep = int.from_bytes(high.translate(_KEEP), "little")
    saturate = int.from_bytes(high.translate(_SATURATE), "little")
    clamped = (int.from_bytes(low, "little") & keep) | saturate
    return _restore_alpha(bytearray(clamped.to_bytes(n, "little")), frame)


def _box_pass(lanes: int, count: int, stride_lanes: int, log2_width: int) -> int:
    """One centred box pass of width 2**log2_width along a stride of ``stride_lanes`` lanes; lanes outside the frame are
    zero, so the sum wraps across row ends for the horizontal pass and takes zeros past the top and bottom rows."""

    width = 1 << log2_width
    step_bits = LANE_BITS * stride_lanes
    full = lane_full_mask(count)
    total = 0
    for j in range(-(width // 2), width - width // 2):
        total += (lanes >> (j * step_bits)) if j >= 0 else ((lanes << (-j * step_bits)) & full)
    return (total >> log2_width) & lane_low_mask(count)  # floor(sum / width); sum <= 256 * 255 keeps lanes apart


def box_blur(frame: bytes, width: int, height: int, log2_width: int, channels: int = 4) -> bytes:
    """Separable centred box filter of width ``2**log2_width`` (1..MAX_BOX_LOG2) on a frame of ``channels`` bytes per
    pixel.

    Declared fidelity limits (review-wp07 findings 3 and 4):
    - within ``2**(log2_width - 1)`` pixels of the left and right edges the horizontal box wraps to the neighbouring
      row; the first and last pixels of the frame, and the rows beyond the top and bottom, take zeros, so a strong
      blur darkens the frame edges and lowers the mean luma slightly;
    - each of the two passes floors ``sum / width``, a bias of up to ``-(width - 1) / (2 * width)`` levels per pass on
      average.
    """

    if not 1 <= log2_width <= MAX_BOX_LOG2:
        raise ValueError(f"log2_width must be in [1, {MAX_BOX_LOG2}] (tool limit)")
    count = len(frame)
    lanes = _box_pass(spread(frame), count, channels, log2_width)
    lanes = _box_pass(lanes, count, channels * width, log2_width)
    out = bytearray(low_bytes(lanes, count))
    return _restore_alpha(out, frame) if channels == 4 else bytes(out)


def luma(frame: bytes) -> bytes:
    """8-bit luma ``(77 R + 150 G + 29 B) >> 8`` of a BGRA8 frame (the weights sum to 256)."""

    pixels = len(frame) // 4
    total = 29 * spread(frame[0::4]) + 150 * spread(frame[1::4]) + 77 * spread(frame[2::4])
    return low_bytes((total >> 8) & lane_low_mask(pixels), pixels)


def histogram(values: bytes) -> list[int]:
    return [values.count(v) for v in range(256)]


def moments(values: bytes) -> tuple[int, float, float]:
    """``(n, mean, variance)`` of a byte string, from its exact integer histogram."""

    counts = histogram(values)
    n = len(values)
    if n == 0:
        raise ValueError("no values")
    total = sum(v * c for v, c in enumerate(counts))
    squares = sum(v * v * c for v, c in enumerate(counts))
    return n, total / n, (squares * n - total * total) / (n * n)


def interior(plane: bytes, width: int, height: int, margin: int) -> bytes:
    """The rows and columns of a one-byte-per-pixel plane at least ``margin`` pixels from every edge."""

    if 2 * margin >= width or 2 * margin >= height:
        raise ValueError("the margin leaves no interior")
    return b"".join(plane[row * width + margin:(row + 1) * width - margin] for row in range(margin, height - margin))


def image_statistics(frame: bytes, width: int, height: int, *, stride: int, dark_level: int, bright_level: int,
                     sharpness_log2: int) -> dict[str, float]:
    """The smart-camera image statistics of a BGRA8 frame (luma, subsampled by ``stride``).

    The high-frequency variance ``var(Y) - var(box(Y))`` is computed on the interior only, excluding the box's
    ``2**(sharpness_log2 - 1)`` margin, where the box has no wrapped or zero contribution: a uniform frame gives 0 at
    any brightness (review-wp07 finding 4, MEDIUM-2).
    """

    y = luma(frame)
    sample = y[::stride]
    counts = histogram(sample)
    n, mean, variance = moments(sample)
    margin = 1 << (sharpness_log2 - 1)
    y_inner = interior(y, width, height, margin)[::stride]
    blurred = interior(box_blur(y, width, height, sharpness_log2, channels=1), width, height, margin)[::stride]
    _, _, inner_variance = moments(y_inner)
    _, _, blurred_variance = moments(blurred)
    return {"meanLuma": mean, "stdLuma": math.sqrt(max(variance, 0.0)),
            "darkFraction": sum(counts[: dark_level + 1]) / n, "brightFraction": sum(counts[bright_level:]) / n,
            "highFrequencyVariance": inner_variance - blurred_variance}
