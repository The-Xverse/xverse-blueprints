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
     clamp. *[Corrected in finding 5: no value above 1 reaches WP-03 through F17, so its clamp is not a second
     line on this path; the arbiter's [0, 1] output contract is a WP-13/WP-14 obligation. The original text
     read "WP-03 still clamps a value above 1, as a second line".]*;
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

## Finding 2: implementation result (2026-10-24 11:37:52; commit `9e9b15b`)

**What was added.**
- `assured_aeb/brake_esc.py` (standard library only), containing:
  - the message builders and the closed-vocabulary check `check_vocabulary` (V26);
  - `BrakeNodeParams` and `ReaderParams`, whose `from_record` takes no defaults;
  - `ChassisZone`, `BrakeEscNode` and `BrakeCommandReader`.
- `tests/test_brake_esc.py`: 42 tests.

**Commands.**
- `/dev/shm/compat-p6-venv/bin/python -I -m pytest tests/test_brake_esc.py`: **42 passed**.
- The whole blueprint suite with `XVERSE_PLATFORM_PROFILES` (rc.1 export): **116 passed**, the 74
  WP-12 tests included.
- `check_topology.py`: exit 0. The WP-12 documents are unchanged.
- Host load 5.0. No live run, no CARLA, no unit process; the loop10 worktrees and the pinned live
  environment were not touched.

**Results against the design (finding 1).**

| Design item | Implemented and tested |
| --- | --- |
| State machine §1.3 | Every delivered request yields `received`, then `accepted` with `forwarded` (one F17 command), or `rejected` with one reason. Requests of one step are processed in sequence order. A zero request is accepted and forwarded as a release. A rejected request forwards nothing |
| Rejection rules | `malformed` (non-object, wrong schema, missing or extra member, non-integer `sequence`/`originNs`/`receivedNs`, non-number or NaN or bool value), `wrong-source` (source ≠ chassis zone, or route ≠ arbiter → chassis zone), `out-of-range` (outside [0, 1], not clamped), `stale` (age > window, or a future origin; the window boundary itself is fresh), `replayed` (sequence ≤ the last accepted one) |
| Simulation time | Only integer-nanosecond simulation time; a non-integer step time is refused. Status `atNs` is the acceptance time (AD-14). The F17 `originNs` is the forwarding time plus the declared compute latency |
| Outputs (V26) | Only the declared `brake-status/1` and `brake-command/1` members. No wheel speed, pressure, deceleration or "applied" member exists; the check rejects a mutated message carrying one, an undeclared status, or another node identity. `injected-fault` is in the vocabulary and is never emitted |
| No defaults | The node and the reader refuse construction without a validated record. Records with a missing, extra, ill-typed, zero (window) or negative (latency) member are refused |
| Chassis zone §1.5 | Routes only the arbiter's well-formed request, re-stamped with source, route and `receivedNs`, and leaves value and staleness to the node. Refuses other sources with a `route-refused` evidence record. Forwards `motion-evidence` to `vehicle-state` unchanged. Records `aeb-status` and `brake-status` as evidence |
| Forwarding | Only F17 to the U2 `loop-gateway`. A test binds the module to the WP-12 topology (element outputs, F17, its hub delay, and the intra messages) |
| WP-03 reader §1.7 | 0.0 before the first command and for a fresh release; the fresh value; `None` when stale or after `mark_lost`; older and non-conforming commands refused and counted. The offline chain arbiter → chassis zone → node → F17 (one hub step) → reader gives `[0.0, 0.0, 0.0, 1.0, 1.0]` for requests `[0, 0, 1, 1, 0]`: each request reaches the driver one hub step later and is never `None` while fresh |
| Fault hooks §1.6 | None: no decided H4 case touches the node or the chassis zone |

All window, latency and step values in the tests are labelled test values (100 ms, 0 ns, 50 ms). No
protocol value is set.

**Residuals.**
1. **Protocol values.** `stalenessWindowNs` of the node and the reader (AD-06, AD-07) and
   `computeLatencyNs` (AD-30) are required from the frozen AD-27 record, through the FR-028
   projection. None exists yet.
2. **Fault-hook decision (§1.6).** If a brake-path fault is ever admitted, its injection must stay
   outside U5 (FR-028), and `injected-fault` should be evidence-only. DECISION NEEDED.
3. **Wiring.**
   - The hub's F17 delivery and `mark_lost` verdict (WP-10).
   - The U5 unit program that hosts these modules (WP-13, WP-14). The functional arbiter must emit a
     request every decision cycle (FR-041), which the reader's staleness rule assumes.
   - The Phase 8 run command that passes the reader to `ArbitratedDriver` (WP-03 B-4).
4. **V34 and Argus.** The node's statuses and commands are kept as evidence records with simulation
   time. Their emission as Argus role events belongs to the ED-12 extension.
5. **The reader's future-origin case.** An F17 command whose `originNs` is later than the reader's
   time is used as delivered. The hub must deliver only at or after the command's delivery point
   (WP-10).
6. **Status back to the arbiter.** The WP-12 topology carries `brake-status` to the chassis zone only,
   with no acknowledgement to the arbiter. If WP-13 needs one, it is a topology change.

The next step is an independent read-only review of `9e9b15b`, then acceptance and merge. Neither has
happened.

## Finding 3: independent review of findings 1 and 2 (2026-10-24 11:41:26)

**Reviewer and method.**
- An independent, read-only reviewer who did not write this increment.
- Read `574207b`, `9e9b15b` and `862c5eb` against base `7851c47`, and checked them against:
  - thesis FR-033, FR-041, V26 and V34, AD-17 B, AD-14 E2, §J and §K, the `decisions.md` row "WP-04 fault
    status" (283), and `design/wp12-xdl-topology.md`;
  - compat `driver_profile.py` and `live/loop.py` at main `855878a`, and review-wp03 B-3.
- Commands (`/dev/shm/compat-p6-venv/bin/python -I`, rc.1 profiles from a scratch `git archive` export):
  - `tests/test_brake_esc.py`: 42 passed;
  - the whole blueprint suite: 116 passed;
  - `check_topology.py`: exit 0.
- Two in-memory probes: a non-zero simulation epoch, and an out-of-range apply request. Nothing in the
  worktree changed except this entry. No CARLA, no live run, no unit process.

### Verdict: **FAIL: one HIGH issue blocks the merge** (a small repair)

The node, the chassis zone and the vocabulary are sound. The reader's staleness rule does not work
against the time base of its declared caller.

### Confirmed
- **State machine** (brake_esc.py 164–223).
  - Every delivered request gives `received`, then either `rejected` with exactly one reason, or
    `accepted` followed by `forwarded` and one F17 command.
  - Rule order: malformed (including bool, NaN and non-integer stamps), wrong-source (source or route),
    out-of-range, stale (age above the window, or a future origin; the boundary itself is fresh), and
    replayed (sequence ≤ the last accepted).
  - A rejection never advances `last_accepted_sequence`, and a zero request is accepted and forwarded as a
    release.
- **V26.** Only the declared status and command members exist. `check_vocabulary` rejects a wheel-speed
  member, an `applied` member, an `applied` status, or a foreign node. `injected-fault` is never emitted,
  which matches the evidence-only decision of `decisions.md` 283.
- **Forwarding.** The module imports only `dataclasses`, `math` and `typing`, writes nothing to CARLA,
  and emits only F17. A test binds it to the WP-12 element outputs, F17 and its hub delay.
- **No defaults.** Both parameter records are exact-member records. The window is a positive int, the
  latency a non-negative int, and a bool is refused. Both constructors require a validated record.
- **Chassis zone.** It routes only the arbiter's well-formed request and re-stamps source, route and
  `receivedNs`. It refuses others with `route-refused`, forwards motion evidence unchanged, and records
  status. It has no authority.
- **Reader against B-3.** It returns 0.0 before the first command and for a fresh release, the fresh value
  otherwise, and `None` after `mark_lost` or when the newest command is older than the window. Each of
  these holds *in one time base*; see HIGH-1.

### Issues

**HIGH-1: the reader compares an episode-relative time with an absolute command origin, so staleness
never fires in the real chain.** This blocks the merge.
- Where: brake_esc.py 260–269; compat `live/loop.py` 83 and 114–115 at `855878a`.
- `ArbitratedDriver` calls `brake_request(sim_s)` with the loop's `sim_s`, which is
  `(frame_ns − episode_ns) / 1e9`: seconds since the episode's first ticked frame.
- The node stamps F17 `originNs` in "integer nanoseconds as in the compat items" (finding 1 §1.1). Those
  are `seconds_to_ns(elapsed_seconds)`, the absolute CARLA world clock, which is far from 0 at episode
  start on a running server.
- The reader computes `age = round(sim_s·1e9) − originNs`, which is then hugely negative, and it has no
  `age < 0` guard.
- Probe, with the world at 1000 s at the episode's first frame: a command forwarded at 1000.05 s is
  returned as `1.0` at relative 0.1 s, **and still `1.0` at relative 10.1 s, when it is 10 s old**.
- The only time-based path to WP-03's invalid-request behaviour (throttle 0, hold the last brake) is
  therefore dead. Examples:
  - after a release, a frozen or silent U5 (the CC-1 freeze) leaves the reader returning a stale 0.0
    indefinitely, so the driver keeps accelerating;
  - a stale brake value is held as if it were fresh.
- The offline chain test (test_brake_esc.py 221–237) starts both clocks at 0, which hides the mismatch.
- Repair:
  - declare one time base on F17 and in the reader: episode-relative ns as WP-03 uses, or absolute with
    the reader given the episode origin;
  - treat `age < 0` as stale (`None`) or as not yet deliverable, not as fresh, which also covers R-5;
  - add the chain test with a non-zero epoch.

**MEDIUM-1: a rejected out-of-range *apply* leaves the release in force. The WP-03 clamp is not a second
line on this path.** Not blocking.
- Where: brake_esc.py 184–185 and 212–214; finding 1 §1.3.
- The node rejects instead of clamping, which is defensible for a status node: the `rejected` status is
  in the FR-033 vocabulary. But a rejected request forwards nothing, so the last forwarded command stands.
- Finding 1 records only the safe direction ("a rejected release holds the brake").
- Probe: a 0.0 request, then `1.0000001` (a float overshoot) every cycle. Every apply is rejected
  `out-of-range`, and the reader returns 0.0 for one window and then `None`. The vehicle therefore keeps
  the driver throttle for a window, then coasts with brake 0, and it never brakes.
- WP-03 clamps values above 1, but no value above 1 ever reaches it through F17. Finding 1's "WP-03
  still clamps a value above 1, as a second line" is therefore not true for the brake path. The two rules
  are consistent only if the arbiter never emits a value above 1.
- FR-041 will count such cycles as missing acceptances, so the offline measure sees the failure. The
  physical outcome is still a missed brake.
- Repair or record:
  - WP-13 or WP-14 make the functional arbiter's output contract [0, 1] (clamp at the source, with a
    recorded flag), and the node's rejection becomes a detector;
  - correct the "second line" sentence;
  - state the asymmetric hold in the residuals: a rejected apply keeps a release, and a rejected release
    keeps a brake.
- The rejected-release-holds-brake rule is conservative in the AD-04 family, which has no following
  traffic. The braking it holds is attributed to no arbiter request, so the oracle needs the node's
  rejections as evidence to explain it (V34).

**LOW-1: R-5, delivery timing.**
- The future-origin case is better closed in the reader than delegated to the hub (part of the HIGH-1
  repair).
- The end-to-end timing should be stated once for AD-30 and AD-07:
  - the arbiter's request at step *k* is accepted at *k* (intra-unit);
  - F17 reaches the reader at *k + 1* (hub delay);
  - WP-03 decides with the previous frame (its R-5);
  - the command is applied over the next step.

  So a request first acts about two simulator steps after it is decided, plus `computeLatencyNs`. The
  chain test shows only the hub step.

**LOW-2: no first command within a startup bound is not detected.** As B-3 requires, the reader returns
0.0 indefinitely before the first command. If U5 never produces F17 (for example, it is frozen or never
started), the driver approaches with no AEB and no invalid signal. Because FR-041 requires a request on
every cycle, WP-10 could declare a startup deadline for the first F17 and call `mark_lost` when it
passes. Record it for WP-10.

**LOW-3: residual 2 is now decided.** `decisions.md` 283 (11:38) makes `injected-fault` evidence-only and
places any brake-path fault at the U2 hub relay. Residual 2 should cite that decision instead of
"DECISION NEEDED".

### Residuals 1 to 6
- Residuals 1, 3, 4 and 6 are accurate.
- Residual 2 is superseded (LOW-3). Residual 5 is incomplete (LOW-1).
- Missing: the time-base contract of HIGH-1 and the asymmetric hold of MEDIUM-1.

### Recommendation
- Repair HIGH-1 with a non-zero-epoch chain test and an `age < 0` rule.
- Record MEDIUM-1: the arbiter range contract for WP-13/WP-14, the corrected "second line" sentence and
  the asymmetric-hold residual.
- Record LOW-1 to LOW-3.
- Then a focused re-review, followed by acceptance and merge.

## Finding 4: disposition of finding 3 (2026-10-24 11:43:33; recorded before any change)

This disposition is the coordinator's, under the author's delegation of 2026-10-24, and is flagged for the
author's review.

| Item | Disposition | Planned change |
| --- | --- | --- |
| HIGH-1 | Repair | F17 keeps the absolute CARLA world simulation clock (`originNs`, as the compat items). `BrakeCommandReader` requires the episode origin `episodeOriginNs` (the world time of the episode's first frame, set by the U2 loop); with no origin it refuses to construct or serve. It converts WP-03's episode-relative `sim_s` to absolute before the age. A negative age (a future origin) returns `None`, not deliverable, so WP-03 cuts throttle and holds the brake. New tests: a chain with a non-zero epoch (a world at 1000 s), and a stale case that fails before the fix |
| MEDIUM-1 | Record | Correct finding 1's "WP-03 still clamps a value above 1, as a second line" (it is not a second line on the F17 path). Record as a WP-13/WP-14 obligation the functional arbiter's output contract: [0, 1], clamped at the source with a recorded flag. Add the two-way hold to the residuals: a rejected apply keeps a release, and a rejected release keeps a brake. The node's rejections are evidence for the oracle (V34) |
| LOW-1 | Repair and record | The reader-side future-origin guard (HIGH-1). State the end-to-end delay: about two simulator steps from the arbiter's decision to actuation, plus `computeLatencyNs` |
| LOW-2 | Record | A WP-10 item: a start-up deadline for the first F17 command, after which the hub calls `mark_lost` |
| LOW-3 | Record | Residual 2 is decided: `decisions.md` "WP-04 fault status" (`injected-fault` is evidence-only; any brake-path fault is injected at the U2 hub relay) |

## Finding 5: result of the finding 4 repairs (2026-10-24 11:45:31; repair commit `f19407f`)

**Commands.** `tests/test_brake_esc.py`: 46 passed (42 before). Whole blueprint suite with
`XVERSE_PLATFORM_PROFILES`: 120 passed. `check_topology.py`: exit 0. Host load 5.0. No live run, no CARLA;
the loop10 worktrees and the pinned live environment were not touched.

**HIGH-1, repaired.**
- **One time base.** Every `*Ns` stamp of the node, the chassis zone and F17 is the absolute CARLA world
  simulation clock in integer nanoseconds (as the compat items). WP-03's `sim_s` is episode-relative.
- **The reader.** `BrakeCommandReader(params, *, episode_origin_ns)` requires the world time of the
  episode's first ticked frame, set by the U2 loop. It has no default and refuses `None`, non-integer,
  negative or bool values. The age is `episode_origin_ns + round(sim_s·1e9) − originNs`.
- **Future origin.** A negative age returns `None`: not deliverable, so WP-03 cuts throttle and holds
  the brake.
- **Tests.**
  - Construction is refused without an origin.
  - With the world at 1000 s, a command 50 ms old gives 1.0 and a command 10 s old gives `None`. The
    pre-fix module (`862c5eb`), run in scratch, **returned `1.0` for the 10 s-old command**, so this test
    fails before the fix.
  - A future origin gives `None`.
  - The chain at a 1000 s epoch still gives `[0.0, 0.0, 0.0, 1.0, 1.0]`, and after U5 falls silent the
    reader returns `None` one window later, not a stale 0.0.
- **WP-10 obligation.** The U2 loop must know the episode origin before the first driver call, and
  construct the reader with it.

**MEDIUM-1, recorded.**
- Finding 1's "second line" sentence is corrected in place, with a marker and the original text. No
  value above 1 reaches WP-03 through F17.
- **WP-13/WP-14 obligation.** The functional arbiter's output contract is a value in [0, 1], clamped at
  the source with a recorded flag. The node's `out-of-range` rejection is then a detector, not a path.
- **Two-way hold.** A rejected apply keeps an earlier release in force, and a rejected release keeps an
  earlier brake. The node's `rejected` statuses (reason, sequence, `atNs`) are evidence the oracle needs
  to explain a held brake, or a missed one, that no arbiter request explains (V34).

**LOW-1.**
- The reader-side future-origin guard is in place (HIGH-1).
- **End-to-end delay.** The arbiter's request at simulator step *k* is accepted at *k* (intra-unit). F17
  reaches the reader at *k + 1* (one hub step). WP-03 decides with the previous frame and the command is
  applied over the next step. The request therefore first acts about **two simulator steps** after it
  is decided, plus `computeLatencyNs`. This enters the AD-30 latency declaration and the AD-07 deadline
  table.

**LOW-2, recorded for WP-10.** A start-up deadline for the first F17 command: if none arrives in time,
the hub calls `mark_lost`, so the reader returns `None` instead of 0.0 indefinitely (FR-041 requires a
request every cycle). Its value is a protocol value (AD-07).

**LOW-3.** Residual 2 is decided: `decisions.md` "WP-04 fault status" (11:38) makes `injected-fault`
evidence-only and places any brake-path fault at the U2 hub relay.

**Residuals (replaces finding 2's list).**
1. **Protocol values:** the node's and the reader's `stalenessWindowNs` (AD-06, AD-07), `computeLatencyNs`
   (AD-30) and the first-F17 start-up deadline (AD-07), from the frozen AD-27 record.
2. **Decided:** "WP-04 fault status". There is no hook in Phase 8.
3. **Wiring (WP-10, WP-13, WP-14):**
   - the hub's F17 delivery, `mark_lost`, the start-up deadline, and the episode origin passed to the
     reader before the first driver call;
   - the U5 program, with a request every decision cycle (FR-041);
   - the run command (WP-03 B-4).
4. **Arbiter output contract:** [0, 1] clamped at the source (WP-13/WP-14).
5. **Two-way hold:** a rejected apply keeps a release, and a rejected release keeps a brake. The node's
   rejections are oracle evidence (V34). Their Argus emission belongs to ED-12.
6. **End-to-end delay:** about two simulator steps plus `computeLatencyNs`, declared under AD-30 and
   AD-07.
7. **No acknowledgement to the arbiter.** If WP-13 needs one, it is a topology change.

The next step is a focused re-review of `f19407f`, then acceptance and merge.

## Finding 6: independent re-review of findings 4 and 5 (2026-10-24 11:48:04)

**Reviewer and method.**
- The finding 3 reviewer, read-only. Read `3b645b4`, `f19407f` and `3674c6b` against `583bc72`, with
  compat `live/loop.py` 83–129 at `855878a` for the caller's order.
- Commands:
  - `tests/test_brake_esc.py`: 46 passed;
  - the whole suite with the rc.1 profiles: 120 passed;
  - `check_topology.py`: exit 0.
- One in-memory probe: the conversion at a 600 s episode with a 1000 s world epoch. Nothing in the
  worktree changed except this entry. No CARLA, no live run.

### Verdict: **PASS WITH NOTES. Nothing blocks the merge.**

HIGH-1 is repaired, and MEDIUM-1 and LOW-1 to LOW-3 are recorded as disposed. One wiring point
(MEDIUM-A) must be settled in WP-10 before the reader is used. The merge still awaits acceptance.

### Items of finding 3
- **HIGH-1: closed.**
  - `BrakeCommandReader(params, *, episode_origin_ns)` (brake_esc.py 243) requires an integer,
    non-negative, non-bool origin and has no default.
  - The age is `episode_origin_ns + round(sim_s·1e9) − originNs` (279), and a negative age returns
    `None` (280).
  - Probe at a 600 s episode on a 1000 s world: with `sim_s` computed as `loop.py` 115 does, a command
    50 ms old is served. The window edge (100 ms) is fresh, and the edge plus 1 ns is `None`, so the
    float round trip is exact at this scale.
  - The new tests cover the refused constructions, stale versus fresh at the 1000 s epoch, a future
    origin, and the chain at that epoch (`[0.0, 0.0, 0.0, 1.0, 1.0]`, then `None` one window after U5
    falls silent).
  - Finding 5 records that the pre-fix module returned 1.0 for the 10 s-old command.
- **MEDIUM-1: closed (recorded).**
  - Finding 1's sentence is corrected in place with a marker and the original text (line 76–78).
  - The arbiter's [0, 1] output contract is a WP-13/WP-14 obligation (residual 4).
  - The two-way hold is residual 5, with the node's rejections as V34 oracle evidence.
- **LOW-1: closed.** The future-origin guard is in the reader, and the end-to-end delay (about two
  simulator steps plus `computeLatencyNs`) is residual 6, for AD-30 and AD-07.
- **LOW-2: closed (recorded for WP-10).** The start-up deadline for the first F17, with `mark_lost`, is a
  protocol value (AD-07), in residuals 1 and 3.
- **LOW-3: closed.** Residual 2 cites the "WP-04 fault status" decision.

### New notes (none blocking)
- **MEDIUM-A: the WP-10 obligation "construct the reader with the episode origin before the first driver
  call" cannot be met as stated.**
  - In `LiteVehicleLoop.run` the first `command_source(sim_s, last_motion)` call is at tick 0 (loop.py
    94), *before* the first `link.tick()` (98). `episode_ns` is set only from that first frame (114).
  - `ArbitratedDriver(params, brake_request)` is built before `run()` starts, so the reader must exist
    before the origin is known.
  - The reader does not need the origin until it holds a command: it returns 0.0 before the first one.
    The cleanest fix is therefore a late binding:
    - `set_episode_origin(ns)`, settable once;
    - `__call__` returns `None` if a command is held while the origin is unset (fail-closed);
    - the hub sets the origin from the first frame's `originNs`, which is the loop's `episode_ns`.
  - Alternatively, WP-10 must obtain the world time of the first frame by another declared path before
    the loop starts.
  - Record this in residual 3, or repair it now. It does not block, because nothing wires the reader yet.
- **LOW-A: a future-origin command displaces an older, still-fresh one.**
  - `deliver` replaces `newest` with any newer-sequence command, even one whose `originNs` lies in the
    reader's future. The reader then returns `None` (throttle cut, brake held) until that origin is
    reached, instead of serving the previous fresh value.
  - This is fail-closed, but it perturbs the driver whenever `computeLatencyNs` exceeds the hub delay.
  - Optional: keep the previous command until the new one's origin is reached. Otherwise state in
    residual 6 that the hub delivers F17 only at or after `originNs`.

### Recommendation
Ready for acceptance. Record MEDIUM-A in residual 3 (or adopt the late binding), and decide LOW-A or
state it.

## Finding 7: disposition of finding 6 (2026-10-24 11:52:19; recorded before any change)

This disposition is the coordinator's, under the author's delegation, and is flagged for the author's
review. It applies the new thesis rule `decisions.md` "AD-30 delivery rule" (11:51): episode-dependent
behaviour is keyed to episode-relative time, with the episode origin bound late from the first frame and
no default.

| Item | Disposition | Planned change |
| --- | --- | --- |
| MEDIUM-A | Repair (late binding) | `BrakeCommandReader` no longer takes the origin at construction. The U2 loop binds it once, from the first frame, with `bind_origin(ns)`. A second bind with a different value is refused; the same value is idempotent. While a command is held and the origin is unbound, the reader returns `None`. Before any command it returns 0.0, bound or not (WP-03 B-3). Tests include the compat `LiteVehicleLoop` order: the driver is called at tick 0 with `sim_s` = 0.0, before the first frame (`live/loop.py` 83–115 at `855878a`) |
| LOW-A | Declared | A newer-sequence command whose origin lies in the reader's future displaces an older fresh one, so the reader returns `None` until that origin is reached. This fails closed (throttle cut, brake held). Under the AD-30 delivery rule the hub delivers at the first step boundary at or after `deliverAtNs`, so this arises only if a command is delivered before its origin |

## Finding 8: result of the finding 7 dispositions (2026-10-24 11:53:53; commit `2bd7683`)

**Commands.** `tests/test_brake_esc.py`: 48 passed. Whole suite with the rc.1 profiles: 122 passed.
`check_topology.py`: exit 0. No live run, no CARLA; the loop10 worktrees and the pinned live environment
were not touched.

**MEDIUM-A, repaired (late binding, `decisions.md` "AD-30 delivery rule").**
- `BrakeCommandReader(params)` no longer takes the origin.
- `bind_origin(ns)` binds it once. It refuses a non-integer, negative or bool value; re-binding the same
  value is idempotent, and a different value is refused.
- `__call__` returns:
  - 0.0 before any command, bound or not (B-3);
  - `None` when a command is held and the origin is unbound;
  - otherwise, the finding 5 age rule (stale or a future origin gives `None`).
- **Tests.**
  - The bind rules.
  - An unbound origin gives 0.0 without a command, `None` with one, and the value once bound.
  - The compat `LiteVehicleLoop` order (`live/loop.py` 83–115 at `855878a`): the driver is called at tick
    0 with `sim_s` 0.0 before the first frame, which then binds the origin. The driver sees
    `[0.0, 0.0, 0.0, 1.0, 1.0, 1.0]` for requests `[0, 0, 1, 1, 1, 0]` at a 1000 s world epoch. The
    frame-*k* request reaches the driver at tick *k + 1* (one hub step) and is applied over the next step.
  - The finding 5 tests now bind the origin explicitly.
- **WP-10 obligation (replaces "construct the reader with the origin before the first driver call").**
  The U2 loop calls `bind_origin(episode_ns)` when the first frame arrives (for example through
  `on_motion` or right after `episode_ns` is set).

**LOW-A, declared.** A newer-sequence command whose origin lies in the reader's future displaces an older
fresh one, and the reader returns `None` until that origin is reached. This fails closed (throttle cut,
brake held). Under the AD-30 delivery rule the hub delivers at the first step boundary at or after
`deliverAtNs`, so this arises only if a command is delivered before its origin.

**Residuals.** Finding 5's list stands, with residual 3's origin item replaced by the `bind_origin`
obligation above, and with the AD-30 delivery rule as the latency rounding (residual 6).

The next step is acceptance and a merge. Neither has happened.

## Finding 9: independent re-review of findings 7 and 8 (2026-10-24 11:58:43)

**Reviewer and method.**
- The finding 3 and 6 reviewer, read-only. Read `264695d`, `2bd7683` and `d536c7e` against `2dad590`, with
  the thesis `decisions.md` row "AD-30 delivery rule" (284), and compat `live/loop.py` 83–126 at `855878a`.
- Commands:
  - `tests/test_brake_esc.py`: 48 passed;
  - the whole suite with the rc.1 profiles: 122 passed;
  - `check_topology.py`: exit 0.
- Nothing in the worktree changed except this entry. No CARLA, no live run.

### Verdict: **PASS WITH NOTES. Nothing blocks the merge.**

### Items
- **`bind_origin` (brake_esc.py 268).** It refuses a non-integer, negative or bool value. Re-binding the
  same value is idempotent, and a different value is refused (`test_origin_binds_once_…`).
- **0.0 before any command, bound or not** (288). This holds B-3.
- **`None` while a command is held and the origin is unbound** (289), the fail-closed rule. The value is
  served once the origin is bound (`test_unbound_origin_serves_zero_…`).
- **`LiteVehicleLoop` order at a 1000 s epoch** (`test_lite_vehicle_loop_order_driver_before_first_frame`).
  It reproduces `loop.py`:
  - the driver is called at tick 0 with `sim_s` 0.0 before the first frame;
  - the first frame sets `episode_ns`, and the reader is bound from it;
  - the next `sim_s` is `(frame_ns − episode_ns) / 1e9`.

  The driver sees `[0.0, 0.0, 0.0, 1.0, 1.0, 1.0]` for `[0, 0, 1, 1, 1, 0]`, so the frame-*k* request
  arrives at tick *k + 1*. That matches the hub step.
- **LOW-A, declared.** A future-origin command displaces a fresh one, and the reader fails closed. Under
  the AD-30 delivery rule ("the first simulator-step boundary at or after its `deliverAtNs`") this arises
  only if a command is delivered early, which is consistent with the thesis row.
- **Consistency with the AD-30 delivery rule.** Staleness is keyed to episode-relative time, the origin is
  bound late from the first frame with no default, and the absolute stamps stay on F17. The rule is
  applied as written.

### New note (LOW, not blocking)
- **LOW-B: bind from `episode_ns`, not from the first motion item.**
  - Finding 8 offers `on_motion` as one way to bind. In `loop.py`, `episode_ns` is the first frame's
    motion `originNs` if a motion item is present, and otherwise the largest other item origin (106,
    114). `on_motion` fires only on a frame that carries motion (123–126).
  - If the episode's first frame has no motion item, binding to the first `motion["originNs"]` would bind
    a later instant than `episode_ns`. Every age would then be overestimated by that offset, which leads to
    early staleness. That fails closed, but it is wrong.
  - A safe derivation inside `on_motion(motion, sim_s)` is `motion["originNs"] − round(sim_s·1e9)`, which
    equals `episode_ns` exactly.
  - Record that in the WP-10 obligation, or bind right after `episode_ns` is set.

### Recommendation
Ready for acceptance and merge. Record LOW-B in the WP-10 obligation.
