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
- a CARLA 0.9.15 server on `127.0.0.1:2000`, started with the author's recipe `just server-nvidia Epic 2000`
  from `~/autoverse`;
- a zenoh router on `tcp/127.0.0.1:7447`;
- no other tick owner or actuator writer (the run command checks for one).

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

After each run, the run command does the following:
- runs the restore guard (asynchronous world, `xverse-lite-*` actors destroyed and verified);
- checks for residue;
- copies Maestro's tmpfs journal and Argus root into the run directory.

A passive observer, which is evaluation-only, measures motion in every run with the same instrument.

## Time domains

- `carla-simulation`: item origins and the flow receiver clock.
- `host-monotonic`: pacing, Maestro deadlines and cancellation. These work while simulation time is paused;
  this is verified by `cancel-paused`.
- `experiment-time`: Maestro's schedule ticks. They are not wall-paced: about 0.17–0.7 s per tick,
  depending on host load.

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
