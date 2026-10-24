# WP-13 terminal arbiter successor (WP-15 DN-1)

Candidate `candidate/phase8-wp13-terminal-20261024`, from isolated accepted integration
`426bd2484d54f660a3aaad5f22fb182bf66fbbb0`. Offline source increment only, pending separate review and suites;
no acceptance, merge, protocol freeze, live execution or scientific claim. Sol at high reasoning is recommended
for this small stateful safety contract; no model switch or benchmark is claimed.

## Finding 1: reconciliation design before code (2026-10-24)

Authority: thesis `specs/002-assured-aeb/decisions.md`, "WP-15 DN-1 to DN-7 and re-review dispositions", accepted
`design/wp15-graph.md` §2.7/DN-1, and the coordinator's scoped implementation instruction. Fresh thesis fetch
leaves HEAD/upstream `d97fdd1167bbd48b97aad5d4071ad59403665f42`, with no incoming canonical-note change.
The working canonical note remains the previously fully read blob `ba244ddb7df388386455524ab7667d4a1e86d5a3`;
its dirty state and all other thesis work are preserved. No canonical note is edited by this successor.

The existing arbiter's `arbiter.mrcSource` enum selects a live ADAS/fallback source or no source in terminal
configuration. This conflicts with the decided entry-value hold and cannot remain an admitted parameter.
Remove it from `ARBITER_DECLARATION` and the TEST-ONLY fixture projection. Refuse it explicitly if an old
projection still supplies it, including all formerly allowed alternatives. No replacement parameter or numeric
default is introduced; freshness and ordinary bounded-hold parameters remain required for operational behavior.
The consumed-parameter digest consequently covers the two remaining entries. Unit projection membership/freeze
is not supplied here; later wiring must use the revised declaration and new admitted digest.

Track the value of the last successfully returned WP-04 brake request separately from raw live requests and
per-source hold caches. On the first accepted `S_MRC_REQUESTED` selector, copy that already clamped emitted value,
including zero, into an immutable terminal snapshot. Do not process a live source to choose terminal output,
including sources delivered in the entry inbox. Repeat exactly the snapshot on every subsequent decision cycle,
regardless of source updates/loss, malformed/nonfinite live requests or the ordinary request-hold window.
The same class/rule applies to all arms without an arm label. Operational selected-source behavior stays unchanged.

Terminal state is irreversible: refuse and record operational/recovery selectors, including those later in the
same inbox. Fresh duplicate terminal selectors are recorded as already entered and cannot change the snapshot
or selector identity. Preserve existing malformed/source/configuration/sequence refusals. Return one unchanged
five-member WP-04 brake request per cycle with advancing sequence/current simulator origin. Terminal-cycle
evidence has kind `terminal-entry-value-hold`, no selected live interface/source metadata, and explicit
`terminalHoldProvenance` (`last-emitted-request` or the empty-history case below); operational evidence has null
provenance. The `value` is the held output and `rawValue` is null: it is not a freshly selected/clamped live request.

**Empty-history disposition, before code (coordinator, delegated; flagged for author review):** terminal can
arrive before the first emission. Keep the existing neutral 0.0 initial output and enter lockout, with provenance
`initial-neutral-no-prior-emission`. Never claim that an actual request preceded it. A same-inbox valid live request
cannot replace this neutral initialization. This adds no brake level, threshold or availability credit and does
not refuse a terminal selector. Whenever emission history exists, the decided last-emission snapshot applies.

The passive MRC request/sink, manager/supervisor wiring, horizon ownership and offline availability classification
remain outside this source change. The arbiter executes no external MRC. Under AD-14 every eligible cycle after
an MRC request counts as missing regardless of held value; terminal output earns no adaptation/availability credit.
SADS/P8-T06 remains partial: this reconciles one productive arbiter behavior, not the full graph, wiring, oracle,
host/runtime fitness or scientific evidence. Existing WP-13 review history is retained with this dated successor
superseding only its terminal live-source contract.

Planned regressions: last emitted zero and positive values; upper/lower clamp results; a last emitted zero after
hold expiry rather than an older positive valid request; both operational sources; live values in entry/later
inboxes and absent live input beyond hold expiry; irreversible same-inbox/later recovery refusal; idempotent
terminal entry; empty-history provenance; obsolete projection refusal; unchanged five-member requests accepted
by the real chassis/node. Use TEST-ONLY fixtures only. While the platform/assembled suites own execution, only
tiny stdlib probes, AST and diff checks are authorized; pytest remains queued for the coordinator.

## Finding 2: implemented candidate and bounded checks (2026-10-24)

Implemented after design checkpoint `061f947`. The arbiter records its last emitted clamped value independently
of per-source caches, snapshots it only at the first accepted terminal entry, refuses recovery/duplicate entry,
and ignores live sources in terminal cycles. Empty-history neutral output has explicit provenance and cannot be
relabelled by a later output. `arbiter.mrcSource` is removed and explicitly refused, with no replacement parameter.
The productive WP-04 shape is unchanged; `terminalHoldProvenance` is an offline evidence addition.
`terminal-arbiter.md` documents the current contract; the old review history has a dated supersession pointer.

The existing TEST-ONLY projection removes the obsolete parameter; its former live-terminal test now asserts
initial neutral output and provenance. Seven new regression functions (19 parametrized cases) cover both
operational sources, zero/positive/upper/lower clamped outputs, later live updates and missing input beyond the
hold window, same-inbox/later recovery refusal, duplicate/replayed/foreign selectors, obsolete projections,
mutable caches/returned requests, last emitted zero after expiry, empty-history order and actual prior-zero
provenance. The terminal request is passed through the genuine unchanged chassis and brake/ESC node contracts.

Performed: 17 tiny stdlib source controls, including both operational sources with four clamp/value cases,
empty-history order, last-zero-after-expiry, all three formerly admitted obsolete parameter values,
mutable-reference independence, actual-zero provenance and genuine WP-04 chassis/node acceptance. All passed.
AST parsing of all three changed Python files and `git diff --check` passed. No pytest runner, inference,
simulation, CARLA, Argus process or heavy suite was started. All numeric probe/test values are TEST-ONLY.

Queued after the coordinator releases execution: focused `tests/test_terminal_arbiter.py` and
`tests/test_aeb_logic.py`, then the complete owning blueprint suite and independent review on the assembled
successor. Suggested focused command from `automotive/assured-aeb` with admitted environments:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 XVERSE_AEB_SENSOR_SITE=/dev/shm/xverse-aeb-sensor-20261024/venv/lib/python3.13/site-packages XVERSE_PLATFORM_PROFILES=/tmp/codex-xverse-review-20261024-q93eotxv/xdl/profiles /dev/shm/compat-p6-venv/bin/python -I -B -m pytest tests/test_terminal_arbiter.py tests/test_aeb_logic.py -q -p no:cacheprovider --tb=short
```

Status: scoped implementation candidate, not accepted/merged. Manager/supervisor/sink wiring, admitted unit
projections, numeric freeze, horizon execution, oracle/availability accounting and live/scientific validation
remain separate gates. Recommend a precise Note 23 AUTHOR-DELEGATED ENGINEERING CONTEXT update after this
successor's acceptance, linking WP-15 DN-1 and its empty-history disposition; do not update the note automatically.
