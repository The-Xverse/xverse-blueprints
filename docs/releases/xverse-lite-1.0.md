# X-Verse Lite 1.0 release record: `xverse-blueprints`

**Status: release candidate rc.1, recorded 2026-10-24.** The step from rc.1 to the final release depends on the
S1d soak, which this repository's tooling runs on the tagged revisions and which is pending.

| Item | Value |
| --- | --- |
| Repository | `/home/jefferson/xverse-blueprints` |
| Code revision | main `5fa8bcba3545e5675e512baf5baa5738bac42599` (S1d2 merge, equal to `origin/main` on 2026-10-24) |
| Release commit | the commit on `release/xverse-lite-1.0-rc.1` that adds this record; its parent is `5fa8bcb`, and it changes documentation only (this record and the blueprint `README.md`) |
| Tag | `xverse-lite-v1.0.0-rc.1`, naming the release commit (created and pushed separately, not by this commit) |
| Blueprint | `automotive/thesis-lite-carla-closed-loop/` |
| Shared sections | program history, platform evidence, CAPA, decision table and open items: `xverse-platform` `docs/releases/xverse-lite-1.0.md` (the platform record) |

## 1. What X-Verse Lite 1.0 is

X-Verse Lite 1.0 is the first engineering-integration baseline of X-Verse Lite across `xverse-platform`,
`xverse-compat` and `xverse-blueprints`. This repository holds the Lite CARLA closed-loop blueprint: a Maestro
Lite run, through the platform's owned trusted-host path `_OriginalRuntimeRun`, of four units against a CARLA
0.9.15 server, with the unchanged legacy VCU, deterministic faults, flow evidence and Argus records, plus a legacy
baseline invocation and the predeclared soak tooling. The blueprint README states its maturity as an "engineering
integration candidate": not AEB validation, not M1 evidence and not a scientific result. It is also not X-Verse
fitness for purpose. The comparison with the legacy baseline is smoke coverage, not parity.

## 2. Components and entry points

| Component | Location | Entry point |
| --- | --- | --- |
| Live run command | `run-live.sh`, `lib-live.sh` | `run-live.sh <case> [run-dir]`, case `nominal`, `freeze-vcu`, `cancel-paused`, `no-carla` or `long-run`. Requires `XVERSE_COMPAT_SRC` (exit 4 without it, FR-014) |
| Maestro harness | `test_live_closed_loop.py`, `units.py`, `conftest.py` | run by `run-live.sh` through pytest with `XVERSE_LIVE_CASE`. Builds the XDL documents, compiles the plan, calls `prepare_lifecycle`, admits schedule, coverage and collection, seals the bootstrap and calls `_OriginalRuntimeRun.start` |
| Units | `units.py` | `lite-driver` (CPython 3.13.13, `xverse_compat.live.driver`); `carla-adapter` (`/usr/bin/python3.10` with the pinned carla 0.9.15 site, `xverse_compat_carla.main`; the only tick owner and actuator writer); `legacy-vcu` (the unchanged `autoverse/vecu/vcu_zenoh@125566e` `main.py`); `driver-stimulus` (`xverse_compat.live.stimulus`) |
| Legacy baseline | `run-baseline.sh` | reference invocation, not Maestro |
| Report | `report.py` | `python3 report.py --out DIR RUN_DIR...` |
| Soak runner | `soak/run_soak.py` | `python3 run_soak.py --compat <clean detached compat worktree> --blueprints <clean detached blueprints worktree> --out <soak dir> [--dry-run]`; also `--dispersion` |
| Soak audit | `soak/audit.py` | P1 and P3–P8 per run, with DR-2, DR-6 and DR-14 |
| Soak health check | `soak/health_check.py` | read-only server check before the preflight and after cleanup (DR-21) |
| Soak tests | `soak/test_run_soak_logic.py`, `soak/test_health_check.py` | offline, with fakes |

Harness parameters on the release revision (`test_live_closed_loop.py`): horizon 400 ticks; long-run 600 ticks
with a 25 s episode; observe at tick 24; freeze at tick 25 for 10 ticks; owned readiness window 1.7 s (attempts at
0, 0.725 and 1.45 s; DR-17, DR-19); TERM grace 0.6 s (S1c-2 package). Unit run directories are staged on
`/dev/shm/xverse-lite-run-<run>` and copied to the evidence directory at cleanup (H2).

## 3. History of this repository

| Step | Merge | Date | Acceptance |
| --- | --- | --- | --- |
| Phase 7 CARLA closed-loop blueprint | `e7a6ebc` (candidate `8805ec5`, evidence code `320a284`) | 2026-10-23 07:41 | author, about 07:39 (AD-01) |
| S1c-1 (FR-014 to FR-017, FR-022, T-2, T-3, T-5) | `126a80b` | 2026-10-23 16:20 | author, about 16:15 |
| S1c-2a blueprint horizons (S1-T14b) | `6ac7703` | 2026-10-23 18:42 | author, about 18:40 |
| S1c-2 live harness after S1b, soak tooling | `aceb5ae` | 2026-10-24 07:14 | under the author's acceptance of 2026-10-24 |
| S1d soak health-check repair (DR-21) | `9b21d5b` | 2026-10-24 08:09 | repair successor under that acceptance |
| S1d2 operator-signal stop (finding 60) | `5fa8bcb` | 2026-10-24 08:48 | repair successor under that acceptance |

Review records for this repository are kept in the compat log
`xverse-compat/docs/engineering/thesis-lite-stabilization/review-s1c.md` (findings 1–62) and, for Phase 7, in
`xverse-compat/docs/engineering/thesis-lite-phase7-live/review-phase7-live.md`.

## 4. Cross-repository compatibility set

| Element | Value |
| --- | --- |
| Platform main | `a9db0ac39a858c0b2d341149042a8a97b7dcf393` |
| Compat main | `30446f6c7f234ec600398ba5db6c57846210c772` |
| Blueprints main | `5fa8bcba3545e5675e512baf5baa5738bac42599` |
| Platform-API lock (compat) | `platformRevision` `a9db0ac39…`, surface `ce779e57d888b61b2a40fa7b4a05999ad900a33e48fc71e340a082b902fb43cd` |
| Pinned live environment | `/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache/xverse-lite-live-20261022/` (`driver-venv`, `platform-src`), rebuilt from `a9db0ac39`; wheel `cea5ced404c277157df9496086fd4a0a8f011c58e01c8e7d659fc2fb5b53cddf` (compat finding 55) |
| CARLA client environment | `/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache/xverse-compat-carla-0.9.15-cp310` |
| External services | CARLA 0.9.15 on `127.0.0.1:2000` (author's recipe `just server-nvidia Epic 2000` in `~/autoverse`); zenoh router on `tcp/127.0.0.1:7447` |

## 5. Verification and evidence

All live sets are on loop10 under
`/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/runs/lite-stabilization-s1/`, each with
`SHA256SUMS` (line counts below; dev3 to dev6 were sealed after their runs).

| Set | Files | Role (compat `review-s1c.md`) |
| --- | --- | --- |
| `s1c2-part2-dev3-20261024` | 520 | finding 47: repaired freeze-vcu and cancel-paused PASS on platform `a16fd1b78`; cold-start readiness failure observed (DR-18) |
| `s1c2-part2-dev4-20261024` | 393 | finding 48: cold nominal PASS (adapter 1.74 s); freeze margin defect (−0.185 s) leading to the tick-25 placement |
| `s1c2-part2-dev5-20261024` | 471 | finding 49: freeze placement confirmed; a unit stalled in an fsync on loop10, leading to H2 |
| `s1c2-part2-dev6-20261024` | 511 | findings 51 and 54 (LOW-5): the H2 tmpfs-staging set on blueprints `7677078`, H1 = 1.95 s; 8 runs, the copy shown and no stage left in all; the first run after the server start failed readiness cleanly (adapter not ready by 1.70 s), the other seven passed, including cancel-paused three times |
| `s1c2-part2-dev7-20261024` | 528 | finding 52: H1 and H2 repairs hold; two `ML-SCHEDULE-EVIDENCE-INCOMPLETE` runs leading to platform S1a-6 (DR-20) |
| `s1c2-part2-dev8-20261024` | 666 | finding 56, final set on blueprints `1650473` and platform `a9db0ac39`: 10 of 10 as designed; readiness slack 0.333–0.531 s; freeze start margins 1.024 and 0.869 s; cancel-paused PASS ×2; no `unverifiable` coverage row except no-carla's expected `ready` row |
| `vs09-20261024` | 144 | VS-09 MET (S1-T06a) on platform `a9db0ac39`, compat `e05d467`, blueprints `aceb5ae`: warm-up nominal PASS (adapter 1.288 s), cancel-paused PASS with `ML-SCHEDULE-CANCELLED`, 15 units frozen, cleanup complete, audit P3 PASS |
| `vs09-20261023` | 1627 | S1c-2a verification on `8aa57ca` (freeze-vcu, nominal, cancel-paused, no-carla) |
| `s1d-soak-20261024-attempt1` | 158 | finding 57: stopped by the soak's own health check after three no-carla PASS runs (DR-21) |
| `s1d-soak-20261024-attempt2` | 222 | finding 60: stopped by the operator at the author's request; not a criterion failure |

Phase 7 evidence is under `.x-verse-build/runs/xverse-lite-live-20261022/report-final` (74 runs indexed) and
`verify-main-20261023/` (post-merge verification).

Offline: soak tests 31 passed at S1c-2 (logic tests, finding 54), 37 at the review of the S1d repair (finding 58)
and 43 after the S1d2 repair (finding 62). The 43 are `soak/test_health_check.py` plus `soak/test_run_soak_logic.py`,
run from `automotive/thesis-lite-carla-closed-loop/` with `XVERSE_PLATFORM_SRC` and `XVERSE_COMPAT_SRC` set:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /dev/shm/compat-p6-venv/bin/python -m pytest -q -p no:cacheprovider soak/test_health_check.py soak/test_run_soak_logic.py
```

The same command on `5fa8bcb` gave 43 passed on 2026-10-24. The blueprint scripts have no offline test of the live
path; the live run is the test.

**Soak (S1d, S1-T16): PENDING.** Protocol: `specs/029-lite-stabilization/plan.md`, "Soak protocol" (thesis
repository; SHA-256 `386c50d0199a40080d9bede3ad0e940d54a884f70a8f63a07215da73ba406852`). 140 runs: nominal,
freeze-vcu, cancel-paused and long-run 30 each (rate bound), no-carla 10 and baseline 10 (smoke); one warm-up per
server start, excluded from the statistics; rounds start at a 1-minute load ≤ 5; runs above load 10 are
observations; the first criterion failure stops the soak; the bound is 1 − 0.05^(1/n) (9.5% per case at n = 30,
2.5% pooled at n = 120). Per finding 60 the soak restarts from zero at 00:00 on 2026-10-25 on the tagged rc.1 revisions, detached, with
`kill -TERM <runner PID>` as the only stop (finding 62).

## 6. Engineering decisions

The full table (S-D1 to S-D9, DR-1 to DR-21) is in the platform record, section 6; source
`specs/029-lite-stabilization/review/author-decisions-20261023.md`, SHA-256
`38a6fc23888727a1f4904601d824d3c2af49604fd1864c10e0676179d35169e4`. Decisions realized in this repository:
S-D4 (soak protocol), S-D6 (live execution), DR-6 and DR-14 (audit conditions), DR-11 and DR-12 (no-carla gaps,
INVALID versus FAIL), DR-17 and DR-19 (H1 = 1.7 s), DR-18 (2) and DR-19 (2) (warm-up), DR-19 (3) (H2 tmpfs
staging) and DR-21 (health check). DR-19 to DR-21 are delegated and flagged for the author.

## 7. Declared limits and residuals

- Single host, one CARLA server, one tick and actuator owner; timing claims only up to sampled load 10.
- No steering; the reverse gear is not carried. No brake status or wheel speed; an echo is not braking evidence.
- No parity with the legacy loop: fixed 0.05 s physics step versus about 8 ms asynchronous, random legacy spawn
  point, legacy throttle damping ÷1.2 (DLG-12).
- CARLA, the SOME/IP bridge, S-CORE and Android are outside Maestro; `CarlaUE4-Linux-Shipping` exceeds the 32 MiB
  sealing limit.
- The legacy VCU stays liveness-only; owned units use the nonce-marker probe.
- Cold-start readiness: the soak results describe a warmed-up server (DR-18, DR-19).
- H2: evidence durability is that of the copy after the run, not of fsync to loop10 during it. The loop10 image was
  97% full in finding 49.
- Soak health check: a server that answers but cannot tick passes the before-check and then fails the warm-up as a
  criterion stop rather than INVALID (DR-21 erratum; finding 58 LOW-2). A pending operator signal leaves no trace
  when another outcome wins (finding 62, LOW-3). An operator stop may take up to about 15 minutes.
- The restore guard does not run after a BLOCKED preflight or in baseline runs (finding 59).
- The `P8.pathHolds` excuse applies to a warm-up only on the adapter-close path when no control was sent.
- The blueprint `README.md` is updated in the release commit to the S1c-2 harness: the `long-run` case, the
  observe at tick 24 and the freeze at tick 25, the owned readiness window of 1.7 s, the current run-length
  bounds, and the soak tooling.

## 8. How to verify a checkout

1. `git -C <checkout> rev-parse HEAD` equals the release revision and `git status --porcelain` is empty; the run
   command refuses dirty trees unless `XVERSE_LIVE_ALLOW_DIRTY=1`.
2. Offline soak tests, from `automotive/thesis-lite-carla-closed-loop/`, with `XVERSE_PLATFORM_SRC` and
   `XVERSE_COMPAT_SRC` set: the command in section 5. Expected: 43 passed.
3. Soak dry run, without CARLA: `python3 soak/run_soak.py --compat <clean detached compat worktree> --blueprints
   <clean detached blueprints worktree> --out <dir> --dry-run`. It refuses (exit 4) unless both checkouts are clean
   and detached, then prints the pinned identities and the schedule and exits 0. It creates `<dir>`. The pinned
   identities also hash the pinned environment under loop10 (`platform-src`, wheels, driver venv) when present.
4. Live cases (loop10 and a CARLA 0.9.15 server required, except no-carla; live execution needs the author's
   authorization, S-D6 covers only VS-09 and the soak):

   ```bash
   export XVERSE_COMPAT_SRC=<clean compat checkout>
   automotive/thesis-lite-carla-closed-loop/run-live.sh nominal
   automotive/thesis-lite-carla-closed-loop/run-live.sh freeze-vcu
   automotive/thesis-lite-carla-closed-loop/run-live.sh cancel-paused
   automotive/thesis-lite-carla-closed-loop/run-live.sh long-run
   automotive/thesis-lite-carla-closed-loop/run-live.sh no-carla
   automotive/thesis-lite-carla-closed-loop/run-baseline.sh
   ```

   The default run root is `$L10/.x-verse-build/runs/xverse-lite-live-20261022/`; the S1 sets pass an explicit
   run directory under `runs/lite-stabilization-s1/`. Each run writes `identities.txt`, `maestro-run.json`,
   `argus-verify.txt`, `restore-guard.json` and the residue lists; the soak audit evaluates them.

## 9. Open items

- **S1d soak (S1-T16):** pending; restart from zero planned for 2026-10-25 00:00. The rc.1 to final step depends on
  its report against P1 and P3–P8, and S-D9 closes only if P6 passes.
- **Ledgers (S1-T17)**, **Phase 8** (Assured AEB, owned by this repository; planning rev 3a; AD-01, AD-21, AD-23,
  AD-29, AD-30, AD-33 and AD-34 decided) and **Phase 9** (campaign runner, owned by this repository; planned):
  platform record, section 9.

## Sources

Thesis repository `/home/jefferson/distributed_safety_critical_thesis`. These files are untracked or locally
modified there, so the SHA-256 below, computed at 2026-10-24 09:15 WEST, is their identity for this record.

| File | SHA-256 |
| --- | --- |
| `specs/029-lite-stabilization/plan.md` | `386c50d0199a40080d9bede3ad0e940d54a884f70a8f63a07215da73ba406852` |
| `specs/029-lite-stabilization/tasks.md` | `03e439bfc9aaef9898bbafd914af156a9448329c6d840e8f462318f329557919` |
| `specs/029-lite-stabilization/review/acceptance-package-s1c1-20261023.md` | `7f1e07fa10096c28f55e15c92d470ba711ea9b45010b68f31146dd3b42d0c342` |
| `specs/029-lite-stabilization/review/acceptance-package-s1c2a-20261023.md` | `5f9e6ae7f40b8ce70a410524e18819309b9597fb3ed6143b619f9af8f8116276` |
| `specs/029-lite-stabilization/review/acceptance-package-s1c2-20261024.md` | `deab3886875592e0a08d0866154bb7b22d8a01828cf4a24d7a9bade039c0412a` |
| `specs/029-lite-stabilization/review/vs09-20261024.md` | `32f3698a4ba6b325d7615096e8e39191b93412e0500e7d4fb7f16ad638e95b73` |
| `specs/029-lite-stabilization/review/vs09-s1c2a-20261023.md` | `ff3660f3f0517e9d5b99c167f8dd68670094909ce485ec9ccf96e5bb9f78dc1d` |
| `specs/001-thesis-lite-compatibility-smoke/review/acceptance-package-20261023.md` | `566f555901a00c0caaec9713c903b75135d14245b90d8d56f08cc1528df5e72c` |
| `specs/002-assured-aeb/decisions.md` | `6fca544cb06bf1bc9375af1053ed0723ca0e8498c6a7d23df6435ca9cc55d03d` |
| `specs/021-thesis-lite-program/tasks.md` | `bee0c284b1a4f3a49c79ea4b547f543ce79416fdb3b5fd31669ddbda7cbd7b94` |
| `specs/029-lite-stabilization/review/author-decisions-20261023.md` | `38a6fc23888727a1f4904601d824d3c2af49604fd1864c10e0676179d35169e4` |
| `specs/029-lite-stabilization/review/acceptance-package-s1a6-s1d-20261024.md` | `ed579593a869427ac4b3d9261f3ea1aca15561cbc6d2c791432246ab2ea94814` |
