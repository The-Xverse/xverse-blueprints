# WP-10 increment #1 review log: the blueprints fault-admission path

Candidate: branch `candidate/phase8-wp10-admission-20261024`, from blueprints main `5f71cde`. This is a direct
engineering increment, and the log follows the same order:
1. findings come before repairs;
2. an independent read-only review;
3. acceptance;
4. a merge.

None of the last three has happened yet.

**Inputs.**
- Thesis `specs/002-assured-aeb/decisions.md`: the row "WP-10 fault relay" (12:11; option (A) decided; increments
  #1–#5; no fault admitted in any live Phase 8 run until (A) is merged), §K, "AD-30 delivery rule" and "WP-04
  fault status".
- `design/wp10-fault-relay.md`:
  - §3: the admitted targets, enforced twice, at admission and again by the hub when it arms;
  - §4: the step-hold handshake and the inequality `D/step × max_step_host + 2 × handshake ≤ thaw_bound`;
  - §5: the admission order and the FreezeBound input validation (WP-12 LOW-B);
  - §6: the increments.
- This repository: `check_topology.py` (`FreezeBound`, `check_fault_admission`, `prepare`, `admit`) and
  `topology.py` (the two document forms).

**Scope.** Offline only. No CARLA, no live run; the soak's loop10 paths are not touched. No platform change:
option (A) is increment #3.

## Finding 1: design (recorded at 12:17:25, before any code)

### 1.1 The harness admission path (`admission.py`, beside `check_topology.py`)
`admit_run(arm, faults, *, freeze_bound, sim_bound, op, schema_paths, platform=..., prepare_fn=..., admit_fn=...)`
runs the order of design §5. The **first refusing stage stops the run**, and no later stage is called.

| Stage | Name | What it does |
| --- | --- | --- |
| 1 | `generate` | Generate the arm's documents in both forms (`topology.documents`): the topology form for the fault rule (flows), the Maestro form for the plan, with the faults |
| 2 | `bound-inputs` | Validate the FreezeBound inputs. They are needed only when at least one `freeze` is present. `thaw_bound_s` and `max_cycle_s` must be finite and > 0; a missing value refuses on this path (WP-12 LOW-B). The checker may still report "not bounded" offline |
| 3 | `sim-duration` | Under (A), the simulation-time duration check for every freeze: `SimTimeFreezeBound(thaw_bound_s, step_s, max_step_host_s, handshake_s)`, each finite and > 0, and `D/step_s × max_step_host_s + 2 × handshake_s ≤ thaw_bound_s`. `D` is the declared duration in simulation time, in `ns`, `us`, `ms` or `s`. `max_step_host_s` and `handshake_s` are `TODO: measurement` (D-4c), so while they are unknown (`None`) the stage refuses. A freeze with a tick-keyed duration is refused here, because under (A) freezes are keyed to simulation time (PAIR-1) |
| 4 | `fault-admission` | `check_fault_admission(topology_docs, faults)`: the targets, the CC-1 rule and the §K relay admission. Then the **interim gate**: while the platform does not provide option (A), every non-empty fault schedule is refused ("WP-10 interim: option (A) is not on the platform", decisions row "WP-10 fault relay") |
| 5 | `prepare` | Compile the Maestro form and `prepare_lifecycle` |
| 6 | `admit-schedule` | `admit_schedule` with the live parameters |

- **Platform capability.** `option_a_available(platform)` is the only switch of the interim gate. It is a
  declared capability probe, `xverse.faults.SIMULATION_TIME_TRIGGERS is True`. Increment #3 must provide that
  capability or change this probe in its ADR. On rc.1 it is absent, so the probe returns `False`. A test
  injects the probe to prove that the gate is the only remaining refusal for an otherwise valid schedule.
- **A fault-free run.** It skips stages 2–4, which only judge faults, and proceeds to stages 5–6. This is
  admission only: no live run is authorized (E8-3).
- **Result.** `AdmissionResult(admitted, stage, refusals, stages_run, schedule)`. `stages_run` lists the stages
  entered, so a test can prove that `admit-schedule` was never reached.

### 1.2 FreezeBound input validation (LOW-B)
- `check_topology.FreezeBound` gains validation in `__post_init__`: `thaw_bound_s` and `max_cycle_s` finite and
  > 0, otherwise `ValueError`.
- The offline checker's calls are unchanged in behaviour.

### 1.3 The hub's re-check at arming (interface stub for increment #4)
- `ArmDescriptor`: the minimum descriptor the dispatcher sends to the hub (design §3), with `entryId`,
  `targetElement`, `kind`, `onsetNs`, `durationNs` and `parameters`.
- `HubArmingRecheck`, with two calls:
  - `recheck(descriptor, topology_docs) -> list[str]` repeats the target and kind rule for one descriptor:
    relay flows with their admitted kinds, and the admitted freeze units. This part is implemented, because it
    is the same rule;
  - `arm(descriptor)` raises `NotImplementedError("WP-10 increment #4: hub relay")`.

  The control channel and handshake are increment #3's interface and #4's implementation.

### 1.4 Tests (planned) `tests/test_admission.py`
- **The order and stopping.** For each refusing stage (bound inputs, simulation-time duration, fault
  admission, interim gate), a spy `admit_fn` and `prepare_fn` are never called, and `stages_run` ends at the
  refusing stage.
- **A fault-free arm** reaches `admit-schedule` and is admitted at op 0.29 (6 units; MLOC). This needs the
  platform profiles.
- **The interim position.** With the real capability probe on rc.1, every fault schedule is refused: each
  admitted target kind, the CC-1 pair, and message faults on F09, F12 and F13.
- **With an injected (A) capability.** A valid schedule (a CC-1 pair with known bounds satisfying the
  inequality) passes stages 2–4. The inequality refuses a long `D`, and an unknown measurement refuses.
  These are test values, not D-4c values.
- **The FreezeBound validation** (zero, negative, NaN, infinite and bool values).
- **The hub re-check stub.** An admitted target passes, a non-admitted target is refused, and `arm` raises.

### 1.5 Expected residuals
1. The D-4c values `max_step_host_s` and `handshake_s`, and the step (K-10, 0.05 s) passed by the caller.
2. The capability name is provisional until increment #3's ADR.
3. The faults in the Maestro form compile to tick conversion at rc.1 (L-8); real Maestro admission of
   simulation-time faults needs (A).
4. Hub arming and the control channel (increments #3 and #4).

## Finding 2: implementation result (2026-10-24 12:19:43; commit `f0ecf6e`)

**What was added.**
- `admission.py`:
  - `admit_run`, the six-stage order;
  - `SimTimeFreezeBound` and `sim_duration_ns`;
  - `option_a_available`, the interim-gate capability probe;
  - `AdmissionResult`;
  - `ArmDescriptor` and `HubArmingRecheck`, the re-check plus the `arm` stub.
- `check_topology.FreezeBound` now validates its inputs.
- `tests/test_admission.py`: 27 tests.

**Commands.**
- `tests/test_admission.py` with the rc.1 profiles: 27 passed.
- The whole blueprint suite: 198 passed. Without the profiles: 167 passed and 31 skipped.
- `check_topology.py`: exit 0.
- Host load 4.9. Offline only: no CARLA, no live run; the loop10 paths and the pinned live environment were not
  touched.

**Results against the design (finding 1).**

| Item | Result |
| --- | --- |
| Order and stopping (§1.1) | Spies on `prepare_fn` and `admit_fn` prove that **`admit_schedule` is never reached after a refusal**, and that `stages_run` ends at the refusing stage. Four cases refuse at their own stage: a missing FreezeBound (`bound-inputs`), a missing simulation-time bound (`bound-inputs`), unknown D-4c values (`sim-duration`) and the interim gate (`fault-admission`). A rule refusal (a lone `vc-functional-unit` freeze) stops at `fault-admission` even with the (A) capability injected |
| Simulation-time durations | Under an injected (A) capability, with test bounds (step 0.05 s, `max_step_host` 0.1 s, handshake 0.2 s, thaw 3.26 s), a 500 ms CC-1 pair passes: 10 × 0.1 + 0.4 = 1.4 s. A 1500 ms pair is refused: 3.4 s > 3.26 s. A tick-keyed freeze is refused because PAIR-1 needs simulation time. Unknown inputs refuse |
| Interim position | The real rc.1 probe reports no (A) (`xverse.faults.SIMULATION_TIME_TRIGGERS` is absent, and a non-`True` value counts as absent). **Every fault schedule is refused with the interim message**: the CC-1 pair, freezes of the front zone, ADAS/AD and assurance units, `stale` and `loss` on F09, `proposal-unsafe` on F12, and `evidence-loss` on F13. Neither prepare nor admit is called |
| Fault-free arm | Reaches prepare and `admit_schedule` on the rc.1 platform and is admitted at op 0.29 with 6 units. The thaw bound the caller derives from the admitted schedule is 3.26 s. Admission only: no run is authorized (E8-3) |
| LOW-B | `FreezeBound` refuses zero, negative, NaN, infinite and bool values. `SimTimeFreezeBound.problems` reports each unknown or invalid input |
| Hub re-check (§1.3) | `recheck` admits `stale` on F09 and an admitted freeze unit, and refuses `loss` on F07 and a freeze of `carla-adapter-unit`. CC-1 pairing stays the admission rule's job. `arm` raises `NotImplementedError` naming increment #4 |

All bound values in the tests are labelled test values. None is a D-4c measurement or a protocol value.

**Residuals.**
1. **D-4c values.** `max_step_host_s` and `handshake_s` are unknown, so every freeze is refused at
   `sim-duration` even after (A). The step `step_s` (K-10, 0.05 s) and the thaw bound (from the admitted
   schedule) are the caller's inputs, never defaulted.
2. **The capability probe** `xverse.faults.SIMULATION_TIME_TRIGGERS` is provisional. Increment #3's ADR
   provides it or replaces the probe.
3. **Simulation-time faults in the Maestro form.** They still compile through the rc.1 tick conversion (L-8).
   Real Maestro admission of them, including `prepare` and `admit_schedule` with faults, needs (A). Under the
   injected capability, these stages are spies in the tests.
4. **Hub arming** and the control channel (increments #3 and #4). The re-check is implemented and `arm` is a
   stub.
5. **Message faults reach the hub** (topology form) and process faults reach Maestro (Maestro form). Under (A),
   both move into the single-domain Maestro schedule (design §4 item 6). The admission path then needs no form
   split for faults.
6. **The run command** that calls `admit_run` is increment #5.

The next step is an independent read-only review of `f0ecf6e`, then acceptance and merge. Neither has happened.

## Finding 3: independent review of findings 1 and 2 (2026-10-24 15:15:24)

**Reviewer and method.**
- An independent, read-only reviewer who did not write this increment.
- Read `43000e5`, `f0ecf6e` and `dcf36e4` against base `5f71cde`, and checked them against the thesis
  `decisions.md` row "WP-10 fault relay" (285) and `design/wp10-fault-relay.md` §3–§6.
- Commands (`/dev/shm/compat-p6-venv/bin/python -I`, rc.1 profiles from a scratch export):
  - `tests/test_admission.py`: 27 passed;
  - the whole suite: 198 passed; without the profiles, 167 passed and 31 skipped;
  - `check_topology.py`: exit 0.
- In-memory probes, using spies and an injected (A) stand-in only: the venv's `xverse.faults`, and five
  edge cases. Nothing in the worktree changed except this entry. No CARLA, no live run.

### Verdict: **PASS WITH NOTES. Nothing blocks the merge.**

On rc.1 the interim gate refuses every fault schedule, so nothing reaches Maestro. MEDIUM-1 and MEDIUM-2
are gaps that open only once (A) lifts the gate. They must be closed in increment #3 or #5, before the
gate is lifted. The merge still awaits acceptance.

### Confirmed
- **Order and stopping** (admission.py 98–147). The stages are `generate → bound-inputs → sim-duration →
  fault-admission (rule, then the interim gate) → prepare → admit-schedule`, and every refusal returns
  before `prepare_fn`.
- **The spies are genuine.** `Spy` counts calls and replaces `prepare_fn` and `admit_fn`. For the four
  refusing stages, both counts are 0 and `stages_run` ends at the refusing stage. The fault-free test uses
  the real `prepare` and `admit_schedule`.
- **The interim gate.** `option_a_available` imports `xverse.faults` and requires
  `SIMULATION_TIME_TRIGGERS is True`. In the pinned venv (`xverse_xdl` 0.4.0, rc.1 sources) the attribute
  is absent, and a non-`True` value, an `ImportError` or a missing attribute all count as absent.
  - Every rc.1 schedule tested is refused with `INTERIM`, with neither spy called: the CC-1 pair, the three
    single freeze units, `stale` and `loss` on F09, F12 `proposal-unsafe`, and F13 `evidence-loss`.
  - The probe name is the flag increment #3 is to provide (residual 2).
- **The simulation-time inequality.** `host_seconds = D/step_s · max_step_host_s + 2 · handshake_s ≤
  thaw_bound_s`, as in design §4 and the decision row. Unknown D-4c values (`None`) refuse at
  `sim-duration`, and each unknown or invalid input is reported.
- **FreezeBound validation** (check_topology.py `__post_init__`). Zero, negative, NaN, infinite and bool
  values are refused, as WP-12 LOW-B asked.
- **Lone `vc-functional`.** With (A) injected and known bounds, a lone `vc-functional-unit` freeze passes
  `sim-duration` and is refused at `fault-admission` by the CC-1 rule.
- **Fault-free arm.** It skips stages 2–4, is admitted on rc.1 at op 0.29 with 6 units, and the caller
  derives `cadence − health_scan_seconds = 3.26 s`.
- **The `HubArmingRecheck` rule** repeats the target and kind rule from the topology form (§K flows and
  kinds; the freeze targets), and `arm()` raises `NotImplementedError` naming increment #4.

### Issues (none blocks the merge)

**MEDIUM-1: under (A), only freeze *durations* are checked for simulation-time keying.**
- Where: admission.py 56–64 and 122–136.
- Probes with (A) injected:
  - a **tick-keyed F09 `stale`** fault is admitted through all six stages;
  - a freeze whose trigger unit is `tick` but whose duration is `ms` in `carla-simulation` is admitted.
- `sim_duration_ns` reads only the intent's `timeDomainId` and the duration unit. It never checks the
  trigger unit, and stage 3 runs only for freezes.
- PAIR-1 requires the onset and duration of *every* fault in simulator time: design §4, "a time trigger and
  a duration in a declared simulator time domain".
- Repair before the gate is lifted: require the trigger unit and the duration unit to be in
  `TIME_UNITS_NS` with domain `carla-simulation`, for every fault and not only freezes. Add the probes
  above as tests.

**MEDIUM-2: the inequality counts fractional steps.**
- Where: admission.py 50–53.
- Under the AD-30 delivery rule and the step-hold handshake, a freeze holds whole simulator steps. A `D`
  that is not a multiple of `step_s` therefore costs `ceil(D/step)` steps.
- Probe: `D` = 1201 ms at a 50 ms step gives 2.802 s by the code, against 2.9 s with whole steps, which
  underestimates the host time by up to one `max_step_host_s`.
- That is the P-11 thaw-bound guard, so it should be conservative. Either use `ceil(D / step_s)`, or refuse
  a `D` that is not a whole number of steps.

**MEDIUM-3: the hub's second line admits a lone `vc-functional` freeze.**
- Where: admission.py 176–178; test_admission.py 146.
- `recheck` takes every `admittedSet` member as individually armable. Design §3 says the admitted targets
  are "enforced twice", and the CC-1 constraint (a U5 freeze only together with U6) is part of the
  admitted freeze targets, which WP-12 finding 3 HIGH-1 fixed at admission.
- A lone U5 descriptor reaches the hub only if admission was bypassed, which is exactly the case the
  second line exists for, and there it passes.
- Either give `recheck` the descriptors armed for one onset, as a batch, and apply the same concurrent-set
  rule. Or record in residual 4 and design §3 that the hub re-checks targets and kinds only, and that CC-1
  is enforced once.

**LOW-1: `FreezeBound` is required but never applied.**
- Where: admission.py 118–119 and 138.
- Design §5 calls `check_fault_admission(docs, faults, freeze_bound)`. Here it is called without the
  bound. That is deliberate, because its tick rule would refuse simulation-time durations, but it is not
  recorded.
- Probe: `FreezeBound(0.001, 1.0)` (`max_ticks` 0) does not refuse a 500 ms freeze. Under (A) the
  simulation-time inequality is the duration rule.
- Record the deviation, or drop the tick `FreezeBound` requirement from this path, so that a validated but
  unused input does not suggest a check.

**LOW-2: the test seams are open in the production signature.** `platform`, `prepare_fn` and `admit_fn`
are ordinary keyword arguments. A caller passing any object with `SIMULATION_TIME_TRIGGERS = True` passes
the interim gate (probe). State in residual 6 that the increment #5 run command must not pass them, or make
them test-only, for example a private `_testing` hook.

**LOW-3 (optional):** `recheck` does not repeat the simulation-time duration bound for a freeze
descriptor, although `ArmDescriptor` carries `durationNs`.

### Residuals 1 to 6
- Residuals 1 to 6 are accurate.
- Missing:
  - MEDIUM-1 (simulation-time keying of all faults and triggers) and MEDIUM-2 (whole steps), both as
    conditions for lifting the interim gate;
  - MEDIUM-3 (the CC-1 rule at the hub);
  - LOW-1 (`FreezeBound` not applied).

### Recommendation
- Accept as the interim admission path. Record MEDIUM-1 and MEDIUM-2 as gate-lift conditions for
  increments #3 and #5, and MEDIUM-3 for increment #4.
- Optionally repair MEDIUM-1 and MEDIUM-2 now (small, offline) with the probes as tests.
- Record LOW-1 to LOW-3.

## Finding 4: disposition of finding 3 (2026-10-24 15:20:02; recorded before any change)

This disposition is the coordinator's, under the author's delegation: repair now. It is flagged for the author's
review.

| Item | Disposition | Planned change |
| --- | --- | --- |
| MEDIUM-1 | Repair | Require simulation-time keying of the **trigger and the duration of every fault**, message faults included: domain `carla-simulation` and both units in `ns/us/ms/s`. Tests: a tick-keyed F09 `stale`, and a freeze with a tick trigger and a millisecond duration, both refuse with (A) injected |
| MEDIUM-2 | Repair | The inequality counts whole steps: `ceil(D / step_s) × max_step_host_s + 2 × handshake_s ≤ thaw_bound_s`. Test with the 1201 ms probe |
| MEDIUM-3 | Repair | `HubArmingRecheck` takes the whole armed batch, and applies the CC-1 rule: a member of an admitted set that is not individually admitted is armable only when every member is in the batch with the same onset and duration. A lone `vc-functional` is refused |
| LOW-1 | Repair | Apply the FreezeBound tick cap in admission: a freeze's duration in Maestro ticks, `ceil(D/step)` steps, must not exceed `FreezeBound.max_ticks`. A bound allowing 0 ticks refuses a 500 ms freeze (test) |
| LOW-2 | Record | The `platform`, `prepare_fn` and `admit_fn` parameters are test seams. The increment #5 run command must not pass them: the real harness uses the imported `xverse.faults` module and the real prepare and admit. Documented in the docstring |
| LOW-3 | Repair | The hub re-check repeats the simulation-time duration bound for each freeze descriptor, when the bound is given |

## Finding 5: result of the finding 4 repairs (2026-10-24 15:22:21; repair commit `c61a2bc`)

**Commands.** `tests/test_admission.py` with the rc.1 profiles: 34 passed (27 before). Whole suite: 205 passed.
`check_topology.py`: exit 0. Host load 6.2. Offline only; no CARLA, no live run; the loop10 paths and the
pinned live environment were not touched.

**MEDIUM-1, repaired.**
- `sim_keying(fault)` requires a `time` trigger, the domain `carla-simulation`, and both the trigger unit
  and the duration unit in `ns/us/ms/s`.
- Stage `sim-duration` now applies it to **every** fault, message faults included, before any freeze bound.
- Tests, with (A) injected: a tick-keyed F09 `stale` is refused at `sim-duration`; a freeze with a tick
  trigger and a millisecond duration is refused; a simulation-time-keyed F09 `stale` passes to admission.
  On rc.1 that `stale` is still refused by the interim gate.
- The interim-position cases now use simulation-time-keyed message faults, so they reach and test the
  gate.

**MEDIUM-2, repaired.**
- `SimTimeFreezeBound.steps(D) = ceil(D / step_s)`, and `host_seconds = steps × max_step_host_s + 2 ×
  handshake_s`.
- Test (bounds: step 0.05 s, `max_step_host` 0.1 s, handshake 0.2 s, thaw 2.85 s): 1201 ms is 25 steps,
  2.9 s, and is refused ("25 steps"). The old fractional count would have given 2.802 s and admitted it.
  1200 ms is 24 steps, 2.8 s, and is admitted.

**MEDIUM-3, repaired.**
- `HubArmingRecheck.recheck(batch)` takes the whole armed batch.
- A member of an admitted set that is not individually admitted is armable only when every member is in
  the batch with the same onset and duration.
- Tests:
  - a lone `vc-functional-unit` is refused (CC-1);
  - the pair is armable;
  - the pair with a different onset, or a different duration, is refused;
  - `vc-assurance-unit` alone is armable, because it is individually admitted.

**LOW-1, repaired.**
- The FreezeBound tick cap is applied in admission: `ceil(D/step) ≤ FreezeBound.max_ticks`. Under the
  lockstep hub each simulator step is counted as at least one dispatcher cycle, a conservative reading
  recorded in the module docstring.
- Test: `FreezeBound(0.001, 1.0)` (0 ticks) refuses a 500 ms CC-1 pair ("tick cap 0").

**LOW-2, recorded.** The module docstring states that `platform`, `prepare_fn` and `admit_fn` are test seams.
The increment #5 run command must not pass them: the real harness uses the imported `xverse.faults` and the
real prepare and admit.

**LOW-3, repaired.**
- With a `SimTimeFreezeBound` (and optionally a `FreezeBound`), the hub re-check repeats the duration
  rules for each freeze descriptor. It refuses when the bound is unknown.
- Tests: no bound means not checked; a known bound refuses 1500 ms; an unknown bound refuses.

**Residuals (replaces finding 2's list).**
1. **D-4c values:** `max_step_host_s` and `handshake_s` are unknown, so every freeze is refused at
   `sim-duration` even after (A). `step_s` and the thaw bound are caller inputs.
2. **Capability probe:** `xverse.faults.SIMULATION_TIME_TRIGGERS` is provisional until increment #3's ADR.
3. **Gate-lift conditions (increments #3 and #5).** Simulation-time faults must be admissible in the
   one-domain Maestro form, with the keying and whole-step rules of this path applied unchanged. Real
   prepare and `admit_schedule` with faults are still untested: spies stand in under the injected
   capability.
4. **Hub arming:** the control channel and `arm()` belong to increments #3 and #4. The batch re-check
   (targets, kinds, CC-1, durations) is in place.
5. **The tick-cap reading** (one step is at least one dispatcher cycle) is to be confirmed or replaced by
   D-4c.
6. **The run command** (increment #5) calls `admit_run` without the test seams.

The next step is acceptance and a merge. Neither has happened.

## Finding 6: independent re-review of findings 4 and 5 (2026-10-24 15:27:30)

**Reviewer and method.**
- The finding 3 reviewer, read-only. Read `581b91e`, `c61a2bc` and `1972efe` against `d5e4acf`.
- Commands:
  - `tests/test_admission.py`: 34 passed;
  - the whole suite with the rc.1 profiles: 205 passed;
  - `check_topology.py`: exit 0.
- In-memory probes, with spies and an injected (A) stand-in only:
  - the step count at 1200, 1201 and 50k ms, and +1 ns;
  - a sweep of the tick cap against the inequality;
  - a tick-keyed F09 fault.
- Nothing in the worktree changed except this entry. No CARLA, no live run.

### Verdict: **PASS WITH NOTES. Nothing blocks the merge.**

### Items of finding 3
- **MEDIUM-1: closed.**
  - `sim_keying` requires `timeDomainId == carla-simulation`, a `time` trigger, and both the trigger and the
    duration in ns, us, ms or s. Stage 3 applies it to **every** fault before the freeze rules.
  - Probe: the finding 3 tick-keyed F09 `stale` fault now stops at `sim-duration`. The mixed tick-trigger,
    ms-duration freeze is refused (test).
  - A simulation-keyed message fault passes to the gate, and on rc.1 it gets `INTERIM`.
- **MEDIUM-2: closed.**
  - `steps = ceil(D/step − 1e-12)`. The 1201 ms probe gives 25 steps and 2.9 s; 1200 ms gives 24, and the
    test bound of 2.85 s separates the two.
  - The epsilon is safe: `D` has 1 ns resolution, so a genuine fraction is at least 2e-8 of a step. Every
    multiple of 50 ms from 50 ms to 3 s counts exactly, and +1 ns adds a step.
- **MEDIUM-3: closed.**
  - `recheck(batch)` applies the CC-1 rule over the batch: a member of an admitted set is armable only if every
    member is armed with the same onset and duration.
  - A lone `vc-functional` is refused; the pair is accepted; a later onset or a longer partner is refused; a
    lone `vc-assurance` is accepted.
  - This matches design §3: "at `start` it arms the hub boundary with each entry", so the batch is the run's
    whole armed set.
- **LOW-1: closed in behaviour; the reading needs relabelling (see LOW-A).** The tick cap is applied, and a
  `FreezeBound` allowing 0 ticks now refuses the 500 ms pair.
- **LOW-2: closed.** The module docstring and residual 6 state that the test seams are for tests only and
  that the increment #5 run command must not pass them.
- **LOW-3: closed.** The hub re-check repeats the duration bound when given one: an over-long freeze is
  refused, an unknown bound refuses, and no bound means no check, as documented.
- **Residuals 1–6** are accurate and now carry the gate-lift conditions (3) and the tick-cap reading (5).

### New notes (LOW, not blocking)
- **LOW-A: the tick cap is not "conservative". It is implied by the inequality under its own assumption.**
  - Finding 5 counts "each simulator step as at least one dispatcher cycle". That makes `steps` a *lower*
    bound on the dispatcher ticks during the hold, so `steps ≤ max_ticks` cannot guarantee
    `ticks ≤ max_ticks`.
  - Under the same assumption (`max_step_host_s ≥ max_cycle_s`), the §4 inequality already implies the cap:
    `steps · max_cycle ≤ steps · max_step_host ≤ thaw`. A sweep over 1–79 steps and cycles of 0.05, 0.08 and
    0.1 s with `max_step_host` 0.1 s found **0** cases where the inequality admits and the cap refuses.
  - The §4 inequality is the real guard, so this is not a safety gap. But residual 5 and the docstring should
    say that the cap is a redundant consistency check under the lockstep assumption, not a conservative one.
    D-4c should confirm `max_step_host_s ≥ max_cycle_s`. If it is not confirmed, the cap needs ticks
    (`ceil(host_seconds / max_cycle)`), not steps.
- **LOW-B (optional): integer step arithmetic.** `ceil(duration_ns / step_ns)`, with `step_ns` an integer,
  would avoid the epsilon altogether.

### Recommendation
Ready for acceptance and merge as the interim admission path. Relabel the tick-cap reading (LOW-A) in
residual 5. LOW-B is optional.

## 7. Acceptance (written at 15:28:30 2026-10-24)

- **Accepted** under the author's delegation of 2026-10-24 (thesis `specs/002-assured-aeb/decisions.md` §G, §J,
  §K and the rows cited in this log). It is flagged for the author's review.
- **Basis:** findings 3 and 6 (both PASS WITH NOTES), repairs in findings 4-5; suite 205 passed, checker exit 0.
- This is the interim admission path: every fault schedule refuses until option (A) is merged. Residual 5 is relabelled: the tick cap is a redundant consistency check, implied by the section 4 inequality when `max_step_host_s >= max_cycle_s`, not a conservative bound. If D-4c does not confirm that, the cap counts ticks as `ceil(host_seconds / max_cycle)`. LOW-B (integer step arithmetic) is optional.
- **Merged** into blueprints main and pushed (see the merge commit).
