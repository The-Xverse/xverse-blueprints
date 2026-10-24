# WP-07 and WP-06 (blueprint half) review log: sensor self-checks, front-zone checks, camera corruption stage

Candidate: branch `candidate/phase8-wp07-sensor-checks-20261024`, from blueprints main `5f71cde` (WP-04 and
WP-05 merged). This is a direct engineering increment, and the log follows the same order:
1. findings come before repairs;
2. an independent read-only review;
3. acceptance;
4. a merge.

None of the last three has happened yet.

**One increment, two modules.** The camera chain (the U2 corruption stage and the U3 smart-camera
self-checks; WP-06 blueprint half, GA-36) and the radar and front-zone checks (WP-07) share the AD-36 check
classes, the U3 unit and the front zone's inputs. They are reviewed together, as two modules with separate
tests.

**Inputs.**
- Thesis `specs/002-assured-aeb`:
  - `spec.md` FR-002, FR-007, FR-028, FR-031 and FR-034;
  - `decisions.md`: AD-18 C, AD-31 C, AD-36 B, AD-02, §J (corruption in U2's sensor-model stage; the
    schedule reaches no role unit), §K, "AD-30 delivery rule" and "WP-04 fault status";
  - `review/decision-proposals-20261024.md` 210 (the AD-31 kinds: blur, noise, occlusion mask, exposure
    change, frame dropout);
  - `design/wp12-xdl-topology.md` §4 (F05, F06, F07, F08, F09 and the U3 intra messages).
- `xverse-compat` main `95e9e7a`, read-only:
  - `xverse_compat/live/frames.py`: the WP-06 U2 receiver. `FrameResult` gives the verified BGRA8 bytes
    in process through `pixels()`, never in a record; the frame format record `camera-frame-format/1` has
    no default;
  - `xverse_compat_carla/items.py` 49: the item envelope `{type, flowId, sequence, originNs, frame,
    value}`, with consecutive per-flow sequences;
  - `protocol.py` 31: the adapter flows `camera`, `radar-adas`, `radar-vc` and `vehicle-motion`;
  - `sensors.py` 33–64: the camera item value `{width, height, fovDeg, rawSha256, rawLength}`; the radar
    value `{detections: [[alt, az, depth, vel]], count}`, already refused by the adapter outside the
    descriptor bounds;
  - `xdl/descriptors/aeb-sim/carla-sensors.json`: camera 800 × 600 at 90°; radar 100 m, 30° × 10°,
    100 m/s, 500 detections.

**Scope.** Offline modules and tests only. No CARLA, no live run, no unit process; the soak's loop10
paths are not touched. This is engineering evidence only.

## Finding 1: design (recorded at 12:10:09, before any code)

### 1.1 Dependencies (decision recorded)
- **U2 and U3 run on the CPython 3.13 pinned venv** (WP-11; `units.py`). Whether numpy is in it is not
  established, and that environment is the pinned live one, which this increment must not touch.
- **Decision: standard library only.**
  - All per-pixel work uses C-level byte operations: `bytes.translate` look-up tables, extended-slice
    assignment, and arithmetic on lane-packed integers (`int.from_bytes`, shifts, `+`, `&`, `|`), so
    no per-pixel Python loop exists.
  - Histograms use `bytes.count`.
  - Adding numpy to U2/U3 would be a separate pinned-venv decision, like WP-08 for U4. It is not taken
    here.

### 1.2 U2 camera corruption stage (GA-36; AD-31 C; FR-031; §J)
- **Position.** It is the output stage of the modelled smart camera: the imaging part, in U2's
  sensor-model stage. Its input is a verified frame from the compat receiver (`FrameResult.pixels()`
  with the camera item). Its output is the F05 `camera-sensor-out` item with the delivered bytes for
  the U3 smart camera.
- **Schedule record** `assured-aeb.camera-corruption/1`, with no defaults:
  - `seed` (integer ≥ 0; P-4);
  - `frameFormat` (the AD-02 format record, `camera-frame-format/1`);
  - `events`, a list of `{id, kind, startNs, endNs, params}`, active while
    `startNs ≤ t − episodeOriginNs < endNs`.
- **Event params, per kind** (every value is a protocol value, TODO after the AD-02 characterisation):

  | Kind | Params | Transform |
  | --- | --- | --- |
  | `blur` | `boxLog2` (1–8) | Separable centred box filter of width 2^s on B, G and R, on 16-bit lanes, with a power-of-two division by shift and mask. It is a box approximation of blur, and is declared as one |
  | `noise` | `stdLevel` (> 0, in 8-bit levels) | Additive noise per channel byte. A seeded uniform byte maps to a Gaussian offset through a 256-entry inverse-CDF table (`statistics.NormalDist`), clamped to ±255. Addition is on 16-bit lanes with a bias, then clamped to [0, 255] |
  | `occlusion` | `x`, `y`, `width`, `height` (pixels, within the frame), `value` (0–255) | The rectangle's B, G and R are set to `value` |
  | `exposure` | `gain` (> 0), `offset` | `clamp(round(gain · v + offset))` per B, G and R byte, through a 256-entry table |
  | `dropout` | none | The frame is not delivered: no F05 item, so U3 sees a sequence gap |

  Alpha is preserved by every kind. Overlapping events apply in declared order, and dropout dominates.
- **Determinism.** The noise generator is seeded per frame with `SHA-256(seed | event id |
  episode-relative ns)` and drawn with `randbytes`, which is built on the Mersenne Twister
  `getrandbits` sequence. CPython keeps that sequence stable for an integer seed. The inverse CDF is the
  pure-Python `NormalDist.inv_cdf`.
- **Time base (AD-30 delivery rule).** The episode origin is bound once from the first frame
  (`bind_origin`), and no frame is processed before it.
- **No leak (FR-028; §J).**
  - The F05 item carries only the delivered frame's identity: frame, sequence, origin, geometry, and the
    SHA-256 and length of the **delivered** bytes. It carries no adapter `rawSha256`, so U3 cannot detect
    corruption by comparing digests.
  - It carries no event, kind, seed or "corrupted" flag.
  - The applied events are recorded as U2 **evidence only**, as frame number, event ids and kinds, never
    pixels ("WP-04 fault status" analogue).
- **Edge effects (declared fidelity limits).**
  - The box blur wraps horizontally across row ends within 2^(s−1) pixels of the left and right edges,
    and takes zeros beyond the top and bottom rows.
  - The noise is quantised to 256 levels of the inverse CDF.

### 1.3 U3 smart camera self-checks (AD-18; FR-034; AD-36)
- **Inputs.** An F05 item with its delivered bytes. It verifies `sha256(bytes) == frameSha256` and the
  length against the format.
- **Indicators (own output only).**
  - frame sequence (the gap since the last item, duplicate, regression), and frame increase;
  - age (`now − originNs`, absolute ns);
  - image statistics on 8-bit luma `(77R + 150G + 29B) >> 8`, computed on lanes and subsampled by
    `statsStride`: mean, standard deviation, dark fraction (luma ≤ `darkLevel`), bright fraction
    (luma ≥ `brightLevel`), and a high-frequency variance, `var(Y) − var(box(Y))` with a box of 2^
    `sharpnessBoxLog2`, which falls under blur.
- **Check classes (AD-36).**

  | Class | Checks |
  | --- | --- |
  | (i) logical (no number) | consecutive sequence; increasing frame; digest and length match; age ≥ 0 |
  | (ii) plausibility (configured specification) | width, height and encoding equal the configured format (`carla-sensors.json`; AD-02) |
  | (iii) statistical (characterisation; D-2/D-3) | `maxAgeNs`, luma mean bounds, minimum standard deviation, maximum dark and bright fractions, minimum high-frequency variance |

  Class (iii) thresholds come from the record `assured-aeb.smart-camera-checks/1`, with no defaults.
  Its stats parameters (`statsStride`, `darkLevel`, `brightLevel`, `sharpnessBoxLog2`) are protocol
  values too.
- **Output.** `assured-aeb.camera-selfcheck/1`, with the indicators and per-class verdicts, the frame
  identity and the delivered digest. **No pixels.** The bytes pass to the front zone, and through F07 to
  perception, by reference (`frameSha256`) on the frame path.

### 1.4 U3 smart radar self-checks (AD-18; FR-034)
- **Inputs.** The F06 radar item: the adapter's radar envelope (`radar-adas`; the wiring choice of one
  adapter radar flow is WP-10's, and the accepted flow ids are declared).
- **Indicators.** Detection count, frame continuity (sequence gap, duplicate, regression), and age.
- **Check classes.**
  - (i) `count == len(detections)`; sequence; frame increase; age ≥ 0.
  - (ii) each detection within the configured specification (`rangeM`, half fields of view,
    `maxVelocityMps`), and `count ≤ maxDetections`. The specification record must equal the descriptor
    values. The adapter already refuses an out-of-bounds item, so class (ii) here fires only on content
    altered after the adapter. It is kept as a declared second check.
  - (iii) detection-count bounds and `maxAgeNs` (`assured-aeb.smart-radar-checks/1`; D-2; no defaults).
- **Output.** `assured-aeb.radar-selfcheck/1`, with the detections and the verdicts.

### 1.5 U3 front zone (FR-002)
- **Inputs.** The smart-camera and smart-radar self-check items (intra-unit).
- **Reception and freshness.** It assigns `receivedNs` (absolute ns, its step time) and computes
  `ageNs = receivedNs − originNs`. Freshness per sensor uses `freshnessWindowNs` (AD-06;
  `assured-aeb.front-zone-checks/1`, no defaults).
- **Checks.**
  - integrity: schema and members, and a well-formed digest;
  - sequence: monotonic per stream;
  - plausibility: the smart sensor's class (ii) verdict is carried forward.
- **Routing.**
  - camera → F07 `camera-evidence` (to `perception`);
  - radar → F08 `radar-evidence` (to `fusion-risk-aeb`) **and** F09 `radar-evidence` (to `vc-ingress`),
    as two separate items, one per flow.
- **What it does not do.** It decides nothing: every item is forwarded with its verdicts, and the U5
  evidence validator qualifies it (FR-007, FR-008). It carries no pixels, and has no authority.

### 1.6 Files and tests (planned)
- **`assured_aeb/imageops.py`:** the lane-packed byte operations (exposure table, noise, occlusion, box
  blur, luma, histogram statistics).
- **`assured_aeb/camera_chain.py`:** `CorruptionSchedule`, `CorruptionStage` (U2) and `SmartCamera` (U3).
- **`assured_aeb/radar_zone.py`:** `SmartRadar` and `FrontZone` (U3).
- **Tests:**
  - `tests/test_imageops.py`: each transform against a direct per-pixel reference on small frames, plus
    the alpha preservation;
  - `tests/test_camera_chain.py`: the records without defaults; the schedule in episode-relative time
    with late binding; seeded determinism and the two-epoch PAIR-1 case; dropout; no-leak (F05 members;
    the evidence holds no pixels); the self-checks seeing the corruption (blur lowers the high-frequency
    variance, exposure moves the mean, occlusion raises the dark fraction, noise raises the standard
    deviation, dropout gives a gap); each class verdict;
  - `tests/test_radar_zone.py`: the radar classes; the front-zone freshness, integrity and sequence
    checks; F07, F08 and F09 routing; no pixels; topology binding.
- A probe of the host time per 800 × 600 frame is recorded, as an engineering observation only.

### 1.7 Expected residuals
1. Every threshold, corruption severity, stats parameter and freshness window (AD-27; D-2, D-3, AD-02,
   AD-06).
2. Frame transport U2 → U3 → U4 by reference, and the F05 to F09 delivery (WP-10, WP-13).
3. The box-blur approximation and its edge effects, declared.
4. numpy for U2/U3: not used, and adding it is a separate venv decision.
