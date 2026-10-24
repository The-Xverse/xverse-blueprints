# WP-14e: U4 deterministic untrusted roles

Candidate `candidate/phase8-wp14e-20261024`, isolated from accepted integration
`12bc7464f7c3103f3beba34c040ac5c4afc2b9d4` (assembled verification pending).
No acceptance/merge, unit entry, model/framework import or live execution is included.

## Finding 1: detailed design before implementation (2026-10-24)

Inputs read: accepted thesis `design/wp14-roles.md` §2/O-5/O-6/14e; AD-10 option B, AD-33, FR-009,
FR-018/FR-035/FR-040, the accepted WP-15 graph/guard/terminal boundaries; integration's typed role/source/binding
contract, ED-12 writer, actual WP-13 fusion output and narrow runtime projection readers. Fresh thesis fetch is
successful at HEAD/upstream `d97fdd1`, no incoming note change, working note blob `ba244ddb` unchanged.
Existing main AGENTS modifications are preserved. Runtime code uses standard library and runtime helpers only.
Sol/high is recommended for this boundary work; no model switch or price/performance measurement is claimed.

### Delegated structural disposition

The coordinator explicitly accepted **record-supplied closed nominal-return/hold-only objective mapping** before
code. No actual objective string or scientific value is selected. Principal admission/projection review requires
exactly one declared token; a separate frozen intact-chain mapping may admit several tokens. Runtime consumes no
arm, runKind, experiment plan, protocol, fault schedule, oracle, foreign configuration or evaluation labels.
Invalid/degradation H3 injections remain at the WP-16 relay, not in this proposer. Neither role can authorize,
actuate, modify the graph or issue a forced response. AD-08 guard authority remains the independent gate/manager
chain; a NOMINAL fusion basis is only an opportunistic proposal condition, not permission.

### Module and parameters

Add `assured_aeb/u4_untrusted.py`, standard library only, containing `U4Policy`, `Delivered`,
`GoalInterpreter` and `DeterministicProposer`. No accepted wire schema, topology or event vocabulary changes.
`U4Policy` reads a selected **14e-only own-U4 projection** using the existing Projection record format. Require
unit `adas-hpc`, exactly these consumed identifiers, with no defaults:

- `goals.objectiveMappings`: nonempty closed list of `{objective, targetConfiguration}`; objective is a unique
  lower-case identifier token, never natural-language text; target is `C_NOMINAL` or explicit null (hold).
- `goals.objectiveFreshnessNs`, `proposer.goalFreshnessNs`, `proposer.configurationFreshnessNs`,
  `proposer.basisFreshnessNs`, `proposer.proposalValidityNs`: positive integer ns. They are record-supplied
  freshness/validity values, still TODO for real execution. No dwell, threshold or recovery guard is invented.

The unit entry (14f) composes the unit's full consumed projection and supplies this selected slice after the
accepted digest/allow-list checks. Selection does not authorize additional entries and must retain the same
protocol identity. Runtime does not import the offline projection builder or Protocol. Both roles additionally
require an explicit admitted identity prefix and positive engineering maximum accepted-message count. This count
bounds identity retention and is an engineering resource limit, not an experimental timing or scientific value.

`Delivered(payload, producer, message_id)` explicitly separates payload self-source, separately attested received
producer and actual message ID. Bindings are supplied from the admitted endpoint projection, not inferred from the
payload: objective-source→goal-interpreter, goal-interpreter→proposer, configuration-manager→proposer and
fusion-risk-aeb→proposer. The productive proposal-basis wire alias remains the actual `assured-aeb.adas-cycle/1`.
The role-specific basis consumer checks exact current top-level owner members and every field it consumes; it does
not claim to repeat all fusion/risk/physical validation.

### Goal interpreter

`step(now_ns, step, objectives=()) -> goal-model | None`, at most one accepted objective per step. More than one
is an ambiguous batch: reject all with records and preserve the prior accepted goal. Known token maps to its
record target; unknown, malformed, unauthorized, future, stale, expired, replayed or redefined-ID objectives produce
no new goal. No rejected objective replaces the previous accepted goal or appears in a subsequent proposal.

Consume the existing exact objective schema and source binding. Sequence must increase, origin must not decrease,
and origin/expiry must bracket now (equality at expiry is allowed). Also apply declared objective freshness.
Reject reused accepted message/objective IDs and refuse beyond the supplied engineering identity bound. Construct
exact existing goal-model with source `goal-interpreter`, generated stable unique goalId, original objectiveId,
`basisRefs=[actual objective message ID]`, and closed constraints:
`{targetConfiguration, validUntilNs, objectiveSha256}`. Goal lifetime never extends the source objective. The
constraint schema is a role-specific restriction of the existing `constraints` object, not a wire envelope change.
ID prefix/counters are engineering identities, not protocol values; no random or host-time identity is used.

Every rejected objective emits existing ED-12 `rejection` owned by goal-interpreter, using digest/actual source
reference when canonical bytes exist, safe binding IDs only, and a fixed reason code. Malformed noncanonical data
has no invented payload digest: record the digest of a small explicit rejection diagnostic instead, with no source
reference falsely claiming to bind malformed bytes. Accepted goal/real objective bindings/digests appear in the
subsequent `proposal-created`; no new ED-12 kind or false proposal-received event is added.

### Proposer

`step(now_ns, step, goals=(), configurations=(), bases=()) -> proposal | None`. Ingest each stream independently,
with strict type/source/identity/monotonic checks and at most one record per stream per step; ambiguous or bad
updates suppress the cycle's proposal and invalidate that stream's cached input. Without an update, a still-fresh
cached record may be considered. Replayed/older/future/nonfinite records cannot resurrect an old basis or committed
configuration. Each stream retains its last sequence/origin and accepted IDs within the explicit engineering cap.
Simulator step/time must be nonnegative integers and not regress; invalid caller clocks raise before any effect.

Consume typed goal-model/configuration-state through actual endpoint bindings; consume genuine fusion basis with
explicit expected/received/payload producer checks. Goal constraints must be exact and well typed, with nominal or
hold target and original objective expiry/digest; goal has exactly one objective basis reference. Configuration
must be `C_DEGRADED_RADAR`, phase `confirmed`, and committedAtNs <= originNs <= now; an in-progress/provisional,
unknown or terminal state gives no proposal. A nominal configuration needs no return proposal. The basis must be
fresh, state NOMINAL, reason null, and its consumed camera/radar states NOMINAL with empty failure lists. A new
basis can trigger at most one proposal: repeated step calls or a reused sequence do not create retries. A newer
configuration/goal still needs a new basis before another proposal. Gate rejection is never treated as permission.

Emit exact proposal schema/source `proposer`, target only `C_NOMINAL`, current fromConfiguration, actual goal/
configuration/basis message references and objective reference. Expiry is the earliest of now+declared proposal
validity, objective expiry, and each input's origin+declared freshness; never extend source lifetime or emit an
already expired candidate. No `S_MRC_REQUESTED`, degradation, arbitrary placement, authorization or selector output
is possible. Generation does not evaluate AD-08 dwell, monitor admissibility or safety margins.

Emit existing ED-12 **proposal-created** at the proposer, with proposalId, goalId and objectiveId bindings,
actual digested source references and proposal digest. Actual receiver owns proposal-received. An append failure
propagates and yields no returned proposal; the existing shared RoleEvents adapter poisons failed writers. It is
injected once per U4 unit, not opened here. Other proposer refusals/no-proposal reasons are small local decision
records, not falsely labelled gate rejections or new event kinds; 14f may include these in its operational logs.
These records contain reason/IDs/digests, no full productive payloads/pixels and no runtime effect.

### Verification and scope

Add stdlib unittest controls covering genuine typed objective→goal→proposal, actual FusionRiskAeb basis production,
fixed single-token mapping example, multiple-token intact-chain fixture, hold/unknown/conflict/unauthorized/stale/
future/replay/refused identity-cap cases, immutable source copies, validity intersections/boundaries, terminal/
in-progress/nominal suppression, bad/regressing basis/config/goal and caller clocks, no duplicate proposal, ED-12
owner/binding/digest shape and poisoned append failure. Use real RoleEvents with an explicitly TEST-ONLY recording
writer for small deterministic role controls; this tests the adapter boundary, not durable Argus storage. Genuine
Argus storage/integration remains covered by accepted 14a and later unit entry verification. Tests carry TEST-ONLY
values and do not choose real vocabulary or scientific numbers. Add runtime import/authority scans.

Only small stdlib probes, syntax and diff checks run now. Owning suite and independent implementation review are
scheduled by the coordinator. FR-035/V28 is implemented only at role-module level; principal one-token admission,
H3 injection/sets, full unit projection/entry, transport source attestation, independent gate/manager authority and
scientific freeze remain later gates. Inherited platform SADS model integration/execution targets are not completed
by these role modules. No acceptance/merge, AD-27 freeze, principal result or live readiness is claimed.

## Finding 2: first direct controls and lifecycle tightening, before repair (2026-10-24)

Fifteen stdlib direct test methods passed on the first draft, without pytest or frameworks. A subsequent design
cross-check found two missing boundary controls: an objective received partway through its freshness window could
create a goal whose new origin extended that source freshness, and a later contradictory manager record could
reopen proposal generation after terminal receipt. Neither creates direct authority, but both violate the intended
bounded lifetime/terminal graph boundary.

Scope-preserving repair: goal constraint expiry becomes `min(original validUntilNs, objective originNs + declared
objective freshness)`; no source lifetime is renewed by interpretation. A fresh source-validated terminal
configuration latches proposal suppression for the role instance, even if later messages contradict it. No edge out
of terminal or reset API is added. Add decisive aged-objective and post-terminal contradiction tests before repeating
all small direct controls. Also make the genuine fusion fixture obtain its requested sequence from real repeated
producer steps, and replace an unnecessary skipped large-int assertion with an actual refusal check. No scientific
value, target vocabulary, typed schema or authority changes.

Before finalizing the candidate, also make the existing ambiguity boundary explicit for basis references: actual
message IDs used for objective, goal, configuration and fusion basis must be distinct, because the typed proposal's
basisRefs cannot disambiguate two different records sharing an ID. Refuse that candidate rather than deduplicating
away its provenance. Local decision diagnostics bind the admitted instance prefix and consumed-policy digest; they
carry no productive payload. Add the corresponding small collision control.

## Finding 3: role implementation candidate and actual bounded checks (2026-10-24)

Implemented the two untrusted roles and closed own-U4 policy slice in `u4_untrusted.py`; source identities,
existing objective/goal/proposal/configuration schemas and proposal-basis wire alias are preserved. The projection
holds the actual token mappings and all five positive freshness/validity values; no real vocabulary or numeric
protocol value is chosen. Goal lifetime includes original objective freshness, terminal receipt latches suppression,
and actual source-message references must be unambiguous. The gate still owns every AD-08 authorization decision.
No existing source/schema/topology/event file is changed.

Added nineteen deterministic stdlib test methods (with additional refusal subcases) in `test_u4_untrusted.py`.
The positive basis runs actual SmartRadar, FrontZone and FusionRiskAeb producers, including their real sequence
increments; perception inputs and all model-free values are explicit TEST-ONLY fixtures. The real RoleEvents
adapter is shared once by both roles, with a TEST-ONLY recording writer. Its event ownership, bindings, digest-only
references, local actual-prior-event causation and poison-on-append behavior are checked; durable Argus storage is
not re-executed or claimed in these controls. The synthetic principal mapping admits exactly one token, while the
separate intact-chain fixture admits a hold token as well; runtime receives no arm/runKind selector.

**Performed:** all nineteen methods called directly under the stdlib unittest assertion API, two in-memory syntax
checks and `git diff --check`, all passed. The first fifteen-method pass preceded the lifecycle corrections in
finding 2; the final nineteen-method pass includes aged-objective expiry, contradictory post-terminal configuration,
spoofed terminal receipt, explicit engineering identity capacity and actual-message-ID collision refusal. No pytest,
framework inference/training, durable Argus run, CARLA, factory run, download or live action occurred.

The coordinator subsequently reported delivered blueprint main `b8a154571bd3c7529849a3e8e3f89011ba5036d9`, whose
product matches this candidate's `12bc746` base, with **955 owning tests/no skips and eight genuine compiled-plan
digests**. That evidence belongs to the accepted base, not the new 14e delta. Preserve this work and assemble with
that main/delivery record before the coordinator's next owning verification. Independent review, full suite and
acceptance/merge of this increment are still outstanding. Transport source attestation, real run-unique prefixes,
unit-wide projection slicing, actual principal one-token freeze admission and U4 entry composition remain 14f/
WP-16/WP-17 obligations; a selected slice is not proof those steps happened.

Deferred full-suite command, from `automotive/assured-aeb`, only when the coordinator schedules its heavy slot:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 XVERSE_PLATFORM_PROFILES=/tmp/codex-xverse-review-20261024-q93eotxv/xdl/profiles XVERSE_AEB_SENSOR_SITE=/dev/shm/xverse-aeb-sensor-20261024/venv/lib/python3.13/site-packages XVERSE_COMPAT_SENSOR_ENV=/dev/shm/xverse-aeb-sensor-20261024 XVERSE_COMPAT_SRC=/home/jefferson/xverse-compat/src XVERSE_AEB_U4_SITE=/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache/xverse-aeb-inference-20261024/venv/lib/python3.13/site-packages /dev/shm/compat-p6-venv/bin/python -I -B -m pytest tests -q -ra -p no:cacheprovider --tb=short
```

## Finding 4: independent source review, CHANGES REQUESTED (Codex, 2026-10-24)

Reviewed source candidate `947af51ef70fa837d69377264c4335de7c3db753`, its design `329c020` and findings 1–3;
accepted thesis WP-14 O-5/O-6, AD-10/AD-33, typed contracts, productive FusionRiskAeb/SmartRadar/FrontZone forms,
projection/source and ED-12 boundaries. This reviewer did not author 14e and makes **no source or test repair**.
Thesis freshness fetch succeeded, HEAD/upstream remains `d97fdd1`, no incoming note change, canonical working-note
blob `ba244ddb` unchanged from completely read context. Sol/high is recommended for the narrow successor and review;
this adds no approval gate or model-switch claim.

### R14e-1, MEDIUM: repeated calls can exceed the designed per-step output boundary

`u4_untrusted.py:115–121` accepts equal simulator time **and** equal step repeatedly. Neither goal creation at
154–187 nor proposal emission at 258–309 bounds successful outputs per simulator step. The code correctly refuses
reusing an accepted sequence, but a second advancing sequence delivered during a repeated call still creates another
output. The direct counterexamples use actual typed objective/configuration records and genuine producer bases:

- Call the same interpreter twice at TEST-ONLY `now_ns=1000, step=1`, with two distinct valid objective IDs/sequences
  1 and 2. Both calls return distinct goals and the second replaces the first current goal at the same step.
- Start the genuine positive chain at those same time/step values. Call its proposer again at `now_ns=1000, step=1`
  with a new actual FusionRiskAeb basis at sequence 2. Both calls return distinct proposal IDs and create two genuine
  `proposal-created` events with origin 1000. Goal/configuration/objective freshness remains valid throughout.

Finding 1 explicitly specifies at most one accepted objective per step and says repeated step calls do not create
retries; the existing repeat-call test only calls with no new delivery, so it does not test this case. This is a
bounded cadence/ambiguity mismatch, **not** an unauthorized transition or direct actuation bypass: every proposal
still needs the independent gate and manager.

**Disposition needed before repair:** either enforce the stated role-level per-step output/admission boundary with
explicit duplicate-call/taint behavior, or explicitly move that restriction to a proven once-per-step entry contract
and revise this module's advertised guarantee. The former preserves the recorded design. Do not guess a timing
interval, add a scientific default or silently allow a newer same-step objective to supersede an already processed
one. A decisive regression needs two valid advancing records at the same time/step; checking reuse of one sequence
or an empty repeated call is insufficient. Caller-clock rejection/stream watermark behavior must remain explicit.

### R14e-2, MEDIUM: ambiguous objective rejections lose actual causal references

`GoalInterpreter.step` at 162–164 rejects a multi-objective batch by calling `_reject` without any incoming record.
`_reject` consequently emits one diagnostic digest with `bindings={}` and `sourceRefs=[]`, although the batch can
contain two genuine finite typed Delivered objectives with distinct actual message IDs and objective IDs.
The independent probe confirms exactly that empty-reference event and no goal/current state effect.

This preserves rejection but fails the design's "reject all with records" / actual objective reference commitment:
o retained rejection reference identifies which two real objective messages formed the ambiguous set. The fixed
reason `objective-batch-ambiguous` and a digest of `{role,reason}` do not bind the actual batch. This prevents the
promised causal join for those H3 objective cases. The noncanonical-payload diagnostic fallback remains appropriate
for genuinely noncanonical bytes and should not be used to discard known canonical message references.

**Disposition needed before repair:** retain actual message IDs/digests for every individually canonical delivered
member of the rejected ambiguous batch, either as one bounded batch rejection with all actual references or separate
per-member rejection events with the existing objectiveId binding. Preserve prior accepted goal/no configuration
effect, exact event ownership and poisoned-writer semantics; do not label proposer creation as receipt, invent
references for noncanonical data, or copy full objective/productive payloads into ED-12. The engineering serialization
bound must remain explicit; a fixture should verify both canonical members plus mixed malformed members.

### Positive checks, limits and exact verification performed

The reviewed code preserves record-supplied objective tokens and nominal-return/hold-only targets, exact own-U4
projection membership/no defaults, no arm/runKind/oracle/schedule input and no model/framework import. Expected
binding, received producer and payload source are distinct. Existing typed schemas and productive WP-04 bytes are
unchanged; neither role creates an authorization, forced command, selector or brake request. Independent gate/AD-08
authority is not duplicated. Genuine Fusion/SmartRadar/FrontZone outputs are usable; the test perception object is
explicitly synthetic, not claimed genuine ORT execution. Actual vocabulary, principal one-token admission, transport
attestation, unit-wide projection slicing and run-unique prefixes remain honest downstream obligations.

Aged objective freshness is intersected into goal lifetime; proposal expiry intersects its objective and declared
input freshness. Bad/replayed/stale stream updates clear that stream's cache, and later accepted terminal receipt
latches proposal suppression across contradictory manager updates. The source-ID collision guard refuses ambiguous
current references. Valid proposal-created events bind the actual goal/configuration/basis/objective digests and use
the actual shared RoleEvents adapter; local causation remains local and failed appends poison it. These are module
checks, not proof of the later gate/manager guard, actual physical timing or durable Argus integration.

**Actual checks:** three independent tiny counterexample probes above reproduced both findings (separate same-step
goal and proposal probes, plus ambiguous-reference probe). Five exact existing stdlib test methods were called
directly and passed: `test_genuine_typed_chain_has_only_nominal_candidate_and_actual_reference_events`,
`test_future_stale_and_regressing_messages_invalidate_cache_without_reproposal`,
`test_terminal_receipt_latches_even_if_a_later_manager_record_contradicts_it`,
`test_colliding_actual_message_ids_cannot_make_an_ambiguous_basis_reference`,
`test_runtime_import_and_authority_boundary`. Source/test AST checks and `git diff --check` also passed.
No pytest, numerical framework, durable Argus store, simulator/socket, download, factory or live run was executed.
The full suite remains deferred to the coordinator's recorded command/scheduler. No acceptance/merge is performed.
