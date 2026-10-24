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
