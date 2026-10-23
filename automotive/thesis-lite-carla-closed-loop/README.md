# Thesis Lite: CARLA closed-loop integration (Phase 7 live integration)

**Maturity: engineering integration candidate.** This is not AEB validation, not a scientific thesis result
and not M1 evidence. Maestro is driven through its owned trusted-host harness path, the same
`_OriginalRuntimeRun` path the platform uses for its own real-child runtime tests. The external
readiness-reviewed `RuntimeService` path stays closed (thesis DLG-7).

## Command

```bash
automotive/thesis-lite-carla-closed-loop/run-live.sh nominal            # Lite run under Maestro
automotive/thesis-lite-carla-closed-loop/run-live.sh freeze-vcu         # Phase 5 freeze of the legacy VCU unit
automotive/thesis-lite-carla-closed-loop/run-live.sh cancel-paused      # cancel while the simulation clock is paused
automotive/thesis-lite-carla-closed-loop/run-live.sh no-carla           # missing simulator (start without a server)
automotive/thesis-lite-carla-closed-loop/run-baseline.sh                # legacy reference invocation (not Maestro)
python3 automotive/thesis-lite-carla-closed-loop/report.py --out DIR RUN_DIR...
```

Preconditions:
- `XVERSE_COMPAT_SRC` names the `xverse-compat` checkout to use. There is no default path. Both commands
  refuse to run without it: exit 4, before any run directory exists. They record its absolute path as
  `compat-src` in `identities.txt` (thesis S1 FR-014);
- a CARLA 0.9.15 server on `127.0.0.1:2000`, started with the author's recipe `just server-nvidia Epic 2000`
  from `~/autoverse`;
- a zenoh router on `tcp/127.0.0.1:7447`;
- no other tick owner or actuator writer (the run command checks for one).

The Lite run command also refuses a world that already has vehicles, because the declared scenario
assumes an empty world. After a BLOCKED preflight the restore guard is skipped. The guard retries the
settings commit up to 3 times (`applyAttempts`).

The baseline command:
- blocks when the world settings cannot be read;
- normalizes an ownerless synchronous world to asynchronous as a declared setup step, with a bounded retry,
  and blocks when that normalization does not take effect; it then lists the world again;
- refuses a world that already has any vehicle, as the Lite run does (S1 T-5 a);
- after a normalisation, lists the world again into `world-after-normalisation.json`, so `world-before.json`
  keeps the state found before the run (S1 T-2);
- traps EXIT, INT and TERM. Its normal stop sends INT, then TERM, then KILL. The trap cleanup after an
  interrupt sends INT, then KILL after 3 s. The log `tee` and the cleanup ignore further INT and TERM, so
  a Ctrl-C of the process group cannot cut the cleanup short (S1c finding 7);
- destroys a legacy ego that appeared during the run, and verifies the cleanup by listing the world again;
- writes `baseline-status.txt`, writes its exit code to `baseline-exit.txt` on every exit after the run
  directory exists (S1 T-5 c), and exits 3 when any of
  the following holds:
  - the stimulus did not complete;
  - the virtual vehicle or the VCU exited with anything other than 0 or 130, or 143 after the declared TERM step
    (S1 T-5 b);
  - the observer exited non-zero;
  - vehicles remain;
  - processes remain.

The review 4 LOW items T-2, T-3 and T-5 are repaired in successor increment S1c. The record is in the compat
review log `docs/engineering/thesis-lite-stabilization/review-s1c.md`. Both commands record the legacy
identities with dirty flags and diff hashes (S1 FR-016). A hung server is reported in one line and fails
closed (T-5 d).

Run directories are written under
`/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/runs/xverse-lite-live-20261022/`.

## What runs

The XDL documents are derived from the platform's validated Maestro fixture set by `build_documents`. The
harness then validates and compiles the experiment plan, calls `prepare_lifecycle`, and builds permits and
approvals; the legacy VCU's permit drops the `legacy-execution` exclusion under the author's authorization.
It then admits the schedule, coverage and collection, seals the bootstrap, and calls
`_OriginalRuntimeRun.start`.

Maestro starts four units in order:

| Unit | Executable | Role |
| --- | --- | --- |
| `lite-driver` | CPython 3.13.13 | `xverse_compat.live.driver`: the platform side of `carla-items/2`, Phase 6 flow receivers, Argus flow evidence, and the gateway to the VCU |
| `carla-adapter` | `/usr/bin/python3.10` plus the pinned carla 0.9.15 site | `xverse_compat_carla.main`: the only tick owner and actuator writer; it owns the `xverse-lite-*` ego vehicle and sensors |
| `legacy-vcu` | `/usr/bin/python3.10` | the unchanged `autoverse/vecu/vcu_zenoh@125566e` `main.py` |
| `driver-stimulus` | CPython 3.13.13 | `xverse_compat.live.stimulus`: the declared pedal profile that replaces the human driver |

Before each run, the run command:
- refuses dirty candidate trees, and records the revisions with diff hashes;
- refuses competing simulation processes and any unexpected client connected to CARLA;
- records the world settings, including whether the frame advances, in `world-before.json`.

After each run, it runs the following, also from a trap on EXIT, INT and TERM:
- **Residue check.**
- **Restore guard.** The guard:
  - holds the owned ego by ID with throttle 0, brake 1 and the hand brake, while the world is still paused,
    using the adapter's owned-actor registry;
  - restores the recorded pre-run settings (DLG-11). When the recorded state was synchronous and not advancing,
    it restores asynchronous mode and records the reason (DLG-11a);
  - with an asynchronous restore target, holds every owned ego with brake until it is at standstill
    (< 0.05 m/s), or for 5 s, recorded as a failure. It records the hold, un-pause, standstill and destroy
    times (S1 FR-022);
  - destroys the `xverse-lite-*` actors by ID;
  - verifies that none remain.
- **Socket cleanup**, and a copy of Maestro's tmpfs journal and Argus root into the run directory.

A passive observer, which is evaluation-only, measures motion in every run, including through the guard.

Inputs to the baseline and the Lite run:
- **Stimulus.** Both receive the same declared stimulus, keyed on host time from the first clock sample
  (`--time-base wall`, DLG-12).
- **Throttle.** The legacy vehicle divides the VCU throttle by 1.2, so it applies 0.5 for a 0.6 command. The
  Lite adapter applies it undamped.
- **Report.** `report.py` shows the actuated and commanded throttle of each run.

A Lite run succeeds only if Maestro collects every owned completion marker, and every marker records success
(DLG-13).

Contracts: `xverse-compat` `docs/engineering/thesis-lite-phase7-live/carla-items-2.md` and
`bridge-identity-reconciliation.md`.

## Time domains

- `carla-simulation`: item origins and the flow receiver clock.
- `host-monotonic`: pacing, Maestro deadlines and cancellation. These work while simulation time is paused;
  this is verified by `cancel-paused`.
- `experiment-time`: Maestro's schedule ticks. They are not wall-paced: about 0.07–0.7 s per tick were
  measured in Phase 7, depending on host load. After the S1a persistence repair a cycle runs at the 0.05 s poll
  floor (steady mean about 0.057 s), so the tick values are derived from that floor (S1c findings 16, 18 and 19):
  - The schedule runs 400 ticks, which is at least 20 s after tick 0.
  - Observe is at tick 60, before the cancel-paused cancel.
  - The freeze is at ticks 40–50. The platform refuses a thaw that comes more than 3.48 s after the frozen
    unit's last health success (cadence 5 s minus `health_scan_seconds`). The freeze length keeps the worst
    case inside that bound up to a mean cycle of about 0.17 s; it is a bound, not a guarantee under any load.
  - `maestro-run.json` records `tickTiming` and the load average at the start and the end.
  - `argus-verify.txt` holds `xverse-argus verify` for the Maestro and flow roots.

  Every case asserts its expected path: nominal and freeze-vcu must succeed; no-carla must end with
  `ML-RUN-CHILD-EXIT`. cancel-paused must complete observe, be cancelled during the run, and end with
  `ML-SCHEDULE-CANCELLED`. It must also close as P3 requires: no persistence failure, cleanup complete,
  every native unit retired and reaped, and every closure writer `failed` or `closed` (S1c finding 20).

## Limits

The following are not claimed or not covered:
- CARLA, the SOME/IP bridge, S-CORE and Android are outside Maestro. CARLA is an external dependency;
  `CarlaUE4-Linux-Shipping` is 111 MB, above the 32 MiB sealing limit.
- No steering; the reverse gear is not carried.
- No brake status or wheel speed.
- An echo is not braking evidence.
- No parity with the legacy loop: the physics step differs (fixed 0.05 s versus about 8 ms asynchronous) and
  the legacy vehicle uses a random spawn point.
- The Maestro persistence path has a scaling limit (live finding 03), which constrains the run length.
