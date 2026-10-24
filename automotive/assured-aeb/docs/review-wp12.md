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
