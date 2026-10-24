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
