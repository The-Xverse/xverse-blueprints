# WP-13 increment #4b review log: the numpy image operations for U2 and U3

**Candidate.** Branch `candidate/phase8-wp13-imageops-np-20261024`, from blueprints main `18201fe`. The order is:
1. findings before repairs;
2. an independent read-only review;
3. acceptance;
4. a merge.

None of the last three has happened yet.

**Inputs.**
- Thesis `design/wp13-logic-ml-binding.md` §5, with R-7 decided: the port is used only if bit-exact, and otherwise the
  reference wins.
- `decisions.md`, the rows "U2/U3 numpy" and "WP-09 #3 unit isolation" R-1.
- Blueprints `assured_aeb/imageops.py`, the standard-library reference, unchanged, and `camera_chain.py`.
- **The companion compat increment.** `candidate/phase8-wp13-sensor-venv-20261024` (`efd5b6a`): the U2/U3 numpy
  2.5.4 venv, built inside `unshare -rn` at `/dev/shm/xverse-aeb-sensor-20261024` (a verification build, not
  loop10).

**Scope.** Offline modules and tests only. No download, no CARLA, no live run; the soak's loop10 paths are not touched.

## Finding 1: design (recorded at 16:00:43, before any code)

### 1.1 `assured_aeb/imageops_np.py`
It has the same function names, signatures and declared semantics as `imageops.py`. The inputs and outputs are
`bytes`, and numpy is used inside only. Per function:
- `exposure`: the **same** 256-entry table, built by the same Python expression (`_clamp8(round(gain·v + offset))`,
  where `round` ties to even), applied with `np.take`. Alpha is restored.
- `add_noise`: the offsets come from `imageops.noise_tables`, the reference's own table, so the `NormalDist` and
  `libm` dependence is identical. Each output byte is `clip(v + offsets[uniform], 0, 255)` in int16, which equals the
  reference's lane `v + offset + 256` with its keep and saturate masks. Alpha is restored.
- `occlusion`:
  - the same rectangle by reshaping to `(rows, width·4)`, setting bytes 0–2 of each covered pixel;
  - the input is a rectangle inside the frame, as `camera_chain` admits only those (lines 104–106);
  - anything outside raises `ValueError`. The reference's behaviour outside the frame (a flat wrap, or an
    extended-slice `ValueError`) is not reproduced, and that domain is never admitted.
- `box_blur`: the reference's **flat lane semantics**, reproduced exactly.
  - Each pass is `total[i] = Σ_{j=−w/2}^{w−w/2−1} x[i + j·stride]` over the flat byte array, with out-of-range
    terms 0. That gives the same horizontal wrap across row ends and the same zero rows beyond the top and bottom.
  - Each pass is followed by floor division by `2**log2`, in int32.
  - The stride is `channels` for the horizontal pass and `channels·width` for the vertical pass, with the same
    `MAX_BOX_LOG2` limit and alpha restored for 4 channels.
  - This works because the reference's lane arithmetic never carries between lanes: `Σ ≤ 2**log2 · 255 < 2**16`, and
    the shift-and-mask keeps the low byte, which equals `floor(Σ / 2**log2)`.
- `luma`: `(29·B + 150·G + 77·R) >> 8` in int32. The reference's lanes stay below `2**16`, so its shift and mask equal
  this floor.
- `histogram`: `np.bincount(minlength=256)`, as Python ints.
- `moments`: the **same exact-integer formula** on Python ints from the histogram, because an int64 product
  converted to float would round differently above `2**53`.
- `interior`: reshape and slice.
- `image_statistics`: the same composition as the reference, using the numpy versions above. The returned floats come
  from the same Python integer expressions.
- Mutable state: none. Global state: only the reference's cached tables.

### 1.2 Selection (R-7)
- `CorruptionStage(schedule, *, ops=None)` and `SmartCamera(params, *, ops=None)` gain a keyword-only `ops`.
  - `None` means the standard-library reference. This is an implementation choice, not a protocol value: under R-7
    the reference wins unless the port is selected.
  - Only the modules `imageops` and `imageops_np` are accepted. Anything else is a `TypeError`.
- `camera_chain` does not import numpy. The U2/U3 unit entries (a later increment) import `imageops_np` in the sensor
  venv and pass it.
- The evidence records do not change. The corruption stage's records stay the same, so the selected implementation
  is recorded by the unit entry (later), not here.

### 1.3 Bit-exactness tests (`tests/test_imageops_np.py` and the probe `tests/imageops_np_probe.py`)
- **The probe** runs every comparison and prints a JSON summary:
  - `exposure` over gains and offsets that include exact `.5` ties;
  - `add_noise` over `stdLevel` 0.5, 5, 20 and 80;
  - random occlusions;
  - `box_blur` with `log2` 1–4, for 4 channels and for 1 channel;
  - `luma`, `histogram`, `moments` and `interior`;
  - `image_statistics` over strides, dark and bright levels and sharpness 1–4.

  The cases use odd sizes (1×1, 3×2, 9×7, 17×5), a frame narrower than the box (3×2 with `log2` 4), uniform frames,
  and one 800×600 frame at the configured camera size.

  It also checks the camera chain end to end:
  - a `CorruptionStage` with each corruption kind, with `ops=imageops_np` against the default, gives the same delivered
    bytes and `frameSha256`;
  - a `SmartCamera` gives identical self-check records.
- **How the probe runs.** It runs in the **unit pattern**: the real CPython 3.13.13 with `-S -s -B`,
  `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONPATH=<sensor site-packages>:<assured-aeb>`.
  - The site-packages directory comes from `XVERSE_AEB_SENSOR_SITE`, with no default. The test skips without it.
  - If numpy is importable in the test process, the probe also runs in-process.
- **Always-run tests** (standard library only):
  - the selection hook refuses an unknown `ops`;
  - `camera_chain` and `imageops` import no numpy;
  - `imageops_np` imports only numpy and the standard library (AST scan).

### 1.4 Expected residuals
1. Bit-exactness is established for numpy 2.5.4 on this CPU only (R-7). A different pin or host requires re-running
   the probe.
2. The per-frame host time of the port against the reference is a D-4c measurement. One informative timing on the
   800×600 frame is recorded, with no budget claimed.
3. The unit entries that select the port, and record the selection in evidence, come later (WP-10 #5 and the
   U2/U3 entries).
