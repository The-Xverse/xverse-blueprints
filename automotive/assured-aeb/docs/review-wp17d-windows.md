# WP-17d review log: offline evidence windows and deadline tables

Candidate: `candidate/phase8-wp17d-20261024`, worktree
`/home/jefferson/xverse-blueprints-worktrees/phase8-wp17d-20261024`.
Dependency: WP-17a candidate `d2baa8b350ddfc3d353f98ea9d9495384e195d3a`, **unaccepted**. Branching from it
is dependency isolation, not acceptance or delivery. No runtime unit, simulator or factory run is started.

## Finding 1: detailed proposed design before implementation (Codex, 2026-10-24)

Inputs: thesis `specs/002-assured-aeb/design/wp17-support.md`, O-5 (FR-038/V31); the decided AD-06/AD-07
option B in `review/decision-proposals-20261024d.md` §§4–5; AD-05 §2 and runtime WP-13's conservative
range/speed substitution. Thesis freshness fetched successfully: HEAD/upstream `d97fdd1`; canonical note
blob `ba244ddb7df388386455524ab7667d4a1e86d5a3`, unchanged from the completely read context.

**Status: PROPOSED; semantic/math questions below are pending coordinator disposition. No code yet.**
Sol at high reasoning is recommended for the exact arithmetic and cross-role review; this is a task judgment,
not a measured model comparison. Every scientific value remains a Protocol entry or an unresolved decision.

### Interface, identifiers and units

Proposed module: `assured_aeb/window_tables.py`, offline only. API:
`generate(protocol: Protocol) -> dict`. It accepts an admitted WP-17a Protocol object and reads every value via
`Protocol.entry(identifier)`, preserving its identifier, unit, source, status and category in the output.
No private record access, fallback value or runtime projection is used. There is no separate configuration
language: the reference map is one policy entry in the same digest-bound protocol record.

The proposed `timing.tableBindings` entry has unit `identifier-map`, category `policy`, and contains only named
bindings/identities, not scientific numeric values:

- `envelope`: bindings for `worstGap`, `maxClosingSpeed`, `distanceUncertainty`, `speedUncertainty`,
  `deceleration`, `margin`, `endToEnd`, `reserveFraction`;
- `windows`: one or more `{itemId, period, latency, slack, freshness, validity, marginFraction, maxClosingSpeed,
  margin}` bindings. Each scalar member is a Protocol identifier; `itemId` is a unique table identity;
- `path`: ordered `{stageId, from, to, latency}` bindings for the nominal camera → front zone → ADAS/AD →
  Vehicle Control → chassis zone → brake/ESC path. Per-unit computation can appear as a self-step; transport steps
  must follow the declared route, and the generator checks continuity and coverage. No stage latency is inferred;
- `deadlines`: bindings for `decisionCycle`, `monitor`, `transition`, `confirmation`, `fallback`, `mrcRequest`,
  `retainedValidity`;
- `semantics`: references to Protocol entries declaring the transition and confirmation time origins/scopes.
  The generator must not infer an interpretation from a numerical value.

Proposed conventional identifiers (the map fixes the actual frozen IDs):

| Quantity | Example bound ID | Required unit |
| --- | --- | --- |
| Worst declared measured gap | `timing.envelope.worstGapM` | `m` |
| ODD maximum closing speed | `timing.envelope.maxClosingSpeedMps` | `m/s` |
| Conservative range/speed uncertainty | `aeb.distanceUncertaintyM`, `aeb.speedUncertaintyMps` | `m`, `m/s` |
| Assumed available braking deceleration | `aeb.decelerationMps2` | `m/s^2` |
| Runtime margin | `aeb.marginM` | `m` |
| Window fraction / reserve fraction | `timing.camera.validityFraction`, `timing.reserveFraction` | `1` |
| Period / declared latency / slack | `timing.camera.periodNs`, `.latencyNs`, `.slackNs` | `ns` |
| Declared freshness / validity | `timing.camera.freshnessNs`, `.validityNs` | `ns` |
| End-to-end, monitor and recovery response deadlines | `timing.endToEndNs`, `timing.monitorNs`, etc. | `ns` |
| Retained-path evidence validity | `timing.retainedValidityNs` | `ns` |

All nanosecond quantities are exact integers; sampling period and decision cycle are positive, latencies and slack
are non-negative. Fractions are dimensionless within [0,1]. Deceleration must be positive; margin/uncertainties
and declared worst gap/speed are non-negative. Deadline/window positivity and zero-budget treatment are explicit
review questions below rather than silently added policy. Oracle/evaluation outputs and fault parameters are not
inputs. Scenario/ODD bounds are permitted only as offline declared inputs, never exported wholesale to runtime.

### Exact arithmetic and rounding

Use `fractions.Fraction` for every intermediate and comparison. Unit conversion is exactly 10^9 ns/s; the
coefficient 2 in constant-deceleration kinematics is the equation's mathematical coefficient, not a protocol value.
No binary floating-point arithmetic or arbitrary decimal-context precision is used in derivation.

Proposed number conversion: integers remain exact; explicit decimal strings parse through Decimal then Fraction;
finite Protocol floats parse through `Decimal(str(value))` then Fraction, with that canonical stored-decimal
interpretation recorded. **Original JSON decimal token precision is already lost by WP-17a's JSON float parsing;
this conversion policy needs the disposition below before code.** Booleans, non-finite values and malformed decimals
are refused. Every exact result is serialized as numerator/denominator strings, with an explicit integral rounding
field when applicable. Lower bounds round upward; upper bounds round downward. Equality is permitted by ≤/≥.

### Derived rows and checks

Each output row contains `id`, `rule`, source references, input IDs, the complete copied input entries, units,
exact mathematical result, rounded nanosecond bound if finite, declared value, a typed relation/check and verdict.
No value is silently changed to repair a failed check. The table includes Protocol metadata (kind, record digest,
engineering-only status), generator/source identity and canonical table digest. All this remains offline.

1. **Freshness:** `F_min_ns = P_ns + L_ns + S_ns`; require declared `F_ns >= F_min_ns` for each item.
2. **Validity growth:** with fraction f, margin m and the declared physical ODD closing-speed bound v_ODD,
   `growth_m = v_ODD * V_ns / 10^9`; require `growth_m <= f*m`. For positive v_ODD,
   `V_max_ns = floor(10^9*f*m/v_ODD)`. For v_ODD=0 and non-negative f*m there is no finite bound from this
   rule: report `unbounded` and check the declared finite window directly; never serialize Infinity or select one.
3. **End-to-end envelope boundary:** use the same conservative substitutions as runtime WP-13,
   `d_c = d_worst - delta_d`, `v_c = max(0, v_worst + delta_v)`, and
   `B_m = d_c - m - v_c^2/(2*a_b)`.
   For v_c>0 the available-delay boundary is `E_max_ns = floor(10^9 * B_m/v_c)`.
   Require the explicitly declared end-to-end deadline `E_ns <= E_max_ns`.
   This uses the margin-preserving side `d_c - v_c*t - v_c^2/(2*a_b) >= m`; the AD-05 braking-trigger
   inequality has the opposite direction. The boundary is shared, but this interpretation must be approved below.
   Negative B_m means no non-negative delay satisfies that side (`no-solution`). B_m=0 means zero remaining
   budget (`zero-budget`), not a guessed minimal deadline. For v_c=0, non-negative B_m supplies no finite upper
   bound (`unbounded`); negative B_m is still `no-solution`. Negative closing bounds or non-positive deceleration
   are input refusals. No-solution and zero-budget treatment are separately reported, never clamped upward.
4. **Reserve/path:** derive `R_ns = ceil(reserveFraction * E_ns)` from the declared E_ns; require
   `sum(declared_stage_latencies_ns) <= E_ns - R_ns`. Report every stage, the sum, reserve and remaining budget.
   The integer reserve is based on the actual declared integer E_ns, not an unrounded physical boundary.
5. **Monitor:** require declared monitor deadline ≤ the declared decision-cycle length.
6. **Transition/confirmation:** proposed meaning is total transition deadline T from request through confirmation,
   with confirmation deadline C from selector application through confirmation. Require `C <= T <= V_retained`.
   Runtime completion must obey the earlier total/confirmation expiration; do **not** impose `T+C <= V_retained`
   when C is already included in T. The table does not prove that an arbitrary late selector application leaves
   enough confirmation time. It records the runtime composition obligation, which WP-14/WP-15 must verify.
   If the coordinator instead defines T as a pre-confirmation phase, the necessary check is `T+C <= V_retained`.
   The generator may support only an explicitly declared, reviewed scope; there is no implicit default.
7. **Fallback / MRC request:** from loss detection to the corresponding request emission, each declared deadline
   must be ≤ retained-path validity. This checks request deadlines only, never external MRC execution/effectiveness.

A failed input or inequality refuses an accepted table and retains a structured offline diagnostic assessment;
no failed result can be mistaken for a valid frozen table. A report is not protocol acceptance or live readiness.

### Questions requiring disposition before implementation

- **D17d-1, inequality semantics:** AD-05's `residual <= margin` is a brake-needed predicate. Taken literally,
  increasing delay still satisfies it, so it yields no finite *upper* acceptance deadline. Confirm that AD-07's
  method means the shared boundary with the margin-preserving `>=` side for available delay, as proposed above.
- **D17d-2, transition scope:** confirm total request-to-confirmed T with post-selector C and earlier-expiration
  enforcement, or separately allocated pre-confirmation T plus C. Existing AD-07 text does not distinguish them.
- **D17d-3, exact input semantics:** choose canonical stored-decimal interpretation for finite Protocol floats
  (explicitly reported), or require integer/decimal-string physical inputs. Recovering original numeric-token
  precision would need a reviewed WP-17a API change; this worker must not read its private record or silently claim it.
- **D17d-4, degeneracy:** confirm explicit unbounded status for zero speed when the static inequality holds, no-solution
  failure for a negative available budget, and refusal of zero budget for a positive declared E2E deadline. No deadline
  is invented for a degenerate case; other finite declared checks still apply where no physical upper bound exists.
- **D17d-5, uncertainty allocation:** proposed end-to-end bound uses the existing runtime conservative delta_d/delta_v;
  validity growth uses the declared physical ODD maximum closing speed directly, as AD-06 states. If that ODD entry is
  instead an uncertain measured maximum, the protocol must identify the conservative growth bound explicitly rather
  than the generator adding uncertainty a second time.

### Planned verification, after the host slot is released

Synthetic admitted characterisation Protocol records only, every value labelled TEST-ONLY. Cases cover exact lower/
upper equality, fractional-ns floor/ceil, each wrong unit/type/status/missing ID, reserve/path overrun, too-short freshness,
excess validity growth, monitor overrun, both deadline scopes or refusal of an unsupported scope, zero speed,
no-solution/zero budget and non-positive deceleration. A reference test rearranges the inequality independently with
Fractions. Instrument Protocol.entry to prove identifier-only reads; assert the report contains every consumed ID,
rule/value/check and original source metadata. Assert no runtime unit imports the generator or receives its full table.

No pytest/heavy work while the platform regression is active. Syntax/tiny standard-library checks are allowed.
Independent review, acceptance, integration and scientific protocol freeze remain later gates.
