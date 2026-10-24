# WP-04 review log: brake/ESC software-status node and chassis zone (Phase 8; FR-033, AD-17 option B)

Candidate: branch `candidate/phase8-wp04-brake-esc-node-20261024`, from blueprints main `7851c47` (WP-12
merged). This is a direct engineering increment, and the log follows the same order:
1. findings come before repairs;
2. an independent read-only review;
3. acceptance;
4. a merge.

None of the last three has happened yet.

**Inputs.**
- Thesis `specs/002-assured-aeb`:
  - `implementation-plan.md` WP-04;
  - `spec.md` FR-033, FR-041 and V26, V34;
  - `decisions.md`: AD-17 option B, AD-14 option E2 (the node's "accepted" status is the
    actuator-facing acceptance point), §J (chassis zone and brake/ESC node in U5, CC-2c) and §K;
  - `design/wp12-xdl-topology.md` §4.
- This repository: the WP-12 topology (`topology.py`: element classes, the intra-unit messages
  chassis-zone ↔ brake-esc-node and arbiter → chassis-zone, F10, and **F17 `brake-command`** to the
  vehicle-loop hub, hub-delayed by one simulator step).
- `xverse-compat` main `34cc046` (WP-03), read-only:
  - `src/xverse_compat/live/driver_profile.py`: `ArbitratedDriver(params, brake_request)` calls
    `brake_request(sim_s)` once per tick;
  - review-wp03 B-3 as amended (`docs/engineering/phase8/review-wp03.md` 307–310): the source returns
    0.0 whenever no AEB request is active, including before the WP-04 node's first message, and returns
    `None` only for a stale or lost source;
  - `src/xverse_compat_carla/actuation.py` 37–38: the adapter refuses a brake outside [0, 1].

**Scope.** Offline modules and tests only. No live run, no CARLA, no unit process and no hub. This
is engineering evidence: not AEB evidence, not M1, not X-Verse fitness for purpose.

## Finding 1: design (recorded at 11:35:13, before any code)

### 1.1 Placement and boundary
- Both elements are modules of U5 `vc-functional` (§J; CC-2c), in the 7-unit variant of
  `chassis-brake`. The code does not assume co-location: every input and output is a typed message,
  matching the WP-12 element interfaces exactly:
  - `chassis-zone`: in `brake-request` (from `functional-arbiter`), `aeb-status` (from
    `fixed-fallback-supervisor`), `motion-evidence` (F10) and `brake-status` (from the node); out
    `brake-request` (to the node) and `motion-evidence` (to `vehicle-state`);
  - `brake-esc-node`: in `brake-request` (from the chassis zone); out `brake-command` (**F17** to
    `loop-gateway` in U2) and `brake-status` (to the chassis zone).
- **Forwarding.** The node never writes to CARLA. Its only actuation-path output is F17, which the U2
  hub delivers one simulator step later (`hubDelay`). The gateway's ED-15 arbitration (WP-03) then
  puts it in the one command per tick that the adapter, the single actuator writer, applies
  ([A7] 36–38).
- **Time.** Only simulation time is used: integer nanoseconds (`originNs`, `atNs`) as in the compat
  items. No host or wall clock is read. A step is `step(sim_ns, delivered_messages)` and returns the
  emitted messages and evidence records.

### 1.2 Messages (closed schemas; V26)

| Message | Schema | Members (exactly) |
| --- | --- | --- |
| Brake request (arbiter → chassis zone) | `assured-aeb.brake-request/1` | `schema`, `source` (`functional-arbiter`), `sequence` (per-cycle counter, FR-041), `originNs`, `value` |
| Routed brake request (chassis zone → node) | `assured-aeb.brake-request/1` | the same members, with `source` = `chassis-zone`, plus `route` = [`functional-arbiter`, `chassis-zone`] and `receivedNs` |
| Brake status (node → chassis zone) | `assured-aeb.brake-status/1` | `schema`, `node` (`brake-esc-node`), `status`, `requestSequence`, `reason` (`null` unless rejected), `atNs` |
| Brake command (F17, node → hub) | `assured-aeb.brake-command/1` | `schema`, `node`, `sequence` (node counter), `requestSequence`, `requestOriginNs`, `originNs` (forwarding time plus the declared compute latency), `value`, `status` (`forwarded`) |

- **Status vocabulary:** `received`, `accepted`, `rejected`, `forwarded` and `injected-fault`.
- **Rejection reasons:** `malformed`, `wrong-source`, `out-of-range`, `stale` and `replayed`.
- **What is never published:** no member carries wheel speed, deceleration, pressure, "applied",
  "engaged" or any claim about the physical brake. Braking effect is judged offline from the
  evaluation-only motion (FR-033; V26). A vocabulary check rejects any other member or status value.

### 1.3 Node state machine (per delivered request, in sequence order)
1. **received**: a status is emitted for every delivered request message.
2. **Validation** (first failing rule wins; the result is **rejected** with that reason):
   - **malformed**: not the schema, a missing or extra member, a non-integer `sequence` or
     `originNs`, or a non-number value;
   - **wrong-source**: `source` ≠ `chassis-zone`, or `route` ≠ [`functional-arbiter`,
     `chassis-zone`]. Only the arbiter's request, routed by the chassis zone, is accepted (A-4 chain);
   - **out-of-range**: a value outside [0, 1], the actuator domain refused by the adapter
     (`actuation.py` 37–38). It is an engineering domain, not a protocol value. The node does not
     clamp. WP-03 still clamps a value above 1, as a second line;
   - **stale** (simulation time): `sim_ns − originNs > stalenessWindowNs`, or `originNs > sim_ns`
     (a future origin);
   - **replayed**: `sequence` ≤ the last accepted sequence.
3. **accepted**: this is the AD-14 actuator-facing acceptance point (FR-041). Its `atNs` is the
   acceptance time judged against the AD-07 deadline offline.
4. **forwarded**: one F17 `brake-command` per accepted request, carrying the value. A request of 0 is
   accepted and forwarded like any other, since it releases. A rejected request forwards nothing, so
   the last forwarded command stands. That is conservative, because a rejected release holds the brake.
5. **injected-fault**: reserved; see §1.6.

### 1.4 Staleness rule
- The window `stalenessWindowNs` is a protocol value (AD-06 freshness, AD-07 deadlines; AD-27
  record). **It has no default.**
- `BrakeNodeParams.from_record` refuses a record with a missing, extra, ill-typed or non-positive
  member, as `SpeedHoldParams.from_record` does.
- The node's compute latency `computeLatencyNs` (AD-30, the element's `computeLatency` in WP-12) is
  the second required member, with no default. It may be 0 only if the AD-30 declaration says so.

### 1.5 Chassis zone (Note 21: receive motion evidence, route scoped actuation requests, report status)
- **Requests.** It routes only a well-formed `brake-request` whose `source` is `functional-arbiter`.
  It re-stamps the request with `source` `chassis-zone`, its `route` and `receivedNs`, leaves the
  value and sequence untouched, and validates nothing else: value and staleness are the node's single
  check. Any other request is refused with a `route-refused` evidence record and is not forwarded.
- **Other inputs.** It forwards `motion-evidence` (F10) to `vehicle-state` unchanged. It records
  `aeb-status` (AD-39 report) and every node `brake-status` as evidence (acknowledgements).
- **Authority.** It has no configuration or selection authority.

### 1.6 Fault hooks
- **No decided H4 case touches the node or the chassis zone.**
  - H4-01 to H4-09 act on the monitor and gate, the manager and rollback (owned hooks), the ADAS/AD
    unit, `radar-vc`, the front zone and the proposal path.
  - The §K relay admits faults on F09, F12 and F13 only.
  - The WP-12 freeze rule admits no element instance, so U5 is frozen only in the CC-1 pair.
- **No hook is implemented.** `injected-fault` is kept in the vocabulary, because FR-033 names it.
  Nothing emits it in Phase 8.
- **Design point for the owner.** If a brake-path fault is admitted later, its injection must not bring
  the schedule into U5 (FR-028), and a runtime-visible "injected fault" status would tell runtime
  units that a fault was injected (the leak risk noted in decision-proposals-20261024b 177). The
  proposal is that it be recorded as evidence only, never on a runtime flow. DECISION NEEDED; not
  implemented.

### 1.7 The WP-03 `brake_request` source (B-3)
- `BrakeCommandReader` is the gateway-side (U2) adapter that the WP-10 hub will feed. It has two calls:
  - `deliver(command)` stores the newest valid F17 `brake-command` by node sequence;
  - `__call__(sim_s)` is the `brake_request` callable of `ArbitratedDriver`.
- It returns:
  - **0.0** before the first command, and whenever the newest command has value 0, matching B-3: no
    active request;
  - **the value** of the newest command while `sim_ns − originNs ≤ stalenessWindowNs`;
  - **`None`** (an invalid request, so WP-03 holds the last brake with throttle 0) when the newest
    command is older than the window, or when the hub reports the flow lost (`mark_lost`).
- Its window is a separate required parameter (`assured-aeb.brake-command-reader/1`), with no
  default.
- `sim_s` is converted to nanoseconds by `round(sim_s * 1e9)`.
- The rule relies on the per-cycle request of FR-041: the arbiter emits a request, possibly 0, every
  decision cycle, so freshness is meaningful.

### 1.8 Files and tests (planned)
- **`assured_aeb/__init__.py` and `assured_aeb/brake_esc.py`:** the message builders and the
  vocabulary check, `BrakeNodeParams`, `BrakeEscNode`, `ChassisZone` and `BrakeCommandReader`.
  Standard library only.
- **`tests/test_brake_esc.py`:**
  - each status and rejection rule;
  - acceptance timing in simulation time;
  - no wheel speed and no applied claim (V26);
  - parameter records refused without values (TODO, no default);
  - chassis-zone routing and refusals;
  - the reader's 0.0, value and `None` cases;
  - an end-to-end offline chain: arbiter request → chassis zone → node → F17 → reader → WP-03
    `arbitrate` semantics. The compat module is not imported; its contract (B-3) is asserted on the
    reader.
- **Test parameter values** (window, latency) are labelled test values, not protocol values.

### 1.9 Expected residuals
1. Window and latency values (AD-06, AD-07, AD-30; the freeze, AD-27).
2. The fault-hook decision (§1.6).
3. Hub delivery (WP-10) and unit wiring (WP-13, WP-14).
4. V34 Argus event emission: the evidence records are produced here; the Argus extension is ED-12.
