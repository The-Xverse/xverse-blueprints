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
    0 of the `carla-simulation` domain.
  - A sample is emitted for an input item whose slot is greater than the last emitted slot, and its
    measurement time is the item's `originNs` (zero-order hold on the newest frame).
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
