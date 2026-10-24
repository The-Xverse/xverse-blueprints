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
