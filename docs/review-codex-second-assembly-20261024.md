# Independent second blueprint assembly source review — 2026-10-24

## Finding 1 — CHANGES REQUESTED: one obsolete test fixture, no additional product blocker

Reviewed clean exact assembly `4ec3e7f0ce2e7dc35ad0e12bd64cd531103d4df0` in physical loop10
`codex-20261024/worktrees/xverse-blueprints/codex-second-integration-20261024`, accepted base
`b8a154571bd3c7529849a3e8e3f89011ba5036d9`. Read actual combined source/fixtures and external
`preparations/blueprints-second-assembly/merge-preparation.json`. The five merged source pins are:

| Increment | Reviewed successor |
| --- | --- |
| Terminal arbiter | `6748017e86b67605bce07a86fa60479c91357cd3` |
| Untrusted U4 roles | `b21824a06bf1264aefa201001cb73fc7d13087c6` |
| Training4a admission | `5244fbd9ac4d0b087f95249a2b15ca8a32cc8dbf` |
| F11v2 interface | `6382e0bfbf82fb30a4ac7713ca31e8af8cd5dd69` |
| Offline window tables | `ec141490c1be89064322a11d115443345b5cd5e8` |

Root reports actual individual owning-PASS results for these exact successors: terminal972 passed; roles983
passed/25 subtests;4a1070 passed; interface997 passed/25 subtests plus eight compiled plans; windows977 passed/
140 subtests. This review does not rerun or sum those suites, and they are not combined-assembly evidence.
Sol/high is appropriate for this cross-module ownership/provenance review, not a model switch or benchmark.

### R-AS2-1 — MAJOR verification blocker: interface fixture retains removed live terminal parameter

`automotive/assured-aeb/tests/test_wp14b0_interface.py:42` still places `arbiter.mrcSource="none"` in its shared
TEST-ONLY projection helper. The merged terminal constructor intentionally refuses this obsolete parameter at
`assured_aeb/vc_functional.py:144`. Consequently
`InterfaceTests.test_actual_arbiter_rejects_legacy_or_incomplete_metadata_without_upcast` stops at its constructor
on line237, before testing any F11 rejection/recovery behavior. This is an actual interaction between two
individually reviewed candidates, despite a clean mechanical merge.

Confirmed with the exact helper extracted by AST and genuine merged `Projection`/`FunctionalArbiter`, without
pytest/framework imports: `ValueError: arbiter.mrcSource: obsolete terminal live-source parameter; WP-15 DN-1
requires entry-value hold`. Search found no other unintended Python fixture use; the explicit obsolete-parameter
refusal regression in `test_terminal_arbiter.py` is intentional and must remain.

### Root disposition and narrow repair design, recorded before code

Root accepts R-AS2-1. Remove only the obsolete entry from the interface test's projection helper. Keep the
terminal constructor refusal, immutable entry hold, active F11v2 metadata checks and no-upcast/recovery assertions
unchanged. Do not restore a terminal live source, ignore the obsolete parameter or weaken the product to make a
fixture pass. Root implements that TEST-ONLY change after this review checkpoint; independent successor review
precedes actual full combined suite and all eight compiled plans. No repair is performed by this finding.

### Combined source and provenance independently checked

All five source commits are actual ancestors of the assembly. Of86 changed paths against accepted base,84 are
byte-identical Git blobs from at least one reviewed successor. Only `vc_functional.py` and `test_aeb_logic.py`
have mechanically composed content. Direct inspection of the latter shows the expected terminal fixture/negative
test/initial-neutral replacements combined with the reviewed F11 producer fixtures. No unrelated source delta
was found. An AST check of `vc_functional.py` with only the reviewed AC import/schema/metadata guard removed
reproduces the terminal candidate exactly, so terminal policy contains no hidden interface-merge repair.

The merged terminal path snapshots the last actually emitted scalar after clamping, including zero, and never
consults live sources or updates their consumed-source watermarks after terminal entry. Same-inbox source order,
later positive input, expiry and nominal recovery cannot replace the snapshot. Initial empty history remains
explicit neutral provenance. Active F11v2 requires closed typed metadata; an invalid envelope is refused before
its sequence becomes a valid consumed source, then a genuine valid same-sequence envelope can be used. The
request-value finite rejection/clamp stage remains the original productive behavior. Productive WP04 bytes and
passive MRC semantics remain unchanged.

Untrusted roles equal the reviewed F11 successor source: original once-per-cycle/capacity/real-reference behavior
plus strict active basis validation. Model confidence uses verified model label order and actual thresholded
occupancy decision; only the admitted small native quality/check/confidence metadata crosses F11. No vector,
raw OOD or scientific threshold was added. `digest`/`finite-number` parameter readers are narrow; the exact
runtime projection boundary still requires admitted bytes/unit/identifier set. The arbiter declaration has only
its freshness/hold parameters, and the obsolete parameter remains explicitly refused.

Training4a's three-module closure remains exactly
`d83ba1f5e7ce1056d82a924157aad617d64db84862e4be4005abf47fcf1a3e32`; accepted-design copied-file hashes match.
Genuine label/store/manifest fixture admission and all four partitions produce3 usable samples each, preserving
actual source-byte pins, bounded read-only frames and the necessary-memory-only limit. No4b worker/network/loop/
weight modules are present. Its failed real namespace proof and pending framework work are not accepted or
silently included. Offline window/protocol/projection builders remain outside the runtime import inventory.
All22 runtime root modules pass the source-only import boundary scan. F11 schema JSON equals its genuine owner
documents; artifact pins remain byte-identical to accepted base. Eight compiled plans are still root's next gate.

### Checks actually performed and limits

Small independent stdlib controls are retained externally at `codex-20261024/scratch/review_wp15/second-assembly-
review-probes.py` and `.json`: provenance/blob comparisons; exact terminal composition AST; eight source/clamp/
terminal/update/lockout combinations; initial empty history; genuine F11 metadata rejection/recovery; the actual
conflicting interface fixture; admitted own-unit projection plus four narrow-kind controls; genuine4a admission/
partition reads; copied-input pins;22-source offline-import scan; schemas and unchanged artifact pins. Final
controls completed successfully while deliberately reproducing R-AS2-1. Two initial independent harness setup
errors (an unrelated extracted constant's missing JSON global, then a dict rather than the required identifier
collection) were corrected in scratch only; they were not product findings. All20 changed Python files parse and
`git diff --check` passes.

Thesis fetch succeeded with no incoming canonical-note change; working note blob remains
`ba244ddb7df388386455524ab7667d4a1e86d5a3`; dirty thesis files were preserved. All new data/temp/cache remained
loop10. No pytest, Torch/NumPy/ORT, environment-tree hashing, compiled-plan execution, live/C1 operation, source
repair, main update, acceptance or merge was performed by this review. The sole identified blocker is the test
fixture above. After its independently reviewed repair, full combined verification and root's separate
acceptance decision remain mandatory; existing design/live/scientific gates are not reduced.

## Finding 2 — independent TEST-ONLY fixture successor re-review: PASS

Reviewed clean exact repair `21f22fc00817dfb9738b8d9c62f4ac4bd2dcd4d1` against finding1's pre-code disposition.
R-AS2-1 is closed. Byte comparison confirms that the interface test differs from4ec3e7f only by removal of the
single `arbiter.mrcSource="none"` pair. Git product-subtree identity and intentional terminal-refusal test blob
are unchanged. The genuine merged constructor now admits the intended fixture; no product check was weakened.

Executed the exact interface test method
`test_actual_arbiter_rejects_legacy_or_incomplete_metadata_without_upcast`, extracted together with its actual
projection/input helpers by AST and invoked with a stdlib TestCase. Its genuine SmartCamera/FrontZone/
CameraInference model-free fixture/Fusion path constructs active F11v2; all three legacy/unknown/missing-metadata
refusals and subsequent genuine same-sequence recovery assertions pass. No pytest, NumPy, Torch or ORT was
imported. This directly exercises the test path previously blocked by the obsolete constructor parameter.

Four independent actual constructor controls still refuse the obsolete field for adas-cycle, fallback-request,
none and unknown values. An additional genuine F11 source control clamps1.4 to1.0, snapshots that actually emitted
value on terminal entry, ignores a same-inbox zero and later live recovery, and retains last-emitted provenance
with no selected live source. Thus repairing the fixture did not reintroduce a terminal source or bypass metadata.

Complete small-probe script/result are retained externally at `codex-20261024/scratch/review_wp15/second-assembly-
fixture-successor-probes.py` and `.json`. All temporary data remained loop10; no suite, framework, environment-tree
hash, compiled plan, live/C1 run, main update, acceptance or merge was performed. Original failed fixture finding
and source pin remain in history. No further source blocker is open from this independent assembly review.
Root next schedules the full combined owning suite and all eight compiled plans against an exact admitted pin;
their actual results and separate delegated acceptance remain required. Sol/medium was the informational
cost-effectiveness recommendation for this narrow re-review; no model switch was claimed.
