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
