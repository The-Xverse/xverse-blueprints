# WP-12 review log: XDL topology of the assured AEB blueprint (Phase 8, P8-T01)

Candidate: branch `candidate/phase8-wp12-xdl-topology-20261024`, from main `99df3a4` (X-Verse Lite 1.0
rc.1). This is a direct engineering increment, as in S1, and the log follows the same order:
1. findings come before repairs;
2. an independent read-only review;
3. acceptance;
4. a merge.

None of the last three has happened yet.

**Inputs.**
- The thesis design record `specs/002-assured-aeb/design/wp12-xdl-topology.md`, decided under the
  author's delegation in `decisions.md` §K.
- The unit allocation `design/wp11-unit-allocation.md`, decided in §J.
- The platform at tag `xverse-lite-v1.0.0-rc.1` (`64ff9d3eb`), read-only. It is used through the
  pinned test venv `/dev/shm/compat-p6-venv`, wheel `xverse_xdl-0.4.0`, sha256 `cea5ced4…`; its
  `xverse` and `xverse_xdl` sources match the tag. The profile schemas come from a `git archive` of the
  tag.

**Scope.** Offline only:
- no CARLA, no live run and no unit process;
- no platform change: C1, which raises the 64 KiB persistence-configuration limit, is a separate
  platform increment;
- engineering evidence only; not M1, not AEB evidence, not X-Verse fitness for purpose.

## Finding 1: design and file plan (recorded before any document or code)

### Design

1. **One generator, four arms.**
   - `topology.py` is the single source. It declares the nodes, element types (Components), element
     instances, unit instances, flows, common-cause sets and arm membership.
   - It emits one XDL document set per arm: `comparator`, `mloc`, `authorization-bypass` and
     `verification-bypass`.
   - Each set has a System, a Deployment, a Scenario, one Component per element type, the unit-host
     Component and the Profiles.
   - The emitted JSON is committed under `xdl/<arm>/`, and the check fails if it differs from the
     generator output (determinism, V01).
   - The arms differ only by the membership table of design §7. The difference is reported
     machine-readably as the input to the WP-16 pairing manifest.
2. **Shape S-A** (design §3.2, decided in §K).
   - Each Maestro unit is a bound instance of `assured-aeb-unit-host`. Its Deployment binding carries
     the runtime-compatibility v0.2 payload, provider `maestro-process-v1`.
   - Each Note 21 element or role is an **unbound** instance of its own Component, with a
     `hostUnit` member in the blueprint extension.
   - The six units are U1 `carla-adapter`, U2 `vehicle-loop`, U3 `front-zone`, U4 `adas-hpc`,
     U5 `vc-functional` and U6 `vc-assurance`. The comparator omits U6. A seven-unit variant, with a
     separate `chassis-brake` unit, is generated only for the admission dry run.
3. **Blueprint extension `io.xverse.assured-aeb`.**
   - It has a Profile document and a local JSON schema `xdl/profiles/assured-aeb-v0.1.schema.json`
     (platform rule: an extension needs a supplied Profile and schema).
   - It covers Component authority (`authorityClass`, `permittedOutputs`), element `hostUnit`, `arms`
     and `computeLatency`, flow `intraUnit`, `modelledLatency` and `faultAdmission`, and the System
     `commonCause`, `freezeTargets` and `degradedPath`.
4. **TODO representation.**
   - XDL v1alpha1 has no placeholder mechanism: a `quantity` needs a number, and the Phase 6 `quality`
     members need numbers.
   - Every latency, freshness, deadline and window value is therefore carried in the blueprint
     extension as the string `"TODO: author decision (<decision>)"` or `"TODO: measurement (<D-n>)"`,
     which the schema constrains to that prefix.
   - Flow `quality` is **omitted**, since it is optional in the Phase 6 fixture builder. No number
     is written for a protocol value.
   - The engineering parameters that the platform needs for compilation are taken from accepted
     sources and labelled as such: action timeouts (as the Phase 7 blueprint), stop grace and stderr
     capture (S1b, as Phase 7), and the flow-policy queue depth (the Phase 6 fixture `FLOW_POLICY`).
5. **Flows and providers** (design §4).
   - F01 to F19 are inter-unit flows with `deliveryIntent` `ordered` in the `carla-simulation` time
     domain. Intra-unit messages are declared as flows with `intraUnit: true`.
   - The Phase 6 loopback provider takes at most 4 routes. So each consuming unit gets its own
     logical network and Deployment `networkBinding`, carrying an `io.xverse.xcom` `network-provider`
     payload. The provider is selected per flow through its `networkId`.
   - U2's inbound flows are split over two networks: the adapter link and the returns.
6. **`check_topology.py`** (offline). For each arm it checks:
   - **V01:** schema and semantic validation (`validate_sources`) and `compile_experiment_plan`; a
     deterministic plan digest over two compilations; the declared elements are present (both radar
     flows, IVI with no instance and no endpoint, no legacy VCU, no observer instance).
   - **V02:** the authority rules A-1 to A-7 of design §3.3, as a blueprint checker over the
     documents.
   - **D-4a:**
     - `prepare_lifecycle` admits the unbound element instances next to the bound unit instances, and
       derives exactly one unit per unit instance;
     - provider route assignment through `xverse.flows.binding.bind`: bindings, refusals, and at most
       4 routes per provider;
     - two concurrent `freeze` entries on `vc-functional` and `vc-assurance` (CC-1) pass
       `validate_static` and `prepare_lifecycle`;
     - the blueprint freeze-target rule refuses U1, U2, element instances and `crash`.
   - **Admission dry run:** `admit_schedule` with 5, 6 and 7 units at op 0.38, 0.29, 0.25 and 0.20 s,
     and the live parameters otherwise (cadence 5 s, S 4, per-unit 2 s, poll 0.05 s, 8192/8192, action
     timeouts). It also encodes the persistence configuration (`encode_configuration`) for each case,
     to measure its size against 65 536 bytes. A refusal at 6 or more units is recorded as the expected
     C1 dependency, not as a failure.
   - It writes a JSON report and exits non-zero only on a check failure.
7. **Synthetic inputs** are declared and never used as evidence of anything else. The provider
   helper pin and the permits needed by `encode_configuration` are owned-harness values, as in the
   platform bench (`tools/bench/persistence_scaling/bench_persistence.py`). No approval record is
   constructed or claimed.

### File plan (`automotive/assured-aeb/`)

| Path | Content |
| --- | --- |
| `docs/review-wp12.md` | this log |
| `topology.py` | the single-source declaration and the document generator (`python topology.py --write`) |
| `xdl/profiles/assured-aeb-v0.1.schema.json` | the blueprint extension schema |
| `xdl/<arm>/*.json` | generated documents for the four arms |
| `check_topology.py` | the offline checker and report |
| `tests/test_topology.py` | generator determinism; compile per arm; V02 negative fixtures; freeze-target refusals; route cap; the capacity rule against `admit_schedule` |
| `conftest.py` | sets `XVERSE_PLATFORM_PROFILES` (profile-schema directory) for the tests |

### Expected residuals (to be confirmed by the result)
- The 64 KiB limit at 6 or more units, pending C1.
- The F19 route cap in the authorization-bypass arm (WP-16).
- Simulator-time fault onset (WP-10): faults compile only in Maestro ticks today.
- Unit executables are declared module paths that do not exist yet (WP-13 to WP-17). Nothing runs.

## Finding 2: implementation result (commit `3aed505`; check report `docs/evidence/wp12-check-3aed505.json`)

**Environment and commands.**
- Interpreter: `/dev/shm/compat-p6-venv/bin/python -I` (CPython 3.13.13; wheel `xverse_xdl-0.4.0`, sha256
  `cea5ced4…`; its `xverse` and `xverse_xdl` sources equal tag `xverse-lite-v1.0.0-rc.1`).
- Profile schemas: from `git archive xverse-lite-v1.0.0-rc.1 xdl` into a scratch directory. The
  platform checkout was only read.
- Commands:
  - `python -I check_topology.py --platform-profiles <export>/xdl/profiles`: exit 0, 42 checks passed;
  - `XVERSE_PLATFORM_PROFILES=<export>/xdl/profiles python -I -m pytest tests`: 52 passed. Without the
    variable, 24 pass and the 28 platform-backed tests are skipped.
- Host load at the end: 5.57.
- Nothing ran a unit, a simulator, Maestro or CARLA.

### 2.1 Results

**Compile per arm (V01).** All four arms validate and compile in both forms, with no diagnostic. Each
plan digest is identical across two compilations, and the committed documents equal the generator
output.

| Arm | Units | Element instances (unbound) | Forward flows | Return flows | Intra-unit messages |
| --- | --- | --- | --- | --- | --- |
| comparator | 5 (U1–U5) | 22 | 12 | 1 (F04) | 24 |
| mloc | 6 (U1–U6) | 27 | 17 | 2 (F04, F15b) | 27 |
| authorization-bypass | 6 | 27 | 18 (with F19) | 2 | 27 |
| verification-bypass | 6 | 27 | 17 | 2 | 27 |

- Both radar flows are declared from `front-zone`: F08 to `fusion-risk-aeb` (U4) and F09 to
  `evidence-validator` (U5).
- IVI is a node with no instance and no endpoint.
- No legacy-VCU, stimulus, observer or oracle instance is declared.

**V02.** Rules A-1 to A-7 hold in every arm. The negative fixtures are rejected with the expected rules:
a proposer authorizing, a front-zone command, a raw camera item reaching perception, the relay feeding
the manager outside its ablation, the gate braking, an intra-unit message across units, an IVI
instance and an evaluation-only instance. The F19 exception holds only in `authorization-bypass`.

**D-4a.**

| Check | Result |
| --- | --- |
| Unbound element instances | Accepted. `prepare_lifecycle` on the Maestro form derives exactly the bound unit instances (5 or 6) next to 22 or 27 unbound element instances |
| Provider routes (`bind`) | `xcom_plan` status `activatable` in every arm. Per provider: net-adapter-link 3 (+ return F04 = 4), net-u2-returns 2, net-u3 2, net-u4 3 (+ return F15b = 4), net-u5 4, net-u6 3. Only refusal: **F19 `route_capacity_exhausted` on net-u5** in `authorization-bypass`, the expected WP-16 residual (§K) |
| CC-1 concurrent freezes | Two `freeze` entries at the same tick on `vc-functional-unit` and `vc-assurance-unit` pass `validate_static` and `prepare_lifecycle` (2 entries); the blueprint rule admits the pair |
| Freeze-target rule | The blueprint refuses a freeze of U1 or U2, a freeze of an element instance (`safety-gate`), a `crash` and `loss` on F07. **The platform admits each of these statically**, so the blueprint rule is load-bearing. `stale` on F09 is admitted by both |

**Admission dry run.** Live parameters (cadence 5 s, S = 4, per-unit 2 s, poll 0.05 s, 8192/8192,
action timeouts, horizon 600). `admit_schedule` agrees with `(2n + S + 1)·op < cadence` in all 12 cases.

| n | op (s) | Admitted | period / scan (s) | Thaw bound (s) | Reserve (s) | Requests / events | Config bytes, full Maestro form | Config bytes, slim alternative |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 0.38 | no (`HEALTH-CAPACITY`) | — | — | — | — | — | — |
| 5 | 0.29 | yes | 2.10 / 1.45 | 3.55 | 22.73 | 1621 / 1525 | 146 458 | 65 951 |
| 5 | 0.25 | yes | 2.50 / 1.25 | 3.75 | 21.25 | 1579 / 1420 | 146 433 | — |
| 5 | 0.20 | yes | 3.00 / 1.00 | 4.00 | 19.40 | 1543 / 1330 | 146 429 | — |
| 6 | 0.38 | no | — | — | — | — | — | — |
| 6 | 0.29 | yes | 1.81 / 1.74 | 3.26 | 26.76 | 1767 / 1898 | 170 503 | 75 605 |
| 6 | 0.25 | yes | 2.25 / 1.50 | 3.50 | 25.00 | 1697 / 1718 | 170 463 | — |
| 6 | 0.20 | yes | 2.80 / 1.20 | 3.80 | 22.80 | 1641 / 1574 | 170 477 | — |
| 7 | 0.38 | no | — | — | — | — | — | — |
| 7 | 0.29 | no | — | — | — | — | — | — |
| 7 | 0.25 | yes | 2.00 / 1.75 | 3.25 | 28.75 | 1838 / 2082 | 182 273 | 87 866 |
| 7 | 0.20 | yes | 2.60 / 1.40 | 3.60 | 26.20 | 1758 / 1872 | 182 302 | — |

- The derived values of WP-11 are confirmed by the platform: the 6-unit reserve of 26.8 s and thaw
  bound of 3.26 s at 0.29 s.
- **The 64 KiB limit refuses every Phase 8 case, including 5 units** (the expected C1 dependency).
  `encode_configuration` embeds every contributing XDL document. The full Maestro form, with 22 to 27
  element Components, therefore needs 146–182 KB.
- The slim alternative drops the element instances and Components, so the unit allocation would live
  outside the Maestro plan. It needs 66–88 KB, which is about 10 KiB per unit, consistent with S1a.
  Its 5-unit case exceeds 65 536 by 415 bytes, so after S1b the old 5-unit figure no longer holds even
  for the slim form.

### 2.2 Platform limits found (recorded; not repaired here)

| ID | Limit | Consequence and handling |
| --- | --- | --- |
| L-1 | `prepare_lifecycle` admits exactly one time domain (`projection.py` 274–276), and the plan lists every declared System domain (`experiment_plan.py` 1232–1272) | A plan with `carla-simulation` and Maestro ticks cannot be prepared. The documents come in two forms from one source: `topology` (both domains, flows; compiled and bound) and `maestro` (one `experiment-time` domain, no flows; prepared). The hub binds the flows, as the Phase 7 loop does (R-5) |
| L-2 | XDL orders instances by flow and refuses a cycle (`XDL1-PLAN-DEPENDENCY-CYCLE`, `experiment_plan.py` 1340–1404). A closed loop has cycles | The minimal feedback set, F04 `actuation-command` and F15b `configuration-state-proposer`, is declared as hub-bound return flows in the System extension. Both still count against their consumer's 4-route provider |
| L-3 | Deployment `networkBindings` admit no extension. The X-COM profile allows `network-provider` only on targets or networkBindings, and `_select_provider` picks providers by network through Profile references | One provider target per segment, keyed by one selector Profile per segment (`profile-net-*.json`) |
| L-4 | An X-COM contract id is the interface id, and the X-COM profile admits no System attachment | One Component per interface (the first producer in name order) carries the `interface-policy` |
| L-5 | X-COM Scenario observers must target routes | Scenario observers are hub flow-evidence taps. The ground-truth observer and the offline metrics (`A_DQ`, minimum gap) are declared in the Scenario extension (`scenario-evaluation`) and are never planned |
| L-6 | A Scenario with step and observer domains needs a declared mapping, but D6-4 admits only identity or offset | The pair `experiment-time` → `carla-simulation` is declared `unmapped:frames-per-tick-measured-per-run`. Its tolerance of 0 ticks is a schema-required number, not a protocol value |
| L-7 | The platform admits, statically, a freeze of an element instance or of a never-frozen unit, a `crash`, and `loss` on any flow | The blueprint `check_fault_admission` rule refuses them, and it must run before any schedule is admitted (WP-10/WP-16) |
| L-8 (WP-10) | A fault keyed to `carla-simulation` at 1.5 s compiles to `atTicks` 1 500 000 000 (nanosecond canonical unit). `validate_static` refuses it (`XVERSE-FAULT-HORIZON`), and only the one-domain Maestro form is preparable | Simulator-time fault onset (§K) needs a platform or hub mechanism. It is not available at rc.1 |
| L-9 | The experiment profile requires an integer scenario seed | Seed 0 is a declared structural placeholder; the seed lists are TODO (P-4) |

### 2.3 Representation of TODO values
- XDL v1alpha1 has no placeholder mechanism.
- Every latency, freshness, deadline and acceptance value is a string `TODO: <author decision|measurement|engineering
  verification|design> (<ref>)` in `io.xverse.assured-aeb`, and the extension schema enforces that pattern.
- Flow `quality` is omitted.
- The engineering parameters needed to compile (action timeouts, stop grace, stderr cap, flow-policy
  queue depth 4, the 600-tick capacity horizon, the observe tick, seed 0, the probe tick and duration of
  the D-4a fault probes) carry their source in `topology.ENGINEERING_SOURCES` or in the check notes.

### 2.4 Residuals
1. **C1 sizing.** The 64 KiB limit refuses every Phase 8 configuration. C1 must cover at least 182 302 B
   (7 units, full Maestro form) plus margin, or about 88 KB if the slim form is adopted. This is
   **larger than "enough for 7 units" at S1a's per-unit rate**, because the documents dominate. It is a
   decision for the C1 increment and the author; it is not resolved here.
2. **F19 route cap** (WP-16).
3. **Simulator-time fault and freeze onset** (WP-10; L-8).
4. **Two-form projection (L-1, L-2).** The Maestro form omits flows. The flow plan, verdicts and return
   flows are the hub's responsibility (WP-10, WP-13), and its fidelity to the topology form must be
   checked when the hub exists.
5. **Declared but non-existent.** The unit module paths, working directories, the perception model digest
   (WP-09) and the U4 inference venv (WP-08). No live execution is authorized.
6. **Interpreter pins** are host digests at generation (`xdl/pins.json`); the check reports drift.

No platform file was changed. This is engineering evidence only: not M1, not AEB evidence and not
X-Verse fitness for purpose. An independent read-only review comes next, then acceptance and merge.

## Finding 3: independent review of findings 1 and 2 (2026-10-24 11:20:22)

**Reviewer and method.**
- An independent, read-only reviewer who did not write this increment.
- Read `fe51b0b`, `3aed505` and `58d5726` against base `99df3a4`, together with `topology.py`,
  `check_topology.py`, `tests/test_topology.py` and the generated documents. Checked them against the
  thesis design records `wp11-unit-allocation.md` and `wp12-xdl-topology.md` (§3.3, §4, §5, §7 and §8)
  and `decisions.md` §J and §K.
- The profile schemas came from `git archive xverse-lite-v1.0.0-rc.1 xdl` of `/home/jefferson/xverse-platform`
  (`64ff9d3eb`), extracted into a scratch directory.
- Commands:
  - `/dev/shm/compat-p6-venv/bin/python -I check_topology.py --platform-profiles <export>/xdl/profiles
    --report <scratch>`: exit 0, 42 checks, all `ok`;
  - `XVERSE_PLATFORM_PROFILES=<export>/xdl/profiles … -I -m pytest tests -q -p no:cacheprovider`:
    52 passed;
  - `topology.py --write` in a scratch `git archive` copy: `diff -r` against the committed `xdl/` is
    empty.
- Probes ran in that copy or in memory: the fault-admission rule, cycle detection with the intra-unit
  messages included, a field-by-field comparison of the two forms, a scan for numbers in the documents,
  and the X-COM contract owners. Nothing in the worktree changed except this entry. No CARLA, no live
  run, no unit process.

### Verdict: **FAIL: one HIGH issue blocks the merge** (a small repair)

Everything else is sound or needs recording only. Once HIGH-1 is repaired and re-reviewed, the
increment is expected to pass with notes. This verdict is engineering only and carries no acceptance.

### Confirmed
- **Determinism (V01).** The regenerated documents equal the committed ones, and the drift check and the
  two-compilation plan digest pass for every arm and form.
- **Arm composition (§7, §J).**
  - The comparator has U1–U5 and 22 element instances, without proposer, goal-interpreter,
    objective-source, safety-monitor, safety-gate or F12–F16.
  - The MLOC arms have U1–U6 and 27 element instances.
  - F19 exists only in `authorization-bypass`.
  - There is no legacy VCU, stimulus, observer or oracle instance, and IVI has no instance or endpoint.
  - The camera corruption stage is hosted in U2 (the FR-031 point of §J).
- **Admission dry run.** The 12 cases agree with `(2n + S + 1)·op < cadence`, for example n 6 at op
  0.29: 17 × 0.29 = 4.93 < 5, admitted; n 7 at op 0.29: 5.51, refused.
- **V02.** A-1 to A-7 hold in every arm, and every rule has at least one rejected negative case
  (test_topology.py 64–103). The F19 exception holds only in its own arm.
- **Placeholders.**
  - The `io.xverse.assured-aeb` extension contains no number. In the `mloc` topology form, 84 members are `TODO: …` strings,
    constrained by the schema pattern (`assured-aeb-v0.1.schema.json` 79).
  - Seed 0 (L-9, `ENGINEERING_SOURCES`) and the time-mapping tolerance 0 (L-6) are declared
    placeholders.
  - `deadlineMs: 0` in the X-COM flow policy is platform-mandated: `binding.py` 306 refuses any other
    value. It is not a protocol deadline.
- **The two forms.** For every arm, the topology and Maestro forms have identical `componentInstances`,
  identical Deployment `bindings`, and an identical `io.xverse.assured-aeb` extension except `form` and
  `unplannedFlows`. The Maestro form drops only `flows`, `networks`, the two non-experiment domains, the
  provider targets, the network bindings and the CARLA simulator entry.

### Issues

**HIGH-1: the blueprint freeze-target rule admits a lone freeze of `vc-functional`, which design §5
forbids.** This blocks the merge.
- Where: check_topology.py 222; the source is topology.py 255.
- `admitted = set(admitted) | {every member of every admittedSet}` makes each member of the CC-1 pair
  admissible on its own. Probes on `mloc`:
  - a single `freeze` of `vc-functional-unit` gives **no refusal**;
  - the "pair" at different ticks (100 and 300) gives no refusal.
- Design §5 admits only `front-zone`, `adas-hpc` and `vc-assurance`, plus the pair together. CC-2c says
  "none by `freeze` alone".
- A freeze of U5 alone stops the functional AEB path, the fixed-fallback supervisor and the whole
  degraded path ([N] 1497). That is outside every decided case.
- Finding 2 calls this rule load-bearing, because the platform admits such freezes statically (L-7).
  Its D-4a row reports the rule as passing, but `tests/test_topology.py` 106–112 has no lone-U5 case.
- Repair:
  - a member of an `admittedSet` that is not individually admitted is admitted only when every member
    of the set is frozen with the same onset (and, if declared, the same duration);
  - add negative tests for a lone `vc-functional-unit` and for a non-concurrent pair;
  - correct the D-4a row of finding 2.

**MEDIUM-1: the two return flows are minimal only for the XDL-visible graph. The real inter-unit loops
are closed through intra-unit messages that XDL cannot see.** Not blocking.
- Where: topology.py 207–212; finding 2, L-2.
- The intra-unit messages live in the System extension, so `XDL1-PLAN-DEPENDENCY-CYCLE` does not see
  them.
- With them included, a probe finds 10 cycles (comparator) or 11 (MLOC arms) after removing F04 and F15b.
  Two of them cross units:
  - the brake loop `loop-gateway →F06 smart-radar → front-zone →F07/F08 … fusion-risk-aeb →F11
    evidence-validator → … → functional-arbiter → chassis-zone → brake-esc-node →F17 loop-gateway`
    (U2 → U3 → U4 → U5 → U2);
  - in the MLOC arms, the authorization loop `configuration-manager →F15a safety-monitor →
    safety-gate →F14 configuration-manager` (U5 → U6 → U5).
- F04 and F15b break neither of them. The statement that the set "breaks every cycle" is therefore true
  only of the XDL instance graph.
- At run time each loop is broken by the hub's one-tick delay, as in the Phase 7 loop. The hub (WP-13)
  must know which flows carry that delay: at least F17, and F14 or F15a.
- Repair: correct the wording in topology.py and in L-2, and add to residual 4 that the hub's
  delay points include F17 and F14/F15a. Alternatively, declare those flows as return flows too.

**MEDIUM-2: no admission path enforces the blueprint fault-admission rule, and residuals 1–6 do not
say so.** Not blocking while nothing runs.
- Where: finding 2, L-7, and §2.4.
- L-7 says the rule "must run before any schedule is admitted". Today it runs only inside the offline
  checker and its tests. No generator, plan or admission hook calls it, and the platform admits
  every refused case statically.
- Add a residual: WP-10 and WP-16 must call `check_fault_admission` on the exact fault schedule before
  `admit_schedule` and refuse on any finding. Until then a freeze of U1 or U2, a freeze of an element
  instance, a `crash`, or an unadmitted message fault would be accepted.
- The rule also does not bound a freeze duration by the WP-11 thaw bound. Durations are TODO, but the
  check should exist once they are set.

**MEDIUM-3: deviations from the design's §4 flow table are not recorded.** Not blocking.
- Where: topology.py 178, 184, 186 and 190.
- XDL flows here have one destination, and some consumers are reached through intra-unit messages
  instead of the flow itself:
  - F03 ends at `loop-gateway` (design: `motion-sensor-model`), and the model is fed by an intra message;
  - F09 ends at `evidence-validator` only (design: `radar-fallback` and `evidence-validator`, "the
    direct logical stream, [N] 1497"). `radar-fallback` now receives only `qualified-evidence` through
    the validator;
  - F11 ends at `evidence-validator` only (design: also `functional-arbiter`);
  - F15a starts at `configuration-manager` only (design: also `transition-verifier`).
- The degraded-path dependency list still holds, because the validator is in the VC-HPC dependency. The
  radar fallback is no longer fed directly, however, and that is a design change.
- Record each deviation and its reason in this log for the design owner's acceptance. Either restore a
  direct radar input to `radar-fallback` (a second destination on F09, or an intra fan-out from the
  front-zone input), or amend design §4.

**LOW-1: the two forms are equal by construction, but no check asserts it.** Optional: add a check that
instances, bindings and the extension, except `form` and `unplannedFlows`, are identical. In addition,
`d4a-topology-form-maestro` (check_topology.py 453–458) reports `True` even when the topology form
becomes preparable, so it cannot fail.

**LOW-2: the Maestro form cannot carry message faults.** The fidelity gap in the two-form projection
(under L-1, L-4 and L-8) is wider than residual 4 states.
- The preparable form has no flows, so the relay faults of §K (F09 loss, stale and delay; the F12 and
  F13 assurance kinds) can be checked only by `validate_static` on the topology form
  (`_static_message_fault`). They cannot be in a Maestro schedule at rc.1.
- The Maestro plan also declares no flow evidence, and `unplannedFlows` lists only flow ids.
- Residual 4 should say that the hub carries the message-fault schedule and the flow evidence, and that
  it reads both from the topology form.

**LOW-3: the contract of `proposal` is carried by `fault-relay`.** In the MLOC arms, `fault-relay`, an
experiment-control element, carries the X-COM `interface-policy` of `proposal`, because L-4 assigns
the contract to the first producer in name order. This is harmless for compilation, but WP-13 must not
read the contract carrier as the proposal's owner. Optionally pick the carrier by authority class.

**LOW-4: smaller points.**
- `scenario.json` step `schedule.tolerance` 0 ticks (topology.py 626) is an engineering value with no
  entry in `ENGINEERING_SOURCES`.
- A-7's evaluation-only detection matches id substrings (`ground-truth`, `oracle`, `observer`;
  check_topology.py 212), so a differently named evaluation instance would pass.
- A-4 has no negative case for the right producer sending to the wrong consumer.

### Residuals 1 to 6
- Residuals 1, 2, 3, 5 and 6 are accurate.
- Residual 4 is incomplete: see MEDIUM-1 and LOW-2.
- Missing: the enforcement gap of MEDIUM-2 and the unrecorded design deviations of MEDIUM-3.

### Recommendation
- Repair HIGH-1, with tests, on this branch.
- Record MEDIUM-1 to MEDIUM-3 in a disposition: the wording of L-2 and residual 4, an enforcement
  residual, and the §4 deviations for the design owner. Optionally repair LOW-1 to LOW-4.
- Then a focused re-review, followed by acceptance and merge.

## Finding 4: disposition of finding 3 (2026-10-24 11:22:19; recorded before any change)

This disposition is the coordinator's, under the author's delegation of 2026-10-24, and is flagged for the
author's review. Nothing in this entry repairs anything. The repairs follow in a later commit, and their
result is finding 5.

| Item | Disposition | Planned change |
| --- | --- | --- |
| HIGH-1 | Repair | In `check_fault_admission`, a member of an `admittedSet` that is not individually admitted is admitted only when every member of the set is frozen with the same onset and the same duration. Negative tests for a lone `vc-functional-unit` freeze and for a non-concurrent pair; a positive test for the concurrent pair. Correct the D-4a row of finding 2 (in finding 5; finding 2 stays as recorded) |
| MEDIUM-1 | Correct | Correct the RETURN_FLOWS / L-2 claim: F04 and F15b break only the XDL-visible cycles. Declare the cross-unit cycle delay points as hub-delayed, with a one-tick delay, in the flow extension: **F17** (brake loop U2→U3→U4→U5→U2), and **F14 and F15a** (MLOC authorization loop U5→U6→U5). Name them in residual 4. A test checks that every remaining cycle in the graph, intra-unit messages included, crosses a declared delay point |
| MEDIUM-2 | Residual and rule extension | WP-10 and WP-16 must call `check_fault_admission` on the exact schedule before `admit_schedule`. The rule takes an optional thaw bound and refuses a freeze whose duration exceeds it when that bound is known. The bound is a parameter: the 3.26 s of the dry run at 6 units and op 0.29 is passed in by the caller and is never hard-coded as a protocol value |
| MEDIUM-3 | Repair F09; record the rest | Restore F09's direct radar input to `radar-fallback`, so the degraded path does not depend on the validator for its raw radar. For F03, F11 and F15a, restore the design where the route cap allows; otherwise record the deviation and its justification for the design owner (finding 5) |
| LOW-1 | Repair | A real assertion that the topology and Maestro forms are equal apart from `form` and `unplannedFlows`, with a test that shows it can fail. `d4a-topology-form-maestro` must fail if the topology form becomes preparable |
| LOW-2 | Record | Extend residual 4: the hub reads the relay faults and the flow evidence from the topology form |
| LOW-3, LOW-4 | Optional | LOW-3: pick the contract carrier by authority class rather than name order. LOW-4: add the A-4 wrong-consumer negative, and the tolerance-0 source entry |

## Finding 5: result of the finding 4 repairs (2026-10-24 11:28:30; repair commit `5e53a54`; report `docs/evidence/wp12-check-5e53a54.json`)

**Commands.** Same environment as finding 2. `check_topology.py`: exit 0, 50 checks passed. pytest:
74 passed. Without `XVERSE_PLATFORM_PROFILES`, 44 pass and 30 are skipped. Host load 5.79. No unit,
simulator, Maestro run or CARLA was involved.

### 5.1 Per item

**HIGH-1, repaired.** `check_fault_admission` now admits a member of an `admittedSet` that is not
individually admitted only when every member of the set is frozen with the same onset (trigger kind, at,
unit, time domain) and the same duration. The following are refused:
- a lone `vc-functional-unit` freeze;
- the pair at onsets 100 and 300;
- the pair with durations 10 and 20;
- `vc-functional-unit` in the comparator, where the set does not exist.

The concurrent pair is admitted, and the platform still prepares it (2 entries). Tests:
`test_lone_vc_functional_freeze_is_refused`, `test_non_concurrent_cc1_pair_is_refused` (2 cases),
`test_concurrent_cc1_pair_is_admitted` and `test_cc1_pair_is_refused_in_the_comparator_…`.

**Correction to finding 2's D-4a "freeze-target rule" row.** The rule as recorded there admitted a lone
or non-concurrent freeze of `vc-functional-unit` (finding 3). That row's claim, that the rule refuses
everything outside design §5, was wrong for that case at `3aed505`, and holds from `5e53a54`.

**MEDIUM-1, corrected.**
- **Wording.** The `RETURN_FLOWS` comment and L-2 now say that F04 and F15b break only the cycles
  visible to XDL (forward flows). F15b is needed for XDL acyclicity
  (`test_f15b_return_flow_is_needed_for_xdl_acyclicity`: adding it as a forward flow gives
  `XDL1-PLAN-DEPENDENCY-CYCLE`).
- **Hub delay points**, each declared as `hubDelay: {unit: simulator-step, value: 1}` in the flow
  extension:
  - **F17** `brake-command`, the brake loop U2→U3→U4→U5→U2;
  - **F14** `authorization`, the MLOC authorization loop U5→U6→U5;
  - **F04** and **F15b**, the return flows, which are hub-delayed by construction.

  F14, not F15a, is the cut. F14 is the only U6→U5 flow, and delaying F15a alone would leave the loop
  through F13 and F14 closed.
- **`check_cycles`.** It takes the strongly connected components of the full graph (forward, return and
  intra-unit messages) after removing the delay points.
  - No cross-unit component remains in any arm.
  - Removing the delay of F17, F14 or F04 reopens its loop (`test_each_delay_point_is_necessary`).
  - Two intra-unit components remain:
    - U5: arbiter, chassis zone, brake node, manager, verifier, supervisor, validator and related roles;
    - U2: gateway and driver profile.

    They are resolved by each unit's own step order (WP-13, WP-14) and are listed in the report.
- The one-step value is the hub's lockstep semantics, with its source in `ENGINEERING_SOURCES`
  (`hubDelayTicks`). Its relation to the AD-30 latency declaration is `TODO: author decision (AD-30)`.

**MEDIUM-2, residual and rule extension.**
- `check_fault_admission(docs, faults, freeze_bound)` takes an optional `FreezeBound(thaw_bound_s,
  max_cycle_s)`. The thaw bound is `cadence − health_scan_seconds` of the admitted schedule (3.26 s at
  6 units and op 0.29 in the dry run). The maximum cycle is the D-4c measurement.
- Both are supplied by the caller and nothing is hard-coded. The test derives the thaw bound from
  `admit_schedule`, and uses 0.1 s as a labelled stand-in cycle.
- Without a bound, durations are not checked, and the check report says so.

**MEDIUM-3, repaired or recorded.**

| Flow | Design §4 | Now | Status |
| --- | --- | --- | --- |
| F09 `radar-vc` | `radar-fallback` and `evidence-validator` | front-zone → **`vc-ingress`** (U5 inbound fan-out), then intra to `radar-fallback` **and** `evidence-validator`. The fallback takes the raw radar directly, not through the validator | **Restored** (`test_degraded_path_takes_radar_directly_not_through_the_validator`). `vc-ingress` is in the degraded-path VC-HPC dependency |
| F11 `adas-cycle` | `evidence-validator` and `functional-arbiter` | fusion → `vc-ingress`, then intra to `functional-arbiter` **and** `evidence-validator` | **Restored** |
| F15a | from `configuration-manager` and `transition-verifier` | F15a from the manager, plus **F15c** `transition-verdict-assurance` from the verifier to the monitor (net-u6: 4 routes, the cap) | **Restored** as two flows |
| F03 `motion-raw` | to `motion-sensor-model` | to `loop-gateway`, then intra to the motion model **and** the driver profile | **Deviation, recorded for the design owner.** The adapter link (`carla-items/2`, DLG-8) is one socket terminated at the gateway. Both design consumers are in U2, so there is no inter-unit difference, and a direct F03 would add a fourth adapter-link route without a gain |

`vc-ingress` is a forwarding element (`evidence-router`, emitting only `radar-evidence` and `adas-cycle`).
It is the one-destination realization of the design's two-destination flows within the 4-route cap.
It is a design addition and is recorded for the design owner's acceptance.

**LOW-1, repaired.**
- `forms_difference` asserts that the topology and Maestro forms agree, except for the declared
  projection: instances, endpoints, interfaces, nodes, the extension minus `form` and `unplannedFlows`,
  bindings, unit targets, steps and Components.
- It is empty in every arm, and `test_forms_difference_can_fail` shows it detects a mutation.
- `d4a-topology-form-maestro` now fails if the topology form becomes preparable, or if it is refused
  for a reason other than `ML-TIME`.

**LOW-2, recorded** in residual 4 below.

**LOW-3, repaired.** The contract carrier is chosen by authority class. `proposal` is carried by
`proposer`, not `fault-relay` (test).

**LOW-4, repaired in part.**
- The A-4 wrong-consumer negative (arbiter → brake node directly) is rejected.
- `stepScheduleTolerance` has a source entry.
- The substring-based evaluation-instance detection of A-7 is unchanged and is recorded as a limit.

### 5.2 Updated figures
- **Arms.** Comparator: 23 element instances, 12 forward and 1 return flows, 28 intra-unit messages.
  MLOC and verification bypass: 28, 18, 2 and 31. Authorization bypass: 28, 19, 2 and 31.
- **Routes per provider.** At most 4 in every arm; net-u5 and net-u6 are at 4 in the MLOC arms. The
  only refusal is still F19 (`route_capacity_exhausted`) in `authorization-bypass`, the WP-16 residual.
- **Admission.** `admit_schedule` agrees with the capacity rule in all 12 cases, and the thaw bounds and
  reserves are unchanged.
- **Configuration bytes** (full Maestro form): 150 053 (5 units at 0.29 s), 174 586 (6 at 0.29) and
  186 358 (7 at 0.25). The slim alternative gives 65 951, 75 605 and 87 866. Every case is still over
  65 536, so the C1 dependency remains.

### 5.3 Residuals (replaces finding 2 §2.4)
1. **C1 sizing.** At least 186 358 B (7 units, full Maestro form) plus margin, or about 88 KB with the
   slim form. This decision belongs to the C1 increment and the author.
2. **F19 route cap** (WP-16).
3. **Simulator-time fault and freeze onset** (WP-10; L-8).
4. **Two-form projection and hub responsibilities** (L-1, L-2; finding 3 MEDIUM-1, LOW-2).
   - The Maestro form omits the flows. The hub (WP-10, WP-13) carries, and reads from the topology
     form:
     - the forward and return flows;
     - the hub delay points **F04, F14, F15b and F17** (one simulator step each);
     - the relay faults of §K (F09 `loss`, `stale` and `delay`; the F12 and F13 assurance kinds), which
       cannot be in a Maestro schedule at rc.1 and are checked only by `validate_static` on the
       topology form;
     - the flow evidence (the Scenario taps).
   - The fidelity of the hub to the topology form must be checked when the hub exists.
   - The intra-unit cycles of U5 and U2 are resolved by each unit's step order (WP-13, WP-14).
5. **Enforcement** (finding 3 MEDIUM-2). WP-10 and WP-16 must call `check_fault_admission`, with a
   `FreezeBound` once D-4c gives the maximum cycle, on the exact fault schedule before `admit_schedule`,
   and refuse on any finding. Until then the platform statically accepts what the rule refuses.
6. **Design-owner items** (MEDIUM-3): the `vc-ingress` addition, F15c, and the F03 deviation.
7. **Declared but not yet existing:** the unit module paths, the perception model digest (WP-09) and the
   U4 inference venv (WP-08). No live execution is authorized.
8. **Interpreter pins** are host digests (`xdl/pins.json`); drift is reported by the check.
9. **A-7 limit.** The evaluation-only detection matches names (LOW-4).

The next step is a focused re-review of `5e53a54` against finding 3, then acceptance and merge. Neither
has happened.
