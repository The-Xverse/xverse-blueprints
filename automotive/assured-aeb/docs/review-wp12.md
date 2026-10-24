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
