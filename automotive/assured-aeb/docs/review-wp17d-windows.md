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

## Finding 2: coordinator dispositions before implementation (2026-10-24)

The parent coordinator confirmed D17d-1 to D17d-5 under the recorded delegation:
- Use the AD-05 boundary and the margin-preserving `>=` side for the available-delay bound; document that `<=`
  remains the braking-trigger predicate. This supplies no new physical-safety claim.
- Transition T is total from request through confirmation; C is from selector application through confirmation.
  Runtime completion obeys the earlier expiry. Check `C <= T <= V_retained`, not an unsupported sum T+C.
- Rational arithmetic operates on `str(decoded finite int/float)` via exact decimal interpretation. Preserve existing
  numeric parameter semantics; do not require scientific values to become strings. Do not claim arbitrary-precision
  preservation of the original JSON numeric token, which WP-17a has already decoded.
- v=0 may be `unbounded-by-this-model`, never Infinity or a selected default. Constant margin violation is
  `no-solution`; a zero finite bound refuses a positive declared E2E deadline. Declared deadlines remain positive
  when the model supplies no physical upper bound.
- Validity growth uses the physical declared ODD maximum closing speed, explicitly distinct from the conservative
  measured v_c used by the envelope.

The implementation will keep integer-nanosecond quantities exact, report upper bounds with floor and reserve/lower
bounds with ceil, and leave every numeric protocol entry unset until supplied by an admitted Protocol. No code or
verification result is accepted by this disposition. WP-17a remains an unaccepted dependency at d2baa8b.

## Finding 3: offline implementation candidate and limited probes (Codex, 2026-10-24)

**Status: IMPLEMENTED CANDIDATE; NOT independently reviewed/accepted, no scientific protocol chosen.**
WP-17a d2baa8b remains the unaccepted dependency. FR-038/V31 O-5 is implemented as an offline generator and
synthetic controls; actual frozen-record generation, independent review and integration remain pending.

`assured_aeb/window_tables.py` supplies `generate(admitted_protocol) -> report` and `TableRefused` with a copied
assessment. It reads the map and every scientific value through public `Protocol.entry(identifier)`. Units,
categories, numeric domains, positive declared deadlines and explicit scope entries are checked. Exact rational
arithmetic uses the adopted canonical stored numeric representation; no scientific value/default is in the module.
Every derived row includes its rule, complete referenced entries and IDs, exact result/unit and comparison, plus
integer bound/reserve rounding where applicable. The detached report carries Protocol/source/table identities;
input failures and failed declared inequalities refuse a valid table without changing any declaration.

The report distinguishes the physical ODD bound used for validity from conservative measured envelope speed;
finite, zero-budget, no-solution and unbounded-by-this-model states are explicit. The AD-05 trigger direction is
recorded separately from the available-delay inequality. Total transition includes confirmation; the output records
its earlier-expiry runtime obligation, not T+C. Fallback/MRC rows stop at request emission.

The API is intentionally offline; no runtime module imports it and no runtime projection is changed. Example
consumer action after Protocol admission is `json.dumps(generate(protocol), sort_keys=True, allow_nan=False)`.
This does not add an alternate admission path, run a simulator or freeze/approve the supplied protocol.
Route validation checks abstract continuity/coverage and explicit latency declarations only: proving that the declared
stage latencies include all physical/processing contributions remains a protocol/experiment review obligation.
Runtime execution, deadline enforcement, clock synchronization and physical fitness are not established here.

`tests/test_window_tables.py` uses genuine digest/chronology-bound characterisation admission, with every fixture
value/provenance labelled TEST-ONLY. Seventeen stdlib test methods cover complete by-ID provenance and deterministic
report digests, independent fraction reference, equality, fractional-ns floor/ceil, every rule's failed comparison,
strict input units/status/types/categories/identifiers, route and scope checks, explicit zero-speed/no-solution/zero
budget cases and runtime-import boundaries. These fixture values are not protocol recommendations.

Actual checks while the parent reserved the heavy verification slot:
- AST parsed the two new Python files; `git diff --check` passed.
- Eight selected tiny stdlib controls passed (two groups of four, 0.028 s and 0.035 s): complete report/provenance,
  fractional bounds/reserve rounding, negative-budget zero/positive speed, included confirmation/earlier expiry,
  simultaneous equal boundaries, independent fraction reference/trigger direction, separated speed meanings and
  all nine failed-inequality diagnostics. No pytest/NumPy/torch/ORT import occurred.
- The other test methods and full pytest suite have **not** run. These are limited probes, not a suite pass.

Deferred exact command, from this worktree's `automotive/assured-aeb`, when the coordinator schedules it:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  /dev/shm/compat-p6-venv/bin/python -I -B -m pytest -q -p no:cacheprovider tests/test_window_tables.py --tb=short
```

Then run the assembled blueprint suite after reconciling the accepted Protocol dependency, review both API and
report formulas independently, and exercise a genuinely frozen/admitted author record only when authorized.
No acceptance, merge, protocol freeze, principal run or factory action is included in this candidate.

## Finding 4: independent read-only review, CHANGES REQUESTED (2026-10-24)

Reviewed exact candidate `a417541b2a2b942d5a24f9ced942517e156f6b95`, findings 1–3, accepted thesis
`decisions.md` §“WP-17d derivation semantics”, O-5 and the full generator/tests plus its public Protocol dependency.
The reviewer did not author this implementation and makes **no source/test repair** in this pass. Thesis upstream
fetch succeeded at HEAD/upstream `d97fdd1`; the canonical working-note blob remains `ba244ddb`, with no incoming
note change. Sol at high reasoning is appropriate for the next scope-preserving formula/report repair and review;
no model switch or measured comparative result is claimed.

### R17d-1, MEDIUM: the explicit completion obligation omits retained-evidence expiry

`window_tables.py:239` emits:
`confirm by min(requestTime + totalTransitionDeadline, selectorTime + confirmationDeadline)`.
The accepted disposition explicitly subjects **both** clocks to retained-evidence validity as well. Checking
`C <= T <= V_retained` does not cover evidence already aged at request; nor does it supply the evidence's absolute
expiry. The table correctly defers runtime enforcement, but the explicit rule handed to that enforcement is
incomplete. The transition-row text also omits the evidence-expiry intersection.

Concrete independently reproduced timeline, all **TEST-ONLY integer ns**: retained evidence originates at 0 with
validity 200; request at 150; selector at 170; total T=100; confirmation C=40. The generated table is valid after
setting the other recovery deadlines to consistent TEST-ONLY values. A completion at 205 satisfies its emitted
`min(150+100,170+40)=210` rule but exceeds retained-evidence expiry 200. This counterexample changes no scientific
parameter and does not claim the runtime currently accepts such a completion.

**Required disposition before repair:** preserve the accepted clock definitions and table inequalities; make the
explicit runtime obligation the minimum of total-transition expiry, post-selector confirmation expiry and **all
applicable retained-evidence absolute expiries**, including the fact that evidence can predate the request. Do not
invent T+C, a new origin, an evidence age of zero, or a static default deadline. This table lacks event-time inputs,
so it should state that complete composition obligation and require runtime verification, not pretend to compute an
absolute expiry. Add a decisive TEST-ONLY aged-evidence regression of the described contract.

### R17d-2, LOW: the zero-speed check's comparison unit is misreported

In `window_tables.py:198–203`, when conservative speed is zero the envelope row's `value` is null and its declared
row `unit` remains `ns`, but `check.left` is the constant **distance** budget and the check is `budget_m >= 0`.
A genuine zero-speed fixture produces left `94/1` with row unit `ns`; that value represents metres. The acceptance
logic and unbounded/no-solution classification are mathematically correct, but a consumer cannot correctly type the
comparison from the serialized unit. Input units do not make the reported comparison unit unambiguous.

**Required disposition before repair:** explicitly type that comparison as metres (a separately typed check or
constant-condition row is sufficient), while retaining nanoseconds for the finite deadline bound and preserving
null rather than Infinity for an absent time bound. Cover zero-speed unbounded and no-solution reports; no equation,
protocol value or degeneracy policy needs changing.

### Positive checks and carried boundaries

- The conservative-distance/speed substitutions, trigger/budget sign distinction, exact Fraction arithmetic over
  the adopted decoded-number representation, floor upper bounds and ceil reserve are consistent with the accepted
  interpretation. Equality, positive-speed finite/zero/negative budgets and zero-speed constant-bound cases are
  handled without upward clamping or fabricated deadlines. Decimal strings and boolean numeric values are refused.
- AD-06 growth uses its separately declared physical ODD speed directly; envelope uncertainty is not added twice.
  Monitor, transition, included confirmation and fallback/MRC request inequalities match the declared scopes.
  Request-emission checks make no MRC execution claim.
- Genuine Protocol admission/entry access retains record digest, kind, source/status/category/unit identities.
  Unresolved consumed entries, forbidden oracle/fault/metric categories and wrong units refuse the table. Principal
  finality remains the public Protocol dependency's responsibility; that dependency is still unaccepted.
- Abstract route continuity/coverage is checked, but completeness and correctness of latency contributions remain
  an explicit protocol review obligation. The code cannot infer omitted per-unit processing, rounding or hub-delay
  contributions from the declared list, or establish actual topology/physical timing. No full retained-path/runtime
  verification or clock-synchronization robustness is demonstrated. Keep these limits through downstream projection
  and protocol freeze; a valid table is not proof that every real contribution was declared.

**Checks actually performed:** 21 small independent direct assertions using genuine digest/chronology-admitted
Protocol fixtures: four rational envelope/rounding cases, three zero-speed constant cases, the aged-evidence
counterexample, the zero-speed unit mismatch and unit/status/category refusals. Two in-memory Python syntax checks
and `git diff --check` passed. One initial counterexample setup left the fixture's old fallback/MRC deadlines above
the newly shortened retained validity and was correctly refused; its related TEST-ONLY inputs were made consistent
before the successful reproduction, with no source change. No pytest runner, framework import, socket exchange,
full owning suite or scientific record was executed. The coordinator retains repairs/disposition and serialized
owning verification; acceptance/merge/freeze remain outstanding.
