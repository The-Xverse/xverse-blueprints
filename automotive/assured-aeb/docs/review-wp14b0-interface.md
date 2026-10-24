# WP14b0: minimal versioned F11 evidence interface

## Finding 1: detailed implementation design before code (Codex, 2026-10-24)

Authorized scope is coordinator disposition `076e96e`, WP14b design finding2 and thesis
`review/wp14b-dispositions-20261024.md` / decisions.md. Read all D14b-1..7 dispositions. This isolated worktree
`/home/jefferson/xverse-blueprints-worktrees/phase8-wp14b0-20261024`, branch
`candidate/phase8-wp14b0-20261024`, starts at `b21824a06bf1264aefa201001cb73fc7d13087c6`.
Its reviewed WP14e dependency remains **full-suite pending and unaccepted**; it must be accepted before 14b0 delivery.
The pinned WP14e branch is untouched. Thesis freshness fetch succeeded, HEAD/upstream d97fdd1, unchanged canonical
note blob ba244ddb from completely read context, no incoming note change/pull. Preserve unrelated dirty work.

This increment implements interfaces/reader types only. It does not implement validator, diagnostics, startup,
new observation routes, ED12 additions, supervisor/transition policy, scientific thresholds, live execution or freeze.
Sol/high is recommended for exact owner/consumer reconciliation; no model switch or measured comparison is claimed.

1. Add stdlib `assured_aeb/adas_contract.py`, owning active `assured-aeb.adas-cycle/2`, historical v1 name, exact
   top-level/nested native types and detachable validation. Active emission is v2 only; v1 is an explicit historical
   identifier, not an implicitly upgraded assurance record. Every v2 camera summary includes seven exact inputQuality
   keys, each its owned enum or null (fresh is exact bool/null), plus nullable occupancyDecisionConfidence and
   distanceClassConfidence. Radar summary adds nullable exact original F08 checks. Existing other members stay.
2. Camera quality forwarding admits only the known source quality keys plus the already owned optional indicators,
   but exports only the seven named categorical fields. Missing/unknown/wrong-native values are null, never pass;
   undeclared source quality shape is wholly unavailable. No raw image indicators enter F11. Original F08 checks are
   copied only when closed shape/native types/known vocabularies hold. Pass-with-failed-codes and fail-with-empty-
   codes remain known typed contradictions, copied unchanged for later U5 refusal; do not repair/launder them.
   Unknown/extra classes or malformed types yield unavailable checks, not a fabricated favorable check record.
3. FusionRiskAeb keeps its entire productive hypothesis, state, association, decision/latch/hold algorithm and
   parameter declaration unchanged. Add metadata after the existing camera view is derived: occupancy confidence
   is p when p>=the already admitted fusion.occupancyThreshold, otherwise 1-p. Distance confidence indexes the
   actual selected predictedBin in the protocol-known class order no-obstacle/overlap/bin-0..bin-(N-1)/beyond;
   a missing/mismatched/nonfinite probability vector or unknown selected label makes it unavailable. No extra vector,
   OODscore, source-clock rewrite, image statistic or provenance field is emitted. Three ML provenance keys stay exact.
   Unknown profile metadata does not alter the existing productive state/request. New camera metadata survives cached
   cycles with its original sample origin; outer sequences/time do not refresh that origin.
4. Reconcile active aliases and exact consumers: role-contract wire aliases map the existing logical adas-cycle /
   proposal-basis URNs to v2. Closed owner validation is shared by the role adapter and proposer basis consumer.
   Preserve expected/received/payload source separation and only the existing actual endpoint pairs. The arbiter uses
   v2 envelope/native metadata checks, preserving its existing finite-request rejection/sequence-consumption/clamp/
   hold/forwarded-state behavior; request-value nonfiniteness remains handled at its original stage. Out-of-range
   finite requests still reach its deliberate clamp. No blanket assurance qualification or state-driven selection is
   added. Fallback schema/behavior and WP04 wire records remain unchanged. Historical v1 never passes active v2
   consumers merely because its source/brake field looks usable.
5. Generate a closed v2 JSON Schema from the owner definitions for both logical aliases and regenerate wire-aliases.
   Existing logical XDL URNs remain interface IDs as with accepted14a's wire-alias mapping; no route/authority/units/
   flow budget changes are authorized. Compare generated topology/maestro JSON to the current checked-in forms using
   existing pins; if documents are unchanged, record that rather than claiming new compiled identities. Root schedules
   actual owning/topology/compiled-plan verification; no platform/framework imports for it now.
6. Add Projection.take kinds digest (bare lowercase HEX64) and finite-number (exact finite int/float, excluding bool
   and unrepresentable numeric values). Values still require explicit identifiers and own-unit admission; no raw entry
   access, coercion or default. This adds capability for future14b declarations, not a new role or chosen real value.
7. Tests use real SmartCamera/FrontZone/CameraInference contract emission with a TEST-ONLY deterministic inference
   callable (no ORT claim), real SmartRadar/FrontZone and FusionRiskAeb. Check occupancy zero, a non-half threshold
   demonstrating p-versus-1-p rather than max(p,1-p), selected-bin indexing, known false/null flags and unchanged
   contradictions, unknown/extra/native-type refusal, detached copies, exact v1/v2/unknown consumers, separate source
   identity, digest/finite-number cases and metadata stripping equivalence against the pre-change genuine owner.
   Amend sparse old arbiter test messages into complete explicit v2 fixtures while preserving malformed-request tests
   and every existing brake/hold/clamp expectation. Existing genuine U4 proposer fixtures consume the new owner version.

Only syntax, small stdlib direct controls and document-generation comparisons are permitted during the active
platform regression. No pytest/NumPy/ORT/torch/Argus durable work, download, factory/live run or acceptance/merge.
Independent source review, root-scheduled complete suites/topology evidence and accepted14e dependency are delivery
gates. O-2/V04 remains allocated to later14b qualification; these metadata changes are not its completion or a
scientific confidence/quality proof. All threshold values/minima/numeric freeze and remaining startup/deadline
observation design questions stay open. Recommend a DRAFT Note23 update only after later acceptance, never automatic.

## Finding 2: explicit logical payload version disposition before generated-form edits (2026-10-24)

The coordinator disposition supersedes finding1 §5's proposed stable logical URN aliases: this is a material payload
contract evolution, so **both** logical payload contracts become `urn:xverse:assured-aeb:adas-cycle:v2` and
`urn:xverse:assured-aeb:proposal-basis:v2`, with their X-COM interface-policy schemaVersion `2.0.0`.
Element/interface/endpoint/flow names, source authority, other payload URNs/policy versions and WP04 bytes remain
unchanged. Active EndpointBinding/version lookup must use this version explicitly; historical v1 registration is
separate and cannot silently negotiate or upcast assurance metadata. Wire schema remains `assured-aeb.adas-cycle/2`.

Update owner-generated schemas/aliases and topology generation together; use unchanged existing recorded artifact
pins and retain precise before/after document identities. Actual compiled semantic plan identities will change as
measured by the coordinator's later topology verification; do not claim they are unchanged from text/source equality.
No new route, authority or latency/allocation value is authorized. Owning/topology/capacity/compiled checks stay in
root's serialized queue. Record this amendment in a separate design checkpoint before editing generated forms.

## Finding 3: implementation checkpoint and actual limited evidence (Codex, 2026-10-24)

Source checkpoint `bdcf5b2f50f08d3e5719be079658ddcdabaee86d` follows design `7e241a6` and the explicit logical-version
amendment `ab222af`. **Implemented candidate, independent review and owning delivery pending.** Its WP14e/main
assembly dependency b21824a remains subject to full-suite/dependency acceptance before this increment's delivery.

`adas_contract.py` owns exact active F11/proposal-basis /2 native shapes and generated JSON Schemas. FusionRiskAeb
adds only the seven categorical camera flags, the two dispositioned confidence scalars and closed original F08
checks. Camera flag native types are preserved (including false), unknown values are null, original typed radar
contradictions remain unchanged and no raw image indicators/bin vectors/OODscore are added. The occupancy equation
uses the actual admitted fusion threshold, including threshold values other than one half and p=0. Distance
confidence indexes the actual selected class in the known protocol class order. No threshold/default, quality claim,
new qualification algorithm or ML provenance key is introduced. Existing productive association/state/latch/request
logic remains the owner; metadata does not authorize a transition or select a braking source.

The active F11 wire and both logical payload URNs are explicitly v2, with X-COM interface-policy version 2.0.0.
The historical v1 wire/URN registrations are separate, documented and excluded from active negotiation; current
consumers refuse v1/unknown versions rather than invent missing assurance metadata. Role endpoint consumption keeps
expected producer, received producer and original payload owner distinct. The exact owner validator is shared by
the role/basis consumers; the arbiter validates the v2 envelope while retaining its original nonfinite-request
watermark stage, finite clamp, hold, selector and forwarded-state behavior. Transport attestation and actual
whole-unit entry wiring remain 14f obligations, not demonstrated here. Narrow digest/finite-number Projection kinds
read explicit identifiers with no coercion or default. Validator, diagnostics, startup, new observation routes,
ED12 additions and remaining 14b/14c policies are not implemented by this increment.

The generated-document receipt `docs/evidence/wp14b0-generated-document-deltas.json` compares all **301** existing
topology/maestro documents against generation with their unchanged recorded artifact pins. Exactly **46** documents
change; an independent recursive comparison restricts their deltas to the two payload URNs and their interface-
policy schemaVersion values. Every before/after document SHA256 is retained. Artifact-pin bytes remain unchanged
(SHA256 `0e8ba373d5676f5d2f67bf9b8c27b93b3914e81b33b5f6ef5d851695b8187472`). New owner schema documents, active
wire aliases and a separate historical-only alias file are generated from the runtime definitions. No compiled
semantic plan digest, topology/capacity suite pass or unchanged-plan-identity claim is supplied: those are later
root-scheduled measurements after this material version evolution.

**Actually performed before the relocation hold, on final source:** eighteen selected tiny stdlib controls passed:
ten new interface methods (genuine SmartCamera/FrontZone/CameraInference-contract/SmartRadar/Fusion producers,
zero/non-half/equality occupancy confidence, selected distance confidence, typed unknowns/contradictions, actual
arbiter and basis/endpoint version refusal, source checks, reader types, generated schema/301-document version
comparison and metadata-stripped equivalence against the actual pre-change FusionRiskAeb source); six existing
functional clamp/nonfinite/replay/hold/forwarded-state/WP04/epoch-stream controls; and two genuine U4 proposer/cycle
controls. CameraInference's deterministic TEST-ONLY inference callable is model-free: no real ORT/calibration claim.
Existing sparse arbiter fixtures now use a complete genuine v2 owner envelope before applying their deliberate
request/state stimuli; the untrusted-role fixture's synthetic class vector matches its declared six-class order.
Ten source/test/topology AST parses and `git diff --check` passed. No pytest, NumPy/torch/ONNX/ORT import, durable
Argus, actual model execution, download, factory or live run was performed. These controls are not a full suite.

The author then required new data on loop10. Source was committed cleanly as bdcf5b2 before the write hold. The
coordinator verified the relocation, including all data hashes/modes and Git state, and authorized same-path resume.
The original logical worktree path is now an alias to
`/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/codex-20261024/worktrees/xverse-blueprints/phase8-wp14b0-20261024`.
This worker rechecked physical path, exact HEAD and clean status; it did not rerun tests or rehash the relocation.
All new scratch/fixture/output data must use explicit loop10 TMPDIR, currently the worker subdirectory
`/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/codex-20261024/scratch/review_compat_envs`.
Main Git metadata also resides on loop10 under the coordinator's verified relocation. Frozen platform/rc.1 inputs
are untouched. This log is the only post-relocation change in this worker's finalization pass.

Deferred targeted command, from this worktree's `automotive/assured-aeb`, **only when root schedules it**:

```sh
env TMPDIR=/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/codex-20261024/scratch/review_compat_envs \
  PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  /dev/shm/compat-p6-venv/bin/python -I -B -m pytest -q -p no:cacheprovider \
  tests/test_wp14b0_interface.py tests/test_aeb_logic.py tests/test_u4_untrusted.py tests/test_role_contract.py --tb=short
```

Then root owes the complete owning suite and `check_topology.py --platform-profiles <admitted-profiles> --report
<loop10-report>`, its compiled identities/capacity checks and independent source review/acceptance/integration.
The external profile input must be the admitted pinned source; no interpreter/artifact pin refresh or existing run
mutation is implied. Real confidence minima/scientific calibration support, AD27, later 14b/14c startup/deadline
design and live gates remain open. The inherited FR007/FR024/FR028/V04 and public SADS allocations remain partial:
this candidate supplies an interface prerequisite only and closes no parent or scientific assurance claim.

## Finding 4: independent source review, CHANGES REQUESTED (Codex, 2026-10-24)

Reviewed exact `c12cd036bb73b2b4aebb85701de3106c97888296`, source `bdcf5b2`, dispositions `076e96e`, designs
`7e241a6`/`ab222af`, findings 1–3 and the genuine owner/consumer/schema/topology definitions. The reviewer did not
author 14b0 and makes **no product/test repair or acceptance**. Sol/high is recommended for the narrow successor
and independent review. The worktree's physical path is the verified loop10 location recorded in finding 3.
All new temporary data used explicit loop10 TMPDIR under `scratch/review_wp15`, never internal /tmp.

Thesis HEAD/upstream remain d97fdd1 and the working canonical-note blob remains ba244ddb from completely read
context. The thesis still physically resides internally during coordinator relocation, so this interaction kept
it read-only rather than fetch/write new internal Git data, as reported to the coordinator. No new fetch is claimed.
The unchanged local governing dispositions were read; no canonical note or scientific decision is changed.

### R14b0-1, MEDIUM: selected-bin confidence assumes a class order not enforced by its actual owner contract

`FusionRiskAeb.__init__` reconstructs `self.bin_labels` as no-obstacle/overlap/bin-0..bin-(N-1)/beyond from its
distance edges. `AC.confidences` then indexes the received vector by that reconstructed order. However the accepted
`postprocess.parse_record`, `CameraInference.__init__` and `CameraInference.load` permit any explicit unique
postprocess label order from the owned vocabulary. Load checks names/count against static model outputs, not
equality to Fusion's reconstructed order. The perception-output wire contains probabilities/predictedBin and
postprocess provenance, but does not carry the class order or an independently checked order assertion.

The direct independent counterexample uses genuine SmartCamera/FrontZone input and `CameraInference.step`, a
genuine accepted postprocess record and a deterministic TEST-ONLY inference callable (no model/framework claim):

- Actual owner label order: `[no-obstacle, overlap, bin-2, bin-0, bin-1, beyond]`.
- Finite normalized TEST-ONLY probabilities: `[0.05, 0.05, 0.7, 0.05, 0.05, 0.1]`; the actual first maximum selects
  bin-2, so its selected-class probability is 0.7. Occupancy is 0.8, and the genuine perception owner emits NOMINAL.
- Fusion's six-class canonical lookup takes bin-2 from position 4 and emits distanceClassConfidence=0.05.
  The full F11 /2 owner validator accepts the result. No probability/type/length/selected-label check catches this.

This violates the adopted **actual selected class probability** definition while preserving productive braking
logic; it is an assurance-metadata binding gap, not a demonstrated actuation bypass or real-model quality result.
The positive fixture always uses matching canonical order, so all ten existing interface methods pass without
covering it. A known agreed training order does not by itself enforce the actual runtime postprocess binding.

Required disposition before repair: make the actual order agreement an enforced owner/composition boundary before
emitting this confidence. For example, explicitly bind and check the pinned postprocess class order against the
Fusion configuration, or reject noncanonical order at the appropriate perception/model-admission boundary if that
structural contract is chosen. The currently accepted arbitrary-order owner API must not silently disagree with
the new F11 scalar. If order is unavailable/mismatched, it cannot produce a falsely attributed scalar. Add the
same-size permutation regression using the real owner path and require refusal/unavailability or the correct actual
selected probability. Do not silently reorder source probabilities, substitute max(p) as a different method, leak
the vector into F11, add a scientific threshold or change the functional/latch algorithm. Any owner-contract
restriction must be recorded before code and checked against existing ML fixtures. No repair is made here.

### Positive source and limited verification findings

The occupancy equation follows the actual admitted `>=` threshold, including p=0, equality and a non-half
threshold, rather than p alone or max(p,1-p). The seven camera quality fields preserve exact bool/owned enum/null
types; missing/wrong-native/unknown values never default to pass. An undeclared source quality shape becomes
unavailable. Original closed F08 checks are detached and typed contradictions remain unchanged for later U5
qualification; malformed/extra classes become unavailable. No probability vector, raw OODscore or raw image
indicators enter the new F11 metadata. All three existing ML provenance fields remain unchanged.

Active wire /2, both logical payload URNs v2 and X-COM2.0.0 policy versions are coherent. Historical v1 wire/URN
aliases are separate and absent from active lookup; there is no upcast. Exact endpoint consumers preserve projected
expected/received/payload source separation and refuse legacy/unknown/undeclared pairs. The 14e basis consumer uses
the same closed owner and retains its independent source/goal/configuration/cycle guards. Digest and finite-number
reader kinds are narrow, identifier-based and default-free; bool/nonfinite/unrepresentable values are refused.
No new scientific identifier value, qualification rule, gate authority or runtime offline import is introduced.

Independent producer equivalence: compiled the actual prechange Fusion owner from base b21824a and compared twelve
paired current/prechange productive cycles after stripping only the new schema/metadata. All matched, including
real SmartRadar/FrontZone inputs, firing, latch hold, cached/no-input, UNCERTAIN and release cases; observed TEST-ONLY
requests were `[0,0,1,1,1,1,1,1,0,0,0,0]`. A separate six-control actual arbiter probe preserves nonfinite-request
sequence consumption, replay refusal, finite out-of-range clamping, source hold/expiry and forwarded UNCERTAIN
without state-driven braking. This does not prove future whole-unit wiring or timing behavior.

Independent document comparison inspected all 301 existing topology/maestro JSON documents against base b21824a.
Exactly 46 files differ; every recursive difference is one of the two payload URNs v1→v2 or its schemaId-owned
policy schemaVersion 1.0.0→2.0.0. Every recorded before/after SHA256 in the generated receipt matches actual bytes.
Artifact-pin bytes match the base exactly and reproduce SHA256
`0e8ba373d5676f5d2f67bf9b8c27b93b3914e81b33b5f6ef5d851695b8187472`. No authority, route, allocation, endpoint,
flow budget or other payload/policy version delta was found. This was stdlib source comparison, not compiled-plan
or capacity verification; semantic digests and actual topology validation remain scheduled gates.

**Actual checks:** ten existing interface stdlib methods called directly and passed, the class-order counterexample
above reproduced, twelve independently paired productive cycles and six independent arbiter controls passed,
301-document/version/hash/pin comparison passed, ten Python AST parses and whitespace diff check passed.
No pytest runner, numpy/torch/ONNX/ORT import, actual model/calibration, durable Argus, topology compilation,
environment-tree hashing, download, factory or live run occurred. All values/outputs above are TEST-ONLY.

Verdict: CHANGES REQUESTED for R14b0-1. After a separately designed repair, obtain independent successor review and
root-scheduled focused/owning/topology/compiled/capacity evidence, plus the 14e dependency acceptance and correct
assembled integration. The original declared later 14b/14c/WP15 startup, timing, qualification and diagnostics work,
actual projection/source attestation, confidence minima/calibration support, AD27 and live/scientific gates remain.

## Finding 5: R14b0-1 narrow binding repair design before code (Codex, 2026-10-24)

Root authorizes the explicit immutable-model-output binding alternative to finding4; do not impose canonical
label order on the generic postprocess/CameraInference APIs. Starting reviewed HEAD is c0cd027. This design is
committed separately before implementation. Sol/high is recommended for the exact admission/consumer boundary.

Add stdlib `model_output_binding.py` with a frozen, slotted `ModelOutputBinding`. Its only retained fields are
`bin_labels: tuple[str, ...]` and `postprocess_sha256: str`. Its constructor accepts model metadata only, copies
that mapping, calls existing `PP.verify_binding` and `PP.parse`, and derives BOTH fields from the resulting parsed
record. No hash/order-pair constructor, default, setter, full retained postprocess record, scientific number or
alternate parsing method is provided. Caller mutation cannot change the binding. Invalid code binding, malformed
or noncanonical record refuses construction before Fusion exists. This checks record/code consistency; it does
not independently prove that caller-supplied metadata originated in an admitted model.

`FusionRiskAeb(projection, *, model_output_binding=...)` requires the exact binding type, with no default.
Require its label count and complete label set to equal the vocabulary implied by the admitted distance edges;
arbitrary order within that set remains valid. Remove canonical-order reconstruction from confidence indexing;
use the bound actual order. Before computing either new confidence scalar, compare the incoming original
`postprocessSha256` against the binding. A mismatch makes both scalars unavailable/null, without altering the
productive `_camera`/association/decision/latch/hold path or legacy fields. Missing/malformed input still follows
its existing productive treatment. This metadata refusal adds no threshold, actuation gate, vector/order on F11,
new provenance field, full postprocess state in Fusion or dependency on another role's internals. PP/CI files and
model fixture bytes/code hash remain unchanged.

Trusted U4 composition in later14f must derive the binding from the **same digest-verified frozen model metadata**
that genuine `CameraInference.load` inspects, before readiness. It must verify/read those frozen bytes through the
existing loader/static inspector, construct this binding from that public metadata, and supply it explicitly to
Fusion while CI.load independently checks the same declared digest/metadata. It must not invent an unrelated
order/hash pair, infer order from protocol conventions, read CI's private state, or claim helper construction alone
attests a model file. Actual 14f composition/ORT readiness remains deferred, not implemented by this repair.

Tests: migrate all actual Fusion construction sites to explicit bindings from real PP metadata, retaining each
existing parameter/refusal intent. Add genuine SmartCamera→FrontZone→CI-contract fixture with permuted real PP
record and derived provenance: `[no-obstacle, overlap, bin-2, bin-0, bin-1, beyond]` plus TEST-ONLY probabilities
`[.05,.05,.7,.05,.05,.1]` must report actual selected confidence .7. Canonical fixture remains .7; p=0 and actual
threshold equation remain checked. Refuse wrong binding type/missing argument, wrong label count/set, invalid code
binding/malformed/noncanonical metadata; prove frozen/detached state and digest changes when order changes.
Wrong valid PP binding against incoming provenance yields null confidence without a productive change. Repeat
metadata-stripped paired equivalence against the actual prechange owner, including canonical/permuted/mismatched
provenance input. No test may substitute max probability or fabricate a live-model quality claim. All fixtures are
TEST-ONLY; generic PP/CI permutation support must survive. Only stdlib direct controls/AST/diff are currently
authorized. Root schedules pytest/owning/topology verification and independently reviews the exact successor.
No acceptance, merge, new scientific decision or canonical-note update is implied.
