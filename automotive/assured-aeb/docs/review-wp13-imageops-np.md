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

## Finding 2: implementation result (2026-10-24 16:03:50)

**Files.**
- `assured_aeb/imageops_np.py` (new).
- `assured_aeb/camera_chain.py`:
  - `_ops`, and a keyword-only `ops` on `CorruptionStage` and `SmartCamera`;
  - the four corruption calls and `image_statistics` now go through `self.ops`;
  - the `MAX_BOX_LOG2` checks still use the reference constant, which the port re-exports.
- `tests/imageops_np_probe.py` and `tests/test_imageops_np.py` (new).
- `imageops.py` is unchanged.

**Bit-exact result** (the probe in the unit pattern):
- command: `env -i PATH=/usr/bin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<sensor site>:<assured-aeb>` with
  `python3.13 -S -s -B`;
- the sensor site is `/dev/shm/xverse-aeb-sensor-20261024/venv/lib/python3.13/site-packages`, from compat `efd5b6a`;
- **1119 comparisons, 0 failures**;
- numpy 2.5.4 was loaded from the sensor venv, and `site` was not imported;
- the coverage is as designed (§1.3), with three independently seeded frame sets, the 800×600 frame and the camera
  chain end to end;
- the camera chain gives the same delivered bytes, the same `frameSha256`, identical smart-camera self-check records
  and identical stage evidence over nine frames crossing every corruption kind, including overlapping noise and blur.

**Negative control.**
- An in-memory patch, with no file changed, flipped one bit of `imageops_np.box_blur`'s first output byte.
- The probe then exits 1 with 269 failures.
- The comparisons are therefore not vacuous.

**Informative timing** (one run, 800×600 BGRA, this host; **not a budget**; D-4c):

| Operation | numpy | reference |
| --- | --- | --- |
| exposure | 16.4 ms | 2.8 ms |
| add_noise | 10.9 ms | 38.7 ms |
| box_blur (log2 3) | 21.3 ms | 52.9 ms |
| luma | 3.1 ms | 8.8 ms |
| image_statistics (stride 4, sharpness 2) | 5.9 ms | 75.0 ms |

- The port's exposure is slower than the reference's `bytes.translate`.
- Both are bit-exact, so a later increment may route exposure to the reference inside `imageops_np` without any
  semantic change. That is recorded here, not done.

**Commands** (`/dev/shm/compat-p6-venv/bin/python -I`, rc.1 profiles):
- with `XVERSE_AEB_SENSOR_SITE` set:
  - `tests/test_imageops_np.py`, `tests/test_camera_chain.py` and `tests/test_imageops.py`: 65 passed;
  - the whole suite: 291 passed (287 on main plus 4);
- without it: `tests/test_imageops_np.py` gives 3 passed and 1 skipped;
- `check_topology.py`: exit 0;
- `__pycache__` removed;
- no bytecode was written into the sensor venv.

**Residuals.**
1. Bit-exactness holds for numpy 2.5.4 on this host only. A different pin or host requires re-running the probe
   (R-7).
2. The per-frame budget is D-4c, and the exposure routing is optional (above).
3. Later increments must:
   - select `ops=imageops_np` in the U2/U3 unit entries;
   - record the selection and the probe result in run evidence;
   - build the loop10 sensor venv (compat residual 1).
4. The `/dev/shm` sensor venv disappears at reboot. The test then skips, and does not fail.

**Status.** Candidate only. The independent review, acceptance and the merge are pending.

## Finding 3: independent read-only Codex review (2026-10-24), PASS

Reviewed candidate `cc6523e7171997afd39841e057f15afb88f8efa1`: the complete port, reference operations,
selection hook and probe. The signed integer intermediates cannot overflow on the declared byte/noise and box
width domains; both passes preserve the reference's flat-array edge rules and rounding, and alpha restoration is
unchanged. The standard-library implementation remains available and unchanged. No product repair was made.

Re-ran the complete blueprint suite with the pinned test interpreter, rc.1 platform profiles and
`XVERSE_AEB_SENSOR_SITE=/dev/shm/xverse-aeb-sensor-20261024/venv/lib/python3.13/site-packages`:
`env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 XVERSE_PLATFORM_PROFILES=<rc.1>/xdl/profiles
XVERSE_AEB_SENSOR_SITE=<sensor-site> /dev/shm/compat-p6-venv/bin/python -I -B -m pytest -q -p no:cacheprovider tests --tb=short`.
Result: **291 passed**, no skips, in 30.89 s. The non-skipped bit-exact probe checks over 1000 comparisons, numpy
2.5.4 from the named sensor site, and no `site` import. This review does not infer a per-frame budget or live behaviour.
Finding 2 residuals 1 to 4 remain carried, including explicit unit selection and the pending durable sensor venv.

## Finding 4: delegated acceptance (Codex, 2026-10-24; flagged for author review)

Accepted the offline WP-13 #4b port on finding 3, with finding 2 residuals carried. Basis: thesis
`specs/002-assured-aeb/decisions.md` §G and "WP-13 R-1 to R-7", R-7; the author's continuation instruction.
This does not accept the unreviewed sensor-venv increment, select a live unit implementation, fix a D-4c budget,
authorize Phase 8 live execution or establish any scientific result. Merge and assembled-main verification follow.
