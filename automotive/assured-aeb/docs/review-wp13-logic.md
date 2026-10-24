# WP-13 increment #1 review log: deterministic fusion, AEB rule, radar fallback and functional arbiter

**Candidate.** Branch `candidate/phase8-wp13-logic-20261024`, from blueprints main `18201fe`. This is a direct
engineering increment. The order is:
1. findings before repairs;
2. an independent read-only review;
3. acceptance;
4. a merge.

None of the last three has happened yet.

**Inputs.**
- Thesis `specs/002-assured-aeb` (read-only):
  - `design/wp13-logic-ml-binding.md` §1, §3 and §6–§9;
  - `decisions.md`:
    - the row "WP-13 R-1 to R-7" (15:42; R-1 and R-2 adopted; R-3 adopted in a restricted form; R-4 to R-7
      adopted);
    - AD-05 B (the rule form `d − v·t_lat − v²/(2·a_b) ≤ m` on measured evidence with declared uncertainty bounds);
    - AD-06 B and AD-07 B (methods; values `TODO`);
    - AD-35 B (weakest link, unknown counted as `UNCERTAIN`);
    - AD-36 B (three check classes);
    - AD-14 E2 and FR-041 (a per-cycle request, the arbiter's being the final action);
    - FR-007, FR-015, FR-019, FR-028 and FR-036;
  - Note 21 ([N] 1507, 1511).
- Blueprints main `18201fe`:
  - `topology.py`: elements `fusion-risk-aeb` (U4), and `radar-fallback`, `functional-arbiter` and `vc-ingress`
    (U5);
  - flows F08, F09 and F11, and the intra flows `perception-output`, `radar-evidence`, `adas-cycle`,
    `fallback-request`, `selector-command` and `qualified-evidence`;
  - `radar_zone.py` (the `assured-aeb.radar-evidence/1` messages);
  - `brake_esc.py` (the exact five-member `assured-aeb.brake-request/1`, the chassis-zone member check, and the
    [0, 1] actuator domain);
  - `checks.py`.

**Scope.** Offline modules and tests only, on synthetic records, with no unit entry point and no hub wiring (those are
increments #5 and #6). No download, no CARLA, no live run, and the soak's loop10 paths are not touched. This is
engineering evidence only.

## Finding 1: design of increment #1 (recorded at 15:46:26, before any code)

### 1.1 Modules
| Module | Unit | Contents |
| --- | --- | --- |
| `assured_aeb/parameters.py` | all | The FR-028 runtime-parameter projection reader: parameters are read **by identifier**, with no default |
| `assured_aeb/aeb_rule.py` | U4 and U5 | Note 9 states and the weakest-link aggregate; radar-evidence qualification; corridor selection; the conservative AD-05 residual; the R-2 latch |
| `assured_aeb/fusion_aeb.py` | U4 | `FusionRiskAeb`: the `perception-output` and F08 inputs; the R-1 corroboration rule; the per-cycle `adas-cycle` record |
| `assured_aeb/vc_functional.py` | U5 | `RadarFallback` (F09 through `vc-ingress`, plus qualified ego speed) and `FunctionalArbiter` (R-3 restricted) |

U4 code imports nothing from U5 modules, and U5 code nothing from U4 modules: both import only `aeb_rule`,
`parameters`, `checks` and, for the arbiter, `brake_esc.brake_request`.

### 1.2 Parameters by identifier (FR-028; no defaults)
- **The projection record:**
  - `{schema: "assured-aeb.runtime-parameter-projection/1", protocolRecordSha256, unit, entries: {identifier:
    value}}`;
  - the reader refuses a missing identifier, a value of the wrong type or range, and a non-finite number;
  - `check_exact(projection, identifiers)` refuses entries not consumed by the unit's roles (FR-028: only what they
    consume);
  - **proposed form**, to be fixed with the AD-27 freeze, which also fixes the identifiers.
- **Shared configured facts:**
  - `vehicle.egoFrontM`: the ego front bumper `x` in the ego frame (WP-02 R-2);
  - `radar.mountM`: `[x, y]` of the radar mount in the ego frame (configured; compat `RADAR_MOUNT`);
  - `radar.closingSpeedSign`: `−1` or `+1`, so that closing speed = sign · Doppler velocity. This is the CARLA radar
    sign convention, `TODO: engineering verification` on the D-2 run, so the code does not assume it.
- **Fusion (U4):**
  - `fusion.corridor.halfWidthM`, `fusion.corridor.maxRangeM` (must equal the WP-09 label corridor: a freeze
    consistency check);
  - `fusion.cameraFreshnessNs`, `fusion.radarFreshnessNs` (AD-06);
  - `fusion.occupancyThreshold`, `fusion.distanceBinEdgesM` (must equal the label bin edges);
  - `fusion.associationToleranceM`.
- **The rule (U4):**
  - `aeb.distanceUncertaintyM` (δd), `aeb.speedUncertaintyMps` (δv);
  - `aeb.latencyNs` (t_lat; AD-30), `aeb.decelerationMps2` (a_b; D-1), `aeb.marginM` (m);
  - `aeb.brakeLevel` in (0, 1];
  - `aeb.releaseSpeedMps`, `aeb.releaseAbsentCycles` (R-2).
- **Fallback (U5):**
  - `fallback.corridor.halfWidthM`, `fallback.corridor.maxRangeM`, `fallback.radarFreshnessNs`,
    `fallback.vehicleStateFreshnessNs`;
  - `fallback.oddMaxEgoSpeedMps` (the degraded-ODD bound, the only scenario-derived value projected; FR-028,
    FR-029);
  - the same rule and latch set under `fallback.*` (the degraded path may differ).
- **Arbiter (U5):**
  - `arbiter.requestFreshnessNs`, `arbiter.holdWindowNs` (AD-07);
  - `arbiter.mrcSource`, one of `adas-cycle`, `fallback-request` or `none`: what the arbiter follows under
    `S_MRC_REQUESTED`. That is WP-15's terminal behaviour, a declared value, not chosen in code.
- **Configuration semantics** (sourced, not parameters): `C_NOMINAL` → `adas-cycle` and `C_DEGRADED_RADAR` →
  `fallback-request` (Note 21 [N] 1515, 1519).
- Every record carries `paramsSha256`, the SHA-256 of the canonical consumed entries.
- Tests use values marked TEST-ONLY.

### 1.3 Radar qualification and corridor selection (`aeb_rule`)
- **Input:** an `assured-aeb.radar-evidence/1` message on the role's own stream (`f08-radar-adas` for fusion,
  `f09-radar-vc` for the fallback).
- **Advisory Note 9 state:**

  | Condition | State |
  | --- | --- |
  | wrong schema, source or stream | `UNCERTAIN` |
  | front-zone integrity not `pass` | `UNCERTAIN` |
  | front-zone sequence `duplicate`, `regressed` or `unknown` | `UNCERTAIN` |
  | front-zone plausibility not `pass` | `UNCERTAIN` |
  | sensor logical or plausibility not `pass` | `UNCERTAIN` |
  | the consumer's own age outside its freshness window | `UNCERTAIN` |
  | a malformed detection | `UNCERTAIN` |
  | sensor statistical `fail` | `DEGRADED` |
  | otherwise | `NOMINAL` |

  The WP-14 validator re-derives states under its own rule; these are advisory.
- **Detection position.** A detection `[alt, az, depth, vel]` is placed at `x = mount.x + depth·cos(az)`,
  `y = mount.y + depth·sin(az)`.
  - It is in the corridor when `0 ≤ x − egoFront ≤ maxRange` and `|y| ≤ halfWidth`.
  - Its distance is `d = x − egoFront`, and its closing speed is `v = closingSpeedSign · vel`.
- **Selection.** The nearest in-corridor detection, with ties broken by the lower index (deterministic).
- **Altitude.** Altitude is not gated. Ground-clutter handling is a D-2 matter and recorded as a residual.

### 1.4 The AD-05 residual and the R-2 latch (`aeb_rule`)
- **Residual.** With `d_c = d − δd` and `v_c = max(0, v + δv)`:
  `r = d_c − v_c·t_lat − v_c²/(2·a_b) − m`, and the rule fires when the hypothesis is present and `r ≤ 0`.
  - `v_c` is clamped at 0, because the quadratic term is meaningless for a receding target.
- **The latch, per decision cycle:**
  - a fire sets it and resets the absence count;
  - while latched, the request is `brakeLevel`;
  - it is released when either:
    - the hypothesis is present and `v_c ≤ releaseSpeed` (the conservative speed, so the brake is held longer), or
    - the hypothesis has been absent on `releaseAbsentCycles` consecutive decision cycles.
  - A present but non-firing hypothesis keeps the latch and resets the count.

### 1.5 Fusion (U4, R-1 adopted; R-6)
- **Per simulator step,** `step(now_ns, radar=None|message, perception=None|record)` returns one `adas-cycle`
  record.
- **The decision cycle** is a step with F08 or a perception output delivered (R-6). Each source uses its newest
  item within its freshness window, so camera and radar from adjacent steps can pair.
- **A step with neither delivered** gives a record with reason `no-input`, `present = false` and state `UNCERTAIN`.
  - The request is `brakeLevel` while latched, else 0.0, so a missing input never drops an active brake for one
    step.
  - It does not count toward the latch's absence count.
- **Camera usable:** a well-formed `assured-aeb.perception-output/1`, with a state of `NOMINAL` or `DEGRADED`, and
  fresh.
  - **Camera-positive:** usable, `occupancyProbability ≥ threshold`, and `oodFlag` false.
  - **Association:** the radar distance lies in the predicted bin's interval widened by the tolerance on both sides
    (`overlap` is (−∞, 0]; `bin-i` is [e_{i−1}, e_i) with e_{−1} = 0; `beyond` is [e_last, ∞); `no-obstacle` has
    no interval).
- **The perception-output schema is fixed here for increment #3:**
  - its members are `schema`, `source`, `frame`, `frameSha256`, `originNs`, `occupancyProbability`,
    `binProbabilities`, `predictedBin`, `oodScore`, `oodFlag`, `inputQuality`, `provenance`, `state` and `reason`
    (design §4.3);
  - fusion checks all of them, and uses the probability, bin, OOD flag, state and origin.
- **Outcomes:**

  | Case | `present` | Outcome state | Reason |
  | --- | --- | --- | --- |
  | camera unusable | false | `UNCERTAIN` | `camera-unusable` |
  | radar unusable | false | `UNCERTAIN` | `radar-unusable` |
  | `agree`: camera-positive and associated radar | **true** | — | — |
  | `camera-only`: camera-positive, no associated in-corridor radar | false | `UNCERTAIN` | — |
  | `radar-only`: an in-corridor radar detection, camera not positive | false | `DEGRADED` | — |
  | `none` | false | — | — |

  - The `adas-cycle` state is the weakest of the camera state, the radar state and the outcome state (AD-35).
  - On `agree`, `d` and `v` are the radar's, because the camera gives a bin, not a range.
- **The `adas-cycle` record:**
  - `schema`, `source`, `cycle`, `sequence` and `originNs`, where `originNs` is `now_ns`, the absolute world clock;
  - `brakeRequest`, `fired`, `latched` and `reason`;
  - `hypothesis`: `present`, `agreement`, `distanceM`, `closingSpeedMps`, `distanceUncertaintyM`,
    `speedUncertaintyMps` and `residualM`;
  - `sources`: the camera's state, `originNs`, `ageNs`, `frameSha256`, probability, bin, OOD flag and provenance; the
    radar's state, `originNs`, `ageNs`, sequence, count, failures and the selected detection index;
  - `state` and `paramsSha256`.
- No pixels. The record stays far below the 65 536-byte hub line.

### 1.6 Radar-only fallback (U5)
- `step(now_ns, radar=None|message, ego_speed=None|{speedMps, originNs, state})` returns one `fallback-request`
  record per step.
- `ego_speed` is the **qualified vehicle-state evidence** that the WP-14 validator must supply. This form is an
  obligation on WP-14.
- **The ego speed gates firing.** Fallback fires only when all of these hold:
  - radar usable;
  - ego speed fresh, finite, `NOMINAL` or `DEGRADED`;
  - ego speed ≤ `fallback.oddMaxEgoSpeedMps`.

  Above the bound, state `UNSAFE` with reason `outside-degraded-odd`. With speed unknown or stale, `UNCERTAIN`.
- **A held latch continues until its own release condition,** even when the ODD gate fails. This refines design
  §3.3, which said only "0.0 outside the bound": while braking, speed only falls, so a failing gate while latched
  means missing or invalid speed evidence, and holding is the conservative response. **Flagged for review.**
- **The record mirrors `adas-cycle`** without the camera: `schema`, `source`, `cycle`, `sequence`, `originNs`,
  `brakeRequest`, `fired`, `latched`, `reason`, `hypothesis` (`agreement` is `radar-only`), the radar and ego-speed
  sources, `state` and `paramsSha256`.

### 1.7 Functional arbiter (U5, R-3 restricted)
- **Per decision cycle,** `step(now_ns, inbox)` takes `(interface, message)` pairs on `adas-cycle`,
  `fallback-request`, `selector-command` and `qualified-evidence`. It returns **exactly one** WP-04
  `brake_request(sequence, originNs = now_ns, value)`, with the five members unchanged, and appends one
  `assured-aeb.arbiter-cycle/1` evidence record.
- **The selector.**
  - The accepted form is `assured-aeb.selector-command/1`: `{schema, source: "configuration-manager", sequence,
    originNs, configuration}`, with `configuration` one of `C_NOMINAL`, `C_DEGRADED_RADAR` or `S_MRC_REQUESTED`.
    This form is an obligation on WP-14.
  - Any other source, a sequence that does not increase, or an unknown configuration is refused and recorded (A-3).
  - Before the first selector, the request is 0.0 with reason `no-selector`.
- **Fresh:** a request delivered at this step on the selected source's interface, with a sequence greater than the
  last used, an age within `arbiter.requestFreshnessNs`, and a finite `brakeRequest`.
  - It is sent clamped to [0, 1]. `clamped` and the raw value are recorded (WP-04 MEDIUM-1).
- **Otherwise,** the arbiter holds the **selected source's** last valid request while
  `now − its originNs ≤ arbiter.holdWindowNs`, then sends 0.0 with reason `no-valid-source`.
  - **The hold is per source.** Under the strict reading of R-3 ("never selects a source other than the
    selector's"), a value from the previously selected source is not held after a switch. Flagged for review.
  - A non-finite value is never sent: it counts as not fresh and is flagged `non-finite`.
- **`UNCERTAIN` and `UNSAFE` are forwarded, not acted on.**
  - The selected request's `state` and `reason` go into the arbiter-cycle record, keyed by the brake-request
    sequence.
  - The WP-04 brake-request vocabulary is **not widened**: the chassis zone refuses any member beyond the five.
  - Widening it (`brake-request/2`, with changes to the chassis zone and the node) is the alternative, recorded
    for review.
- **Qualified evidence** is received and counted in evidence only. The arbiter makes no decision on it in this
  increment, and its use is WP-14's.
- **The arbiter-cycle record:**
  - `schema`, `sequence`, `originNs`, `configuration` and `selectorSequence`;
  - `selectedInterface`;
  - `kind` (`fresh`, `held`, `no-valid-source` or `no-selector`);
  - `value`, `rawValue` and `clamped`;
  - `sourceSequence` and `sourceOriginNs`;
  - `forwardedState` and `forwardedReason`;
  - `refusals`.

### 1.8 Tests (T-3 to T-6 and T-9 of design §7)
- **Projection:** a missing identifier, a wrong type, a non-finite number and an unconsumed entry are each refused.
- **Radar:** the qualification table; the corridor boundaries; the mount offset; the sign parameter; deterministic
  nearest selection.
- **Rule:** `r ≤ 0` at the boundary; the widening by δd and δv; `v_c` clamped at 0.
- **Latch:** set; held on present but non-firing; released by speed; released by absence; a no-input step neither
  counts nor drops the brake.
- **Fusion:** every outcome row; association at the bin-edge tolerance; freshness pairing across adjacent steps; a
  malformed perception output.
- **Fallback:** the ODD gate (`UNSAFE`) and unknown speed (`UNCERTAIN`); the latch held through a gate failure.
- **Arbiter:**
  - exactly one request per step;
  - the WP-04 five-member form, accepted by `ChassisZone` and `BrakeEscNode`;
  - the clamp and its flag;
  - the hold window, then `no-valid-source`;
  - no switch to the fallback when `adas-cycle` is missing (an ADAS freeze);
  - `UNCERTAIN` forwarded, not acted on;
  - selector refusals;
  - the per-source hold;
  - `S_MRC_REQUESTED` following `arbiter.mrcSource`.
- **Determinism (T-9):** identical input streams give identical record streams, and a shift of the world epoch
  shifts only the absolute stamps.
- **No ML import:** the U4 and U5 logic modules import no `onnxruntime`, `numpy` or perception code (AST scan).

### 1.9 Residuals expected at the start
1. Every value is `TODO` (AD-05, AD-06, AD-07, AD-27, D-1, D-2), and so are the identifiers and the projection
   form.
2. The radar velocity sign (D-2) and ground clutter, with no altitude gate.
3. Obligations on WP-14:
   - the qualified ego-speed record for the fallback;
   - the selector-command form;
   - the use of qualified evidence;
   - the U5 decision-cycle cadence in the unit entry point.
4. Obligations on increment #3: produce the perception-output schema of §1.5.
5. Flagged choices:
   - the fallback latch held through an ODD-gate failure (§1.6);
   - the per-source hold (§1.7);
   - the state forwarded in the arbiter evidence rather than in a widened brake request (§1.7).
6. The FR-007 field completeness of `adas-cycle` (validity window identifier and synchronisation quality) is
   checked by the WP-14 validator. This increment carries only the stamps, ages, states and provenance listed here.

## Finding 2: implementation result (2026-10-24 15:54:11)

**Files.**
- `assured_aeb/parameters.py`: `Projection`, `take` and `check_exact`, and `params_digest`.
- `assured_aeb/aeb_rule.py`: `weakest`, `qualify_radar`, `nearest_in_corridor`, `Rule` and `Latch`.
- `assured_aeb/fusion_aeb.py`: `FusionRiskAeb` and `bin_interval`.
- `assured_aeb/vc_functional.py`: `RadarFallback` and `FunctionalArbiter`.
- `tests/test_aeb_logic.py`: 47 tests.

**As designed in finding 1.** Details that the design left open:
- **Fallback decision cycle.** It is a step with F09 delivered. Ego-speed updates alone are not decision cycles. The
  WP-14 unit entry fixes the U5 cadence.
- **Arbiter hold.** It is measured from the held request's `originNs`, and is inclusive at the window.
- **Arbiter, selector with no source.** A configuration with no source (`arbiter.mrcSource = none` under
  `S_MRC_REQUESTED`) gives 0.0 with kind `no-valid-source`.
- **Arbiter, reused or out-of-order sequences.** A request whose sequence was already used is refused
  (`request-refused`). Requests delivered at the same step are taken in sequence order, and the newest fresh one is
  sent.
- **Arbiter guard.** A non-finite value after clamping is unreachable, because raw values are finite. The guard is
  kept.

**Test fixture correction during the run** (not a logic defect). The fusion case "none" first placed its detection
at an azimuth of 0.5 rad. That is outside the radar's configured ±15° field of view, so the real smart radar correctly
failed plausibility and fusion reported `radar-unusable`. The fixture now uses 0.2 rad, which is in view and outside
the corridor (y = 5.96 m).

**Determinism stream (T-9).** The test also checks that the stream exercises the rule. All eight cycles agree, and
the request is 0.0 on six cycles and 1.0 on two, firing at d = 9.6 m. Identical inputs give identical streams. A world
epoch shifted by 7 s gives the same stream relative to its epoch.

**Commands** (`/dev/shm/compat-p6-venv/bin/python -I`, rc.1 profiles):
- `tests/test_aeb_logic.py`: 47 passed;
- the whole suite: 334 passed (287 on main);
- `check_topology.py`: exit 0;
- `__pycache__` removed.

**Residuals** (finding 1 §1.9, unchanged):
1. Every value, every identifier and the projection form are `TODO` (AD-27). The tests use TEST-ONLY values.
2. The radar velocity sign (`radar.closingSpeedSign`, D-2 verification) and ground clutter, with no altitude gate.
3. WP-14 obligations:
   - the qualified ego-speed record `{speedMps, originNs, state}`;
   - `assured-aeb.selector-command/1`;
   - the use of qualified evidence;
   - the U4 and U5 cadences in the unit entry points.
4. Increment #3 obligation: produce `assured-aeb.perception-output/1` with exactly the members of §1.5.
5. Flagged for review:
   - the fallback latch held through an ODD-gate failure;
   - the per-source hold after a selector switch;
   - the state forwarded in the arbiter-cycle evidence rather than in a widened brake request.
6. FR-007 completeness of `adas-cycle` is the WP-14 validator's.
7. Freeze consistency checks, recorded for AD-27:
   - `fusion.corridor.*` must equal the WP-09 label corridor;
   - `fusion.distanceBinEdgesM` must equal the label bin edges.

**Status.** Engineering evidence on the candidate only. The independent review, acceptance and the merge are pending.
