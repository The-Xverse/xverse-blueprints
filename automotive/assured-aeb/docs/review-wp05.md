# WP-05 review log: modelled motion sensor (Phase 8; FR-004, AD-32 option C)

Candidate: branch `candidate/phase8-wp05-motion-sensor-20261024`, from blueprints main `7851c47`. This is a
direct engineering increment, and the log follows the same order:
1. findings come before repairs;
2. an independent read-only review;
3. acceptance;
4. a merge.

None of the last three has happened yet.

**Inputs.**
- Thesis `specs/002-assured-aeb`:
  - `implementation-plan.md` WP-05;
  - `spec.md` FR-004, FR-021, FR-023, V14 and V24;
  - `decisions.md` AD-32 option C, AD-30, AD-31, §J (U2 hosts the motion-sensor model), §K (relay
    admission) and "WP-04 fault status";
  - `review/decision-proposals-20261024b.md` §3 (AD-32 rationale);
  - `review/freeze-readiness-20261024.md` §2 (class J);
  - `design/wp12-xdl-topology.md` §4.
- This repository's WP-12 topology:
  - F03 `motion-raw` (adapter → `loop-gateway`), with intra messages `loop-gateway → motion-sensor-model`
    and `loop-gateway → driver-profile`;
  - F10 `motion-chassis` (`motion-sensor-model` → `chassis-zone`, latency kind `sensor-sampling`,
    no relay admission).
- `xverse-compat` main `34cc046`, read-only:
  - `xverse_compat_carla/sensors.py` `motion_value`: the adapter item value `{speedMps, accelForwardMps2}`,
    from `world.get_snapshot()`;
  - `xverse_compat/live/driver_profile.py` `_motion`: the driver reads only an item with
    `flowId == "vehicle-motion"`;
  - `xverse_compat_carla/observe.py` 1–16: the WP-01 observer writes evaluation-only JSON Lines, schema
    `xverse-compat.evaluation-observer/2`, with header `evaluationOnly: true`.

**Scope.** Offline module and tests only. No live run, no CARLA, no unit process. This is engineering
evidence only.

**Record note.** The first commit of this log (`39722ef`) committed an empty file, because a shell
quoting error truncated the heredoc. It is replaced by this content in the amended commit, before any
code. The time below is the time of the corrected record.

## Finding 1: design (recorded at 11:40:57, before any code)

### 1.1 Role and boundary
- **What it is.** The motion sensor is a **declared model** of a vehicle-motion sensor (AD-32 option
  C). It is not a fabricated CARLA signal: the author confirmed that it is distinct from [028] 34.
  It turns the adapter's snapshot-derived `vehicle-motion` item, which is **only its input**, into a
  measurement with declared sampling, quantisation, seeded noise and latency.
- **Where it runs.** It is a module of U2 `vehicle-loop`, in its sensor-model stage (§J). Its only
  output is the `motion-evidence` item on **F10** to `chassis-zone` (U5). That flow is its own and is
  distinct from the WP-01 ground-truth observer, which is a separate process outside Maestro with its
  own output root (WP-11 §2.3; FR-021).
- **Inputs it accepts.** It reads only items with `flowId == "vehicle-motion"`, delivered by the
  gateway (the F03 intra message). It refuses and counts anything else: an evaluation-observer header
  or row (`evaluationOnly`, or schema `xverse-compat.evaluation-observer/*`), an item with another
  `flowId`, or a malformed item. It imports no observer, evaluation or oracle code.

### 1.2 Model (deterministic, keyed to simulation time)
- **Sampling grid.**
  - Sample slots are `k = floor(originNs / samplingPeriodNs)` on the simulation-time grid, with epoch
    0 of the `carla-simulation` domain. *[Corrected in finding 5: `k = floor((originNs − episodeOriginNs) /
    samplingPeriodNs)`, with the episode origin bound late from the first frame (finding 4, HIGH-1).]*
  - A sample is emitted for an input item whose slot is greater than the last emitted slot, and its
    measurement time is the item's `originNs`. *[Corrected in finding 5: the sample is the first frame in each slot.
    The original text read "zero-order hold on the newest frame"; the slot and noise key are episode-relative
    (finding 4).]*
  - An item whose `originNs` does not advance, or whose slot was already sampled, emits nothing.
  - So the sensor never invents a sample between frames, and a frozen or stalled input goes stale
    downstream.
- **Noise.**
  - The model is additive Gaussian white noise per channel: speed (`speedNoiseStdMps`) and forward
    acceleration (`accelNoiseStdMps2`).
  - The draw for slot `k` and channel `c` comes from a generator seeded by `SHA-256(seed, k, c)`, so it
    depends only on the seed and the simulation-time slot.
  - The stream is therefore reproducible for a seed, independent of missed earlier samples, and
    identical in both arms of a pair up to the first divergent input (PAIR-1).
- **Physical bound.** Speed is a magnitude, so a negative noisy speed is clamped to 0, as a declared
  model rule.
- **Quantisation.** `round(x / q) * q` per channel (`speedQuantumMps`, `accelQuantumMps2`), applied
  after the noise. Python `round` is ties-to-even and deterministic.
- **Latency (AD-30).**
  - The output carries `originNs` (measurement time) and `deliverAtNs = originNs + latencyNs`.
  - `latencyNs` **is** F10's modelled sensor-sampling latency (latency kind `sensor-sampling` in
    WP-12). One AD-30 entry gives both, so the hub delivers at `deliverAtNs` and must not add F10's
    latency a second time.

### 1.3 Parameters (no defaults; values TODO, class J)
- **Record** `assured-aeb.motion-sensor/1`, with exactly these members:
  - `samplingPeriodNs`: integer > 0;
  - `speedQuantumMps` and `accelQuantumMps2`: > 0;
  - `noiseModel`: `gaussian-additive`;
  - `speedNoiseStdMps` and `accelNoiseStdMps2`: ≥ 0;
  - `seed`: integer ≥ 0;
  - `latencyNs`: integer ≥ 0.
- `MotionSensorParams.from_record` refuses a missing, extra, ill-typed or out-of-domain member. The
  digest of the canonical record is carried in every output (provenance), as WP-03 does.
- **Values.** Every value is `TODO: author decision` (AD-27). Freeze-readiness class **J**
  (justification source: "AD-32 noise model") requires each value to carry a recorded justification
  source when it is set: a sensor datasheet class, a cited reference, or a characterisation. The seed
  comes from the P-4 disjoint seed lists. **No value is set here.** Tests use labelled test values.

### 1.4 Output message (`assured-aeb.motion-evidence/1`; closed members)
- `schema`, `source` (`motion-sensor-model`), `sequence`, `slot`, `originNs`, `deliverAtNs`,
  `speedMps`, `accelForwardMps2` and `modelDigest`.
- **Not carried:** the input values, the noise draws, the true speed, and any evaluation member. The
  evidence validator (WP-14) adds the FR-007 reception, age and validity fields.

### 1.5 Fault hooks
- **None is needed for a decided case.**
  - AD-31's principal conditions are camera corruption (U2 imaging stage), radar faults on F09 and
    ADAS/AD `freeze`.
  - H4-01 to H4-09 act on the monitor and gate, the manager and rollback, ADAS/AD, `radar-vc`, the
    front zone and the proposal path.
  - §K admits no relay fault on F10.
- **No hook is implemented.**
- **If one is admitted later** (for example dropout, stuck-at or bias, for an AD-13 revision), it is
  applied in this U2 sensor-model stage, never in a role unit (§J; FR-028). Any fault indication is
  evidence-only, as decided for WP-04 ("WP-04 fault status"). AD-32's "FR-023 fault hooks" therefore
  have no Phase 8 instance; this is recorded as a residual.

### 1.6 Integration with WP-03's driver (E-5)
- The driver profile reads the adapter's raw `vehicle-motion` item, delivered by the gateway through
  the WP-12 intra message `loop-gateway → driver-profile` (`motion-raw`). It uses that item for
  scenario control only (E-5; FR-030).
- It does not read the motion sensor: WP-03 `_motion` accepts only `flowId == "vehicle-motion"`, and
  the sensor's item has schema `assured-aeb.motion-evidence/1` and no `flowId`.
- The driver is part of the scenario environment and is not a runtime role, so this does not affect
  DYN-002.
- **Confirmed and recorded.**

### 1.7 Files and tests (planned)
- **`assured_aeb/motion_sensor.py`** (standard library: `hashlib`, `random`, `math`): `MotionSensorParams`,
  `MotionSensor` and `check_output`.
- **`tests/test_motion_sensor.py`:**
  - the parameter record without defaults;
  - sampling slots, with no inter-frame invention and a stalled input giving no sample;
  - quantisation and the clamp;
  - determinism: the same seed gives the same stream, a different seed differs, and noise is keyed by
    slot (independent of earlier gaps);
  - the latency stamp;
  - the closed output vocabulary;
  - V14: values differ from the input by the declared model, and with noise 0 they equal the quantised
    input;
  - separation: the sensor refuses observer header and rows and other flows; an import scan of the
    module; no evaluation element consumes `motion-evidence` in the topology; no oracle or evaluation
    module in the blueprint imports the sensor;
  - the E-5 confirmation against the topology.

### 1.8 Expected residuals
1. Parameter values and their class-J justification sources (AD-27).
2. No Phase 8 fault hook (§1.5).
3. Hub delivery at `deliverAtNs` and the single-latency rule (WP-10).
4. The oracle is not yet implemented (WP-17). Its separation test here is structural; the V14 import
   scan must be repeated when the oracle exists.

## Finding 2: implementation result (2026-10-24 11:43:07; commit `329eaf4`)

**What was added.**
- `assured_aeb/motion_sensor.py` (standard library only): `MotionSensorParams`, `MotionSensor`, `noise`,
  `quantise` and `check_output`.
- `tests/test_motion_sensor.py`: 40 tests.

**Commands.**
- `/dev/shm/compat-p6-venv/bin/python -I -m pytest tests/test_motion_sensor.py`: **40 passed**.
- The whole blueprint suite with `XVERSE_PLATFORM_PROFILES` (rc.1 export): **114 passed**.
- `check_topology.py`: exit 0. The WP-12 documents are unchanged.
- Host load 4.85. No live run, no CARLA; the loop10 worktrees and the pinned live environment were not
  touched.

**Results against the design (finding 1).**

| Design item | Implemented and tested |
| --- | --- |
| Parameters §1.3 | Every member is required (one test per member); extra members, the wrong schema and out-of-domain values are refused; the sensor cannot be built without a validated record. The record digest is in every output (`modelDigest`) |
| Sampling §1.2 | One sample per simulation-time slot `floor(originNs / samplingPeriodNs)`. There is no sample between grid instants. A non-advancing or rewinding input is refused (`not-advancing`), and a gap yields one sample for the next frame, with none invented |
| Noise and determinism | The draws are a function of seed, slot and channel only: the same seed gives an identical stream, a different seed differs, and noise is independent of earlier gaps. Paired streams are identical up to the first divergent input (PAIR-1) |
| Model rules | Speed is clamped at 0. Quantisation is on the declared grid. With zero noise, the output is the quantised input. With the test noise, the speed error has the declared spread (V14: "values differ by the declared model") |
| Latency | `deliverAtNs = originNs + latencyNs`; one AD-30 entry shared with F10 (§1.2) |
| Output vocabulary §1.4 | Closed `motion-evidence/1` members. No input value, true value or noise draw is carried |
| Separation | The sensor refuses the WP-01 observer header and rows (`evaluationOnly`, schema `evaluation-observer/*`), other flows and malformed items. An AST import scan shows the module imports only standard-library modules. No blueprint oracle, evaluation, observer or metric module imports it. In every arm the topology sends `motion-evidence` only to `chassis-zone`, admits no relay fault on F10, and has no observer or oracle element |
| E-5 §1.6 | The topology gives the driver the adapter item (`loop-gateway → driver-profile`, `motion-raw`), not the sensor. The sensor's item has no `flowId`, so WP-03 `_motion` would refuse it. Confirmed |
| Fault hooks §1.5 | None (no decided case). No hook code exists |

All parameter values in the tests are labelled test values (50 ms grid, quanta 0.01, noise σ 0.1 and
0.2, seed 7, latency 20 ms). No protocol value is set.

**Residuals.**
1. **Model values and their class-J justification sources** (AD-27). The seed comes from the P-4
   lists.
2. **No Phase 8 fault hook.** AD-32's "FR-023 fault hooks" have no decided instance. A later hook goes
   in this U2 stage and is evidence-only ("WP-04 fault status").
3. **Hub delivery** at `deliverAtNs`, with F10's latency not added a second time (WP-10). The U2 wiring
   that passes the gateway's F03 item to the sensor is WP-10/WP-13.
4. **The oracle does not exist yet** (WP-17). The separation test here is structural and must be
   repeated as the V14 import and process scan when it exists.
5. **The sensor's time base** is the `originNs` of the adapter item, the absolute CARLA world
   simulation clock. Episode-relative consumers must convert, as the WP-04 review found for F17.

The next step is an independent read-only review of `329eaf4`, then acceptance and merge.

## Finding 3: independent review of findings 1 and 2 (2026-10-24 11:50:32)

**Reviewer and method.**
- An independent, read-only reviewer who did not write this increment.
- Read `5f20a0b`, `329eaf4` and `d89530e` against base `7851c47`, and checked them against thesis FR-004,
  V14, AD-32 option C, AD-30, PAIR-1 (`decisions.md` 221), §J and §K. Also read the WP-12 topology on this
  branch, and compat `driver_profile.py` and `live/loop.py` at main `855878a`.
- **Record note, verified.** `39722ef` committed an empty `docs/review-wp05.md` (0 lines). The amended
  `5f20a0b` (150 lines) precedes the code commit `329eaf4` (11:43:07), so the design was recorded before
  any code.
- Commands (`/dev/shm/compat-p6-venv/bin/python -I`, rc.1 profiles from a scratch export):
  - `tests/test_motion_sensor.py`: 40 passed;
  - the whole blueprint suite: 114 passed;
  - `check_topology.py`: exit 0.
- In-memory probes: the same episode-relative trajectory at different world epochs, and the sampling
  phase on a 100 ms grid. Nothing in the worktree changed except this entry. No CARLA, no live run.

### Verdict: **FAIL: one HIGH issue blocks the merge** (a small repair)

This is the residual 5 class, the same class as WP-04 HIGH-1. It breaks PAIR-1 and run-to-run
reproducibility. Everything else is sound.

### Confirmed
- **Sampling** (motion_sensor.py 151–159).
  - At most one sample per slot `originNs // samplingPeriodNs`. A non-advancing or rewinding input is
    refused (`not-advancing`), and a repeated slot emits nothing.
  - There is never a sample without an input frame, so no sample is invented between frames.
- **Noise** (92–98). Each draw is a fresh `random.Random` seeded from `SHA-256(params schema | seed | slot
  | channel)`, so it depends only on seed, slot and channel, with no history state.
- **Clamping and quantisation** (160–165).
  - Speed is clamped at 0 after the noise and before quantisation. The signed acceleration is not
    clamped.
  - Quantisation is `round(x / q) · q`.
  - With zero noise, the output is the quantised input.
- **Parameters.** An exact-member record with no defaults, integer period, seed and latency, positive
  quanta and non-negative σ. The canonical digest is carried as `modelDigest`.
- **Latency.**
  - F10 is not in WP-12's `HUB_DELAYED` set (F04, F14, F15b, F17), and the sensor stamps
    `deliverAtNs = originNs + latencyNs`. So the hub step is not added to F10, and the single AD-30
    entry is stated (residual 3).
  - See LOW-3 for the element's `computeLatency`.
- **Separation (V14, FR-021).** The module imports only standard-library modules. It refuses
  `evaluationOnly` and `evaluation-observer` content and other flows. In every arm the topology sends
  `motion-evidence` only to `chassis-zone`, admits no relay fault on F10, and declares no observer or
  oracle element.
- **E-5.** The driver receives `motion-raw` from `loop-gateway` (topology.py 235), and WP-03 `_motion`
  accepts only `flowId == "vehicle-motion"`. The sensor item has no `flowId`, so the driver cannot read
  it. Confirmed.

### Issues

**HIGH-1: the sampling grid and the noise are keyed to the absolute world clock, so two arms (or two
repeats) of the same episode get different noise and a different sampling phase.** This blocks the
merge.
- Where: motion_sensor.py 156 and 160–161; finding 1 §1.2 ("epoch 0 of the `carla-simulation` domain");
  residual 5.
- `slot = originNs // samplingPeriodNs`, and the noise key is that slot. `originNs` is the absolute
  CARLA `elapsed_seconds` clock, which keeps running across runs on one server (the Phase 7 and S1 runs
  do not reload the world).
- Probe: an identical episode-relative trajectory (10 m/s, six 50 ms frames, seed 7, test σ):
  - world at 1000 s: speeds `[10.06, 10.09, 10.09, 10.16, 9.89, 10.13]`;
  - world at 1600 s: `[9.8, 10.06, 9.95, 9.9, 9.88, 10.06]`.
- With a 100 ms grid, the sampled frames are `[0, 2, 4]` or `[0, 1, 3, 5]` depending only on the
  epoch's offset modulo the period.
- PAIR-1 requires "the sensor observations of the two arms are identical up to the first divergent
  action". The arms of a pair start at different world times, so this fails before any divergence. D-5
  repeatability is affected the same way.
- `test_paired_arms_see_identical_evidence_up_to_the_divergent_input` (test_motion_sensor.py 119–127)
  feeds both arms identical *absolute* origins, which hides the issue.
- Repair:
  - key `slot` (and therefore the grid and the noise) on episode-relative time,
    `originNs − episodeOriginNs`;
  - keep the absolute `originNs` and `deliverAtNs` stamps for the hub and U5;
  - make the episode origin a required input with no default. Given WP-04 finding 6 MEDIUM-A, it should
    be bound late from the first frame (the loop's `episode_ns`), and the sensor refuses to sample until
    it is bound;
  - add a PAIR-1 test with two different world epochs.

### Consumers of the absolute stamps (residual 5)
Each consumer was checked against the clock it uses:
- **The hub (WP-10).** It delivers F10 at the absolute `deliverAtNs`. The U2 hub sees absolute frame
  `originNs`, so this is consistent.
- **The chassis zone, vehicle state and evidence validator (WP-04, WP-14).** They take absolute integer-ns
  `sim_ns`, as the WP-04 node does, so the FR-007 ages are consistent.
- **The offline oracle and V34 joins.** They are absolute, consistent with WP-01 `simElapsedNs` and the
  frame.
- **The driver.** It does not consume the sensor.

The only consumer that is wrong is the sensor's own grid and noise key (HIGH-1).

### New notes (LOW, none blocking)
- **LOW-1: the noise stream depends on `random.gauss`.** CPython guarantees reproducibility only for
  `random()` under a compatible seeder, not for `gauss()` across versions. U2 is pinned to 3.13.13, so
  record that pin as a reproducibility condition, or derive the Gaussian from `random()` with a declared
  Box–Muller transform.
- **LOW-2: wording.** Finding 1 §1.2 says "zero-order hold on the newest frame", but the code samples
  the *first* frame that falls in a new slot. Quantised values also carry float artefacts (for example
  `9.950000000000001`). That is harmless, but the record should not claim exact grid values.
- **LOW-3: a third latency entry.** WP-12 also declares `computeLatency` (`TODO: author decision
  (AD-30)`, topology.py 454) for the `motion-sensor-model` element instance. State that `latencyNs`
  subsumes it (or that it is 0), so AD-30 does not count the sensor delay twice.
- **LOW-4: the hub's step quantises the latency.** With `latencyNs` 20 ms and 50 ms steps, delivery at
  `deliverAtNs` happens at the next step boundary, an effective 50 ms. The AD-30 declaration should say
  whether `latencyNs` is applied exactly or rounded up to the step (residual 3).

### Residuals 1 to 5
- Residuals 1 to 4 are accurate.
- Residual 5 is correct about the stamps but misses the sensor's own keying (HIGH-1). After the repair,
  it should state the split: absolute stamps, episode-relative grid and noise.

### Recommendation
- Repair HIGH-1 with a two-epoch PAIR-1 test.
- Record LOW-1 to LOW-4.
- Then a focused re-review, followed by acceptance and merge.

## Finding 4: disposition of finding 3 (2026-10-24 11:54:15; recorded before any change)

This disposition is the coordinator's, under the author's delegation, and is flagged for the author's
review. It applies `decisions.md` "AD-30 delivery rule" (11:51).

| Item | Disposition | Planned change |
| --- | --- | --- |
| HIGH-1 | Repair | Key the sampling slot and the seeded noise on episode-relative time, `originNs − episodeOriginNs`. The origin is bound late, once, from the first frame (`bind_origin`; a different second value is refused), and no sample is emitted until it is bound. The absolute `originNs` and `deliverAtNs` stamps stay. New test: PAIR-1 with two different world epochs, which fails on `329eaf4` |
| LOW-1 | Repair | Replace `random.gauss` with a declared Box–Muller transform over two `random()` draws of a generator seeded by an integer. CPython's Mersenne Twister `random()` sequence for an integer seed is stable across versions, and `gauss()` is not part of that guarantee |
| LOW-2 | Repair | The wording becomes "the first frame in each slot" (the code is kept: the slot's first frame is the earliest measurement and does not wait for the slot to end). Quantisation uses integer arithmetic: the value is rounded to an integer number of quanta, and the result is rounded to the quantum's decimal precision |
| LOW-3 | Record | `latencyNs` covers the element's WP-12 `computeLatency` for `motion-sensor-model`, so AD-30 declares the sensor delay once |
| LOW-4 | Record | Cite the AD-30 delivery rule: the hub delivers at the first step boundary at or after `deliverAtNs`, so the declared latency is rounded up to whole steps, and the declaration states both values |
