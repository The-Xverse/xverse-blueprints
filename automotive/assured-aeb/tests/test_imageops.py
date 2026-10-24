"""Offline tests: each lane-packed image operation equals a direct per-pixel reference on small frames."""

from __future__ import annotations

import random

import pytest

from assured_aeb import imageops as I

W, H = 9, 7  # a small odd-sized test frame


def frame(seed=1):
    return random.Random(seed).randbytes(W * H * 4)


def clamp(v):
    return max(0, min(255, v))


@pytest.mark.parametrize("gain, offset", [(1.5, -10), (0.3, 40.5), (2.0, 0)])
def test_exposure_matches_reference(gain, offset):
    f = frame()
    ref = bytes(clamp(round(gain * v + offset)) if i % 4 != 3 else v for i, v in enumerate(f))
    assert I.exposure(f, gain, offset) == ref


@pytest.mark.parametrize("std", [1.0, 20.0, 200.0])
def test_noise_matches_reference_and_preserves_alpha(std):
    f = frame()
    u = random.Random(2).randbytes(len(f))
    offsets = I.noise_tables(std)[2]
    ref = bytes(clamp(v + offsets[u[i]]) if i % 4 != 3 else v for i, v in enumerate(f))
    assert I.add_noise(f, u, std) == ref


def test_noise_table_is_a_quantised_symmetric_gaussian():
    offsets = I.noise_tables(10.0)[2]
    assert offsets[:128] == tuple(-o for o in reversed(offsets[128:]))  # symmetric
    assert all(-255 <= o <= 255 for o in I.noise_tables(500.0)[2])  # clamped


def _flat(img, i, c, n):
    return img[i * 4 + c] if 0 <= i < n else 0


@pytest.mark.parametrize("log2", [1, 2, 3])
def test_box_blur_matches_reference_with_the_declared_edges(log2):
    f, k, n = frame(), 1 << log2, W * H
    lo, hi = -(k // 2), k - k // 2
    horizontal = [[sum(_flat(f, p + j, c, n) for j in range(lo, hi)) // k for c in range(4)] for p in range(n)]
    both = [[sum(horizontal[p + j * W][c] if 0 <= p + j * W < n else 0 for j in range(lo, hi)) // k for c in range(4)]
            for p in range(n)]
    ref = bytes(both[p][c] if c != 3 else f[p * 4 + 3] for p in range(n) for c in range(4))
    assert I.box_blur(f, W, H, log2) == ref


def test_occlusion_matches_reference():
    f = frame()
    out = I.occlusion(f, W, 2, 1, 3, 4, 17)
    ref = bytearray(f)
    for y in range(1, 5):
        for x in range(2, 5):
            for c in range(3):
                ref[(y * W + x) * 4 + c] = 17
    assert out == bytes(ref)


def test_luma_matches_reference():
    f = frame()
    assert I.luma(f) == bytes((77 * f[i + 2] + 150 * f[i + 1] + 29 * f[i]) >> 8 for i in range(0, len(f), 4))


def test_moments_are_exact():
    values = bytes([0, 10, 10, 255])
    n, mean, var = I.moments(values)
    ref_mean = sum(values) / 4
    assert (n, mean) == (4, ref_mean) and var == pytest.approx(sum((v - ref_mean) ** 2 for v in values) / 4)


def test_blur_lowers_high_frequency_variance():
    f = frame()
    stats = lambda img: I.image_statistics(img, W, H, stride=1, dark_level=10, bright_level=245, sharpness_log2=1)
    assert stats(I.box_blur(f, W, H, 2))["highFrequencyVariance"] < stats(f)["highFrequencyVariance"]



@pytest.mark.parametrize("level", [0, 1, 37, 128, 200, 255])
def test_uniform_frame_has_zero_high_frequency_at_any_brightness(level):  # finding 4, MEDIUM-2
    f = bytes([level, level, level, 255]) * (W * H)
    for log2 in (1, 2):
        stats = I.image_statistics(f, W, H, stride=1, dark_level=10, bright_level=245, sharpness_log2=log2)
        assert stats["highFrequencyVariance"] == 0.0 and stats["stdLuma"] == 0.0


def test_box_width_above_the_tool_limit_is_refused():  # finding 4, MEDIUM-1
    with pytest.raises(ValueError, match="tool limit"):
        I.box_blur(frame(), W, H, I.MAX_BOX_LOG2 + 1)
