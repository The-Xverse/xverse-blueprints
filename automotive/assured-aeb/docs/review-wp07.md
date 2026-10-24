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

## Finding 2: implementation result (2026-10-24 12:15:10; commit `98d6b25`)

**What was added (standard library only).**
- `assured_aeb/imageops.py`: lane-packed operations: exposure table, inverse-CDF noise, occlusion, box blur,
  luma and histogram statistics.
- `assured_aeb/checks.py`: exact records, AD-36 verdicts and sequence status.
- `assured_aeb/camera_chain.py`: `CorruptionSchedule`, `CorruptionStage` (U2), `SmartCameraParams` and
  `SmartCamera` (U3).
- `assured_aeb/radar_zone.py`: `SmartRadarParams`, `SmartRadar`, `FrontZoneParams` and `FrontZone` (U3).
- **Tests:** `tests/test_imageops.py` (14), `tests/test_camera_chain.py` (32) and
  `tests/test_radar_zone.py` (18): 64 new.

**Commands.**
- The three new files: 64 passed.
- The whole blueprint suite with the rc.1 profiles: 235 passed.
- `check_topology.py`: exit 0. The WP-12 documents are unchanged.
- Host load 4.4. No CARLA, no live run; the loop10 paths and the pinned live environment were not
  touched.

**Results against the design (finding 1).**

| Item | Result |
| --- | --- |
| Dependencies §1.1 | Standard library only. Every transform equals a direct per-pixel reference on a 9 × 7 frame: exposure (3 settings), noise (σ 1, 20 and 200 levels), box blur (widths 2, 4 and 8, including the declared edges), occlusion and luma. Alpha is preserved. Host-time probe (engineering observation only): on 800 × 600 BGRA, noise plus blur 4 in the stage took 68 ms, and the smart camera 47 ms at stride 4 |
| Corruption §1.2 | All five AD-31 kinds. The records are exact, with no defaults; each malformed variant is refused (13 cases). The schedule is active on `[startNs, endNs)` of episode-relative time. The origin binds once, and nothing is processed before it. The input bytes must match the camera item's `rawSha256`. Noise is reproducible for a seed and differs for another seed. Two world epochs (1000 s and 1600.03 s) give identical delivered frames (PAIR-1). Dropout delivers nothing, and the smart camera reports the gap |
| No leak §1.2 | The F05 item has exactly the declared members: no event, kind, seed or "corrupt" word, and no adapter digest. Its digest is that of the delivered bytes. The applied events appear only in the stage's evidence (frame, ids, kinds), with no bytes |
| Smart camera §1.3 | (i): sequence (gap, duplicate, regression), frame increase, digest and length, future origin. (ii): geometry against the configured format. (iii): age, luma mean bounds, minimum standard deviation, dark and bright fractions, and the high-frequency variance. The self-checks see the corruption: blur fails `high-frequency`, darkening exposure fails `mean-luma`, occlusion fails `dark-fraction`, brightening exposure fails `bright-fraction`, and noise raises `stdLuma`. A clean frame passes every class. A digest or length failure leaves class (iii) `not-evaluated`. No pixels are in the output |
| Smart radar §1.4 | (i): count consistency, sequence, frame, future origin. (ii): the configured specification, with values equal to `carla-sensors.json` (range, half fields of view, velocity, maximum detections). (iii): the count bounds and age. The accepted flow ids are the adapter's `radar-adas` and `radar-vc` |
| Front zone §1.5 | Assigns `receivedNs` and checks `ageNs` against the window per sensor (a future origin is not fresh). Checks integrity on the exact members and a well-formed digest, and sequence per sensor. Carries the sensor's class (ii) verdict forward. Routes camera evidence to F07, and radar evidence to F08 and F09 as separate deep copies, bound to the WP-12 flows (front-zone producer; consumers `fusion-risk-aeb` and `vc-ingress`). No pixels |

All formats, schedules, statistics parameters, thresholds and windows in the tests are labelled test values.
The radar specification is the configured descriptor, as AD-36 class (ii) requires.

**Residuals.**
1. **Protocol values (AD-27).**
   - The corruption severities, event times and seed (AD-31 after the AD-02 characterisation; P-4).
   - The camera statistics parameters and class (iii) thresholds (D-2, D-3).
   - The radar count and age thresholds (D-2).
   - The front-zone freshness windows (AD-06).
   - The frame format (AD-02).
2. **Transport and wiring** (WP-10, WP-13):
   - frames U2 → U3 → U4 by reference (`frameSha256`), and F05 to F09 delivery under the AD-30
     delivery rule;
   - `bind_origin` at the first frame;
   - which adapter radar flow feeds the smart radar (both ids are accepted). The adapter emits
     `radar-adas` and `radar-vc` separately, and the front zone produces the two logical streams.
3. **Declared fidelity limits.**
   - The blur is a box approximation, with its edge wrap and zeros.
   - The noise is a 256-level inverse-CDF quantisation, clamped to ±255.
   - The statistics use luma subsampled by a stride.
   - Radar class (ii) duplicates the adapter's own refusal and fires only on content changed after the
     adapter.
4. **numpy for U2/U3:** not used. Adding it would be a separate pinned-venv decision.
5. **Reproducibility condition.** The noise relies on CPython's Mersenne Twister `getrandbits`
   (through `randbytes`) and on the pure-Python `NormalDist.inv_cdf`, both pinned with the U2 interpreter.
6. **Evidence emission.** The stage's evidence and the self-check items become Argus records through
   ED-12, and are never on a runtime flow except as the declared self-check items.

The next step is an independent read-only review of `98d6b25`, then acceptance and merge. Neither has
happened.

## Finding 3: independent review of findings 1 and 2 (2026-10-24 12:19:50)

**Reviewer and method.**
- An independent, read-only reviewer who did not write this increment.
- Read `967ada2`, `98d6b25` and `c795b24` against base `5f71cde`, and checked them against:
  - thesis FR-002, FR-007, FR-028, FR-031 and FR-034, AD-18 C, AD-31 C, AD-36 B (`decisions.md` 83) and
    AD-02, §J, §K and the "AD-30 delivery rule";
  - compat `sensors.py` 47–64 and `carla-sensors.json` at `95e9e7a`.
- Commands (`/dev/shm/compat-p6-venv/bin/python -I`, rc.1 profiles from a scratch export):
  - the three new test files: 64 passed;
  - the whole suite: 235 passed;
  - `check_topology.py`: exit 0.
- In-memory probes on 800 × 600 BGRA: the uniform-frame statistics, blur widths 2^2, 2^5 and 2^8 (time,
  mean luma and the edge pixels), and the noise table spread. Nothing in the worktree changed except this
  entry. No CARLA, no live run.

### Verdict: **PASS WITH NOTES. Nothing blocks the merge.**

The modules are offline and unwired. MEDIUM-2 and MEDIUM-3 should be settled before the D-2/D-3
characterisation, because they shape the AD-03 input-quality indicators. MEDIUM-1 must be a WP-10/D-4
obligation before any live run. The merge still awaits acceptance.

### Confirmed
- **Corruption stage, determinism and time base** (camera_chain.py 106–163).
  - The events are active on `[startNs, endNs)` of `originNs − episodeOriginNs`. The origin binds once,
    and nothing is processed before it (`origin-unbound`, `before-episode`).
  - Noise bytes come from `Random(SHA-256(schema | seed | event id | relative ns)[:8]).randbytes(n)`, so
    two world epochs give identical delivered frames (PAIR-1 test).
- **Incoming digest.** `sha256(pixels)` must equal the adapter item's `rawSha256`, and the length must
  equal the configured format, before anything is applied.
- **F05 content.** Exactly `schema, source, frame, sequence, originNs, width, height, encoding,
  frameSha256, frameLength`.
  - `frameSha256` is the digest of the delivered bytes, and the length is constant for the format.
  - No event, kind, seed, flag or adapter digest is present.
  - `frame`, `sequence` and `originNs` are the adapter's own, so a dropout appears as an adapter-sequence
    gap, indistinguishable from a real missing frame.
  - The evidence holds `frame`, `originNs`, event ids and kinds only, never bytes. U3 can therefore learn
    nothing about the schedule from the *content*. For timing, see MEDIUM-1.
- **Image operations** (imageops.py).
  - Lane arithmetic stays carry-free: noise sums lie in [1, 766], box sums are ≤ 256 · 255, and luma is
    ≤ 256 · 255.
  - The noise clamp is correct: high byte 0 maps to 0, 1 keeps the low byte, and ≥ 2 maps to 255.
  - Luma is BT.601 in integer form (77/150/29).
  - The 14 reference tests agree on 9 × 7 frames.
- **AD-36 classes.**
  - (i) is logical: sequence, frame, digest and length, future origin, radar count consistency.
  - (ii) is the configured specification: camera geometry, and the radar range, fields of view, velocity
    and maximum detections equal to `carla-sensors.json`.
  - (iii) is characterisation thresholds.
  - Every record is exact-member with no defaults.
- **Front zone** (radar_zone.py 132–181). It assigns `receivedNs`, and freshness is `0 ≤ age ≤ window`.
  - It checks integrity and sequence, carries the sensor's plausibility verdict, and forwards every item
    whatever its verdicts (no decision).
  - The camera payload is the digest, frame and indicators only (no pixels).
  - Radar goes to F08 and F09 as separate deep copies.
- **Radar class (ii)** reproduces the adapter's bounds rule (`sensors.py` 47–64, the same
  `ANGLE_TOLERANCE`). With the shipped descriptor it fires only on content altered after the adapter, as
  declared. See LOW-2.

### Issues (none blocks the merge)

**MEDIUM-1: the host cost of the image work is the size of the step, and its timing consequences are
not recorded.**
- Measured on this host with no other load control:
  - box blur alone takes 49 ms at 2^2, 151 ms at 2^5 and **913 ms at 2^8**;
  - finding 2 records 68 ms for noise plus blur 4 in the stage, and 47 ms for the smart camera on every
    frame at stride 4;
  - the simulator step is 50 ms (K-10).
- The `boxLog2` domain [1, 8] therefore admits severities that cannot run at 20 Hz. The U3 statistics
  alone take about one step on every frame.
- **Timing side channel.** The stage cost depends on the active kind: a clean frame needs only a digest,
  while blur and noise take tens to hundreds of ms. U3 learns nothing from content. It also learns nothing
  from simulation time, *provided that*:
  - (a) the hub delivers F05 at a simulation time independent of the processing duration (the stage
    completes inside the U2 tick that delivers the frame, or delivery is keyed to the frame's stamp under
    the AD-30 delivery rule, never "when ready");
  - (b) no role unit derives an indicator from host time.
- Record (a) and (b) as WP-10/WP-13 obligations, and the per-frame host budget as a D-4/E8-3a item, in
  the residuals. Either bound `boxLog2` by the measured budget, or declare that numpy (residual 4) may be
  needed.

**MEDIUM-2: the high-frequency indicator is biased by the zero edges of its own box, so it depends on
mean luma.**
- Where: imageops.py 162–174.
- Probe: a perfectly uniform 128-grey frame (stride 4, sharpness box 2^2) gives `stdLuma` 0 but
  `highFrequencyVariance` **−10.226**. The darkened top and bottom rows of `box(Y)` add variance that
  `Y` does not have.
- The term grows with the square of mean luma, so exposure changes alone move the blur detector. A
  brightening exposure lowers it and can trip `high-frequency`, which is the blur check. That confounds
  the per-kind attribution the AD-03 indicators are meant to give.
- Strong blur in the corruption stage also darkens the frame through the same zero edges: mean luma fell
  from 128 to 127.8 at 2^2, 126.3 at 2^5 and **114.2 at 2^8**. Blur therefore also moves `mean-luma`.
- Repair options: compute the indicator on the interior only, excluding `2^(s−1)` rows and columns, or
  with edge replication. Alternatively declare the bias in residual 3 and require D-3 to characterise
  thresholds with this exact function. The stage-side darkening belongs in the declared fidelity limits.

**MEDIUM-3: no self-check fails for the `noise` kind.**
- Where: camera_chain.py 182–183 and 259–266; test_camera_chain.py 202–205.
- Class (iii) has only lower bounds on `stdLuma` and `highFrequencyVariance`, and noise raises both.
  `test_noise_raises_the_luma_spread` checks only that the indicator rises; no verdict fails.
- So of the five AD-31 kinds, noise is the one the camera self-checks *observe* but never *flag*. FR-034
  requires observation, which holds, but the AD-03 input-quality verdict is blind to it.
- Either add upper bounds (`maxStdLuma` or `maxHighFrequencyVariance`, characterised under D-3), or
  declare noise as indicator-only, left to the ML OOD indicator, in the record.

**LOW-1: the parameter records do not check consistency or class.**
- `minMeanLuma ≤ maxMeanLuma` is not enforced, and fractions are not limited to [0, 1].
- `maxAgeNs` sits in class (iii), "from characterisation", although an age bound is an AD-06/AD-07
  freshness value. The front zone also has its own `cameraFreshnessWindowNs`, so two age thresholds now
  exist. Declare which one is the AD-06 value.

**LOW-2: radar class (ii) runs on rounded values.**
- The adapter checks the raw detection, then rounds altitude and azimuth to 6 decimals and depth and
  velocity to 3 (`sensors.py` 62). The smart radar checks the rounded value against bound + 1e-9.
- With the shipped 30° × 10° specification no rounded value can cross the bound. For other fields of view
  a value within half a unit of the last decimal below the bound can round above it, for example
  azimuth 0.3054326 at 35°, giving a false `detection-out-of-specification`.
- Add the rounding half-unit to the tolerance, or state the limit.

**LOW-3: the declared fidelity limits are incomplete.**
- The first and last pixels of the frame take zeros rather than wrapping. Probe: the top-left pixel
  becomes 50 from 200 at width 2.
- Two flooring passes bias the blur by up to about −(w − 1)/2w levels per pass.
- The inverse-CDF table truncates the noise at about ±2.9σ: extremes ±58 at σ 20, with a spread of
  19.95.
- Add these to residual 3.

**LOW-4: reproducibility.** CPython documents version stability only for `random()` under a compatible
seeder. `randbytes` and `getrandbits` are covered by the interpreter pin, which residual 5 states.
`NormalDist.inv_cdf` uses `math.log` and `math.sqrt`, so the host libm is also a condition. Its offsets
are rounded to integers, so the effect is limited to rounding boundaries. Add the libm condition to
residual 5, as for WP-05.

### Residuals 1 to 6
- Residuals 1, 4 and 6 are accurate. Residual 2 is accurate but should add MEDIUM-1 (a) and (b).
  Residual 3 is incomplete (MEDIUM-2, LOW-3). Residual 5 is accurate and should add the libm condition.
- Missing: the host budget and the timing conditions (MEDIUM-1), and the noise detection gap (MEDIUM-3).

### Recommendation
- Before D-2/D-3, repair or decide MEDIUM-2 (interior-only high-frequency variance) and MEDIUM-3 (noise
  upper bounds, or indicator-only).
- Record MEDIUM-1 as WP-10, WP-13 and D-4 obligations, with a `boxLog2` bound.
- Record LOW-1 to LOW-4.
- Then acceptance and merge.

## Finding 4: disposition of finding 3 (2026-10-24 15:16:50; recorded before any change)

This disposition is the coordinator's, under the author's delegation: repair now. It is flagged for the author's
review.

| Item | Disposition | Planned change |
| --- | --- | --- |
| MEDIUM-1 | Record and repair | Record as WP-10/WP-13 obligations: (a) F05 is delivered at a simulation time independent of the processing duration; (b) no role unit derives an indicator from host time. Record the per-frame host budget of the U2 stage and the U3 camera as a D-4c TODO. `boxLog2` and `sharpnessBoxLog2` get an enforced **tool upper bound** of 4, based on the finding 3 measurements (49 ms at 2^2, 151 ms at 2^5 and 913 ms at 2^8, against a 50 ms step). It is recorded as a tool limit, not a protocol value |
| MEDIUM-2 | Repair | Compute the high-frequency indicator on the frame interior, excluding the box's 2^(s−1) margin rows and columns, so a uniform frame gives 0 at any brightness. Test across brightness levels. Declare the stage-side blur darkening (zero edges) in the fidelity limits |
| MEDIUM-3 | Repair | Add upper bounds `maxStdLuma` and `maxHighFrequencyVariance` (D-3; no defaults), so noise trips a check. Test each corruption kind against its check |
| LOW-1 | Repair | Refuse min ≥ max in the threshold records, and fractions outside [0, 1]. Remove `maxAgeNs` from the camera and radar checks: the age bound is the front zone's AD-06 window. The age indicator and the logical future-origin check remain |
| LOW-2 | Repair | The radar plausibility tolerance adds the descriptor's rounding half-unit (6 decimals for altitude and azimuth, 3 for depth and velocity; compat `sensors.py` 62). Test at a 35° field of view |
| LOW-3 | Record | Complete the fidelity limits: the first and last pixels take zeros; two flooring passes bias the blur by up to −(w − 1)/2w levels per pass; the inverse-CDF noise is truncated at about ±2.9σ |
| LOW-4 | Record | The host libm (`math.log`, `math.sqrt` in `NormalDist.inv_cdf`) is a reproducibility condition, beside the interpreter pin |

## Finding 5: result of the finding 4 repairs (2026-10-24 15:19:30; repair commit `f1eb4cf`)

**Commands.** The three module test files: 82 passed (64 before). Whole suite with the rc.1 profiles: 253
passed. `check_topology.py`: exit 0. Host load 5.5. No CARLA, no live run; the loop10 paths and the pinned live
environment were not touched.

**MEDIUM-1, recorded and repaired.**
- **Tool limit.** `imageops.MAX_BOX_LOG2 = 4` applies to the stage's `boxLog2` and the camera's
  `sharpnessBoxLog2`. It is enforced in `box_blur` and in both records, and recorded as a tool limit, not a
  protocol value.
- **Re-measured on 800 × 600 BGRA** (engineering observation only, at load about 5): blur 2^2 took 38 ms,
  blur 2^4 70 ms, and the smart-camera statistics 50 ms. Even at the limit, blur takes longer than the
  50 ms step. The per-frame budget is therefore a D-4c measurement, and numpy for U2/U3 may become
  necessary (residual 4).
- **Obligations stated in `camera_chain.py`** (WP-10/WP-13):
  - the hub delivers F05 at a simulation time independent of the stage's processing duration;
  - no role unit derives an indicator from host time.

**MEDIUM-2, repaired.**
- The high-frequency variance is computed on the interior only (`imageops.interior`), excluding the
  2^(s−1) margin, where the box has no wrapped or zero contribution.
- A uniform frame now gives exactly 0, with `stdLuma` 0, at levels 0, 1, 37, 128, 200 and 255 and at
  sharpness boxes 2^1 and 2^2 (test).
- The stage-side blur darkening (zero edges) is declared in the `box_blur` docstring.

**MEDIUM-3, repaired.**
- New upper bounds `maxStdLuma` and `maxHighFrequencyVariance` (class (iii), D-3; no defaults). The
  statistical names are now `std-luma-low`/`std-luma-high` and `high-frequency-low`/`high-frequency-high`.
- **Each AD-31 kind is tested against its check:**

  | Kind | Check it trips |
  | --- | --- |
  | blur (2^3) | `high-frequency-low` |
  | darkening exposure | `mean-luma` |
  | occlusion | `dark-fraction` |
  | brightening exposure | `bright-fraction` |
  | noise (σ 60) | `std-luma-high` and `high-frequency-high` |
  | dropout | the logical `sequence-gap` (existing test) |

**LOW-1, repaired.**
- The camera record refuses min ≥ max for mean luma, the luma spread and the high-frequency variance, and
  fraction thresholds outside [0, 1]. The radar record refuses `minCount ≥ maxCount`.
- `maxAgeNs` is removed from both sensors' checks. The age bound is the front zone's AD-06 freshness window.
  The age stays an indicator and a logical check (future origin), and a test asserts that no age threshold
  remains in the camera checks.

**LOW-2, repaired.**
- Radar class (ii) adds the adapter's rounding half-unit: 0.5e-6 rad for altitude and azimuth, 0.5e-3 for
  depth and velocity (compat `sensors.py` 62).
- At a 35° field of view, the raw azimuth 0.30543261 rounds to 0.305433, above the raw bound plus
  `ANGLE_TOLERANCE`. It is now plausible; before the repair it gave a false `detection-out-of-specification`.
  0.3060 is still refused (test).

**LOW-3 and LOW-4, recorded** in the `imageops` docstrings.
- The first and last pixels of the frame, and the rows beyond the top and bottom, take zeros.
- Two flooring passes bias the blur by up to −(w − 1)/2w levels per pass.
- The noise is truncated at about ±2.9σ (`inv_cdf(0.5/256)`) and rounded to whole levels.
- Reproducibility depends on the interpreter pin and the host libm (`math.log` and `math.sqrt` in
  `NormalDist.inv_cdf`).

**Residuals (replaces finding 2's list).**
1. **Protocol values** (AD-27): the corruption severities, event times and seed; the camera statistics
   parameters and class (iii) bounds, now including `maxStdLuma` and `maxHighFrequencyVariance`; the radar
   count bounds; the front-zone AD-06 windows; the frame format.
2. **Wiring (WP-10, WP-13):**
   - frames by reference;
   - F05 to F09 delivery under the AD-30 delivery rule, at a simulation time independent of processing
     duration;
   - no host-time indicator in any role unit;
   - `bind_origin`;
   - the choice of adapter radar flow.
3. **Fidelity limits:** the box approximation with its edge wrap, zero edges and darkening; the flooring
   bias; the noise truncation and rounding; the luma stride; radar class (ii) as a second check.
4. **Host budget:** the per-frame budget of the stage and the smart camera (D-4c). numpy for U2/U3 may be
   needed: blur at the tool limit (70 ms) exceeds the step.
5. **Reproducibility:** the interpreter pin (`randbytes`/`getrandbits`) and the host libm.
6. **Evidence emission:** ED-12.

The next step is acceptance and a merge. Neither has happened.

## Finding 6: independent re-review of findings 4 and 5 (2026-10-24 15:25:17)

**Reviewer and method.**
- The finding 3 reviewer, read-only. Read `6135b53`, `f1eb4cf` and `9b0f4aa` against `f89c97f`, with the new
  thesis row "U2/U3 numpy" (`decisions.md` 289).
- Commands:
  - the three module test files: 82 passed;
  - the whole suite with the rc.1 profiles: 253 passed;
  - `check_topology.py`: exit 0.
- In-memory probes on 800 × 600: uniform frames at levels 0, 128 and 255; a seeded textured frame, clean,
  under exposure gain 0.5, offset +60 and blur 2^3; and the tool limit. Nothing in the worktree changed except
  this entry. No CARLA, no live run.

### Verdict: **PASS WITH NOTES. Nothing blocks the merge.**

### Items of finding 3
- **MEDIUM-1: closed.**
  - `MAX_BOX_LOG2 = 4` (imageops.py 20) is enforced in `box_blur` and in both records, and labelled a tool
    limit; `box_blur(…, 5)` raises.
  - The two wiring obligations are stated in `camera_chain.py` and residual 2: F05 is delivered at a simulation
    time independent of processing duration, and no role unit derives an indicator from host time.
  - The re-measured cost (blur 2^4 70 ms, statistics 50 ms, against a 50 ms step) is now the basis of the
    decided "U2/U3 numpy" row.
- **MEDIUM-2: closed.**
  - `interior` (175) excludes the 2^(s−1) margin. That margin is exactly the box's reach: the offsets run from
    −w/2 to w/2 − 1, so no interior pixel sees a wrapped or zero contribution.
  - Probe: uniform frames at 0, 128 and 255 give a high-frequency value of exactly `0.0`, compared with
    −10.2 at 128 before the repair.
  - The stage-side darkening is declared in `box_blur`.
- **MEDIUM-3: closed.**
  - `maxStdLuma` and `maxHighFrequencyVariance` were added to class (iii) (camera_chain.py 186–188), with
    split low and high names.
  - The tests map each AD-31 kind to a failing check:
    - blur → `high-frequency-low`;
    - darkening → `mean-luma`;
    - occlusion → `dark-fraction`;
    - brightening → `bright-fraction`;
    - noise → `std-luma-high` and `high-frequency-high`;
    - dropout → `sequence-gap`.
- **LOW-1: closed.** min < max is enforced for the three pairs, fractions must lie in [0, 1], and the radar
  record requires `minCount < maxCount`. `maxAgeNs` is removed from both sensors, so the AD-06 window in the
  front zone is now the only age bound. The age remains an indicator and the future-origin check.
- **LOW-2: closed.** The rounding half-units are added (`ANGLE_ROUNDING` 0.5e-6 rad, `LINEAR_ROUNDING`
  0.5e-3; radar_zone.py 33–34), with a 35° test: 0.30543261 is accepted and 0.3060 refused.
- **LOW-3 and LOW-4: closed** in the docstrings: the zero first and last pixels, the flooring bias, the ±2.9σ
  truncation, and the interpreter pin plus libm.

### New notes (LOW, not blocking)
- **LOW-A: the high-frequency indicator is contrast-dependent by nature.**
  - Probe on a seeded textured frame: clean 2285.0; exposure gain 0.5 gives **571.3** (×0.25, the square of
    the gain); offset +60 with clipping gives 1740.2; blur 2^3 gives 9.1.
  - So a contrast-reducing exposure also lowers the value that `high-frequency-low`, the blur check, bounds.
    Whether a darkening event also trips the blur check depends on the D-3 thresholds.
  - That is physics rather than an artefact, so it is not a defect. But AD-03 attribution would be cleaner with
    a contrast-normalised sharpness, for example `highFrequencyVariance / var(Y)`, as an added indicator. This
    is optional and should be decided with D-3.
- **LOW-B: residual 4 is now decided.** It says "numpy for U2/U3 may be needed". `decisions.md` "U2/U3 numpy"
  (15:23) decides a pinned numpy 2.5.4 venv under WP-13, with the standard-library operations kept as
  reference implementations. Residual 4 should cite the row. The numpy port must reproduce these semantics
  bit-exactly against the reference tests, including the edges, flooring and interior, or declare any
  difference.

### Recommendation
Ready for acceptance and merge. Update residual 4 to cite the numpy decision, and decide LOW-A with D-3.

## 7. Acceptance (written at 15:28:30 2026-10-24)

- **Accepted** under the author's delegation of 2026-10-24 (thesis `specs/002-assured-aeb/decisions.md` §G, §J,
  §K and the rows cited in this log). It is flagged for the author's review.
- **Basis:** findings 3 and 6 (both PASS WITH NOTES), repairs in findings 4-5; suite 253 passed, checker exit 0.
- Residual 4 is decided by thesis `decisions.md` "U2/U3 numpy": the WP-13 numpy port must match these standard-library reference tests exactly (edges, flooring, interior), or declare each difference. LOW-A (a contrast-normalised sharpness indicator) is decided with the D-3 characterisation.
- **Merged** into blueprints main and pushed (see the merge commit).
