# Independent review of actual WP09 training4b evidence — 2026-10-24

## Finding 1: retained synthetic execution evidence passes independent review

**Verdict: PASS for the inspected TEST-ONLY training4b execution/evidence boundary. No material blocker found.**
This finding does not accept or merge the candidate and makes no real-data, model-quality, calibration, export,
camera-model freeze or scientific-result claim.

Source pin: `d47ddf9e7bab9e5ab08a1cf1707e406ed83204ae` in external worktree
`worktrees/xverse-blueprints/phase8-wp09-training4b-20261024` (clean, matching HEAD during review). Product
namespace successor is `b6f7e0b`; this review inspected retained evidence and source associations, not another
framework execution. External root throughout is
`/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/codex-20261024`.

Inspected actual attempts under
`scratch/codex-training4b-namespace-verification-20261024/genuine-attempt/{case-0,case-1,case-2,nonfinite-loss}`:
each command, worker receipt, stdout/stderr, job/stage/locations, actual supplied manifest/labels/source records,
bounded referenced frame blobs, and successful trained outputs. Also read the actual terminal root queue receipts
and complete logs under thesis
`specs/002-assured-aeb/review/codex-training4b-namespace-verification-20261024`.

Independent standard-library checks are retained beside this finding:

- `actual-evidence-audit.py`, SHA256 `f8d39f360a49390eeb98fc65fe4072b23fd64e90e8f3a12b59b901943ec64877`.
- `actual-evidence-audit.json`, SHA256 `b4736056a087b11809182af1f81af5c368d987ecaf4f87078d2c98ae12e6457e`.

The audit completed successfully using `python -S -s -B`; it imported only the owning standard-library record and
safe-weight readers plus the shared preprocessing parameter module, never Torch, NumPy or ORT. Its final module
check confirms those frameworks were absent. No official suite/driver rerun, namespace/kernel probe or environment
tree walk was performed. All new review artifacts remain outside candidate branches on loop10.

## Execution association and retained source pins

All four real worker commands begin `unshare -rn`, then the explicit Python3.13.13 interpreter with `-S -s -B -m
assured_aeb.perception.training_worker`. Each receipt records exactly passed namespace FDs3/4, the typed original
net/user proof, and identical before/after proof/file/closure observations. Command proof, context proof and
before/after proof agree. Real job/stage/locations, environment identity, training lock, driver and supervisor
bytes match their captured hashes. External scratch/cache locations remain on loop10. All captures have
`capture_complete=true`, `timed_out=false`, `failure=null`, cleanup complete with no errors or required TERM/KILL,
and `accepted=false`, `merged=false`.

The seven product/admission files were compared directly with their Git blobs at the source pin. Recomputing the
actual four-module closure gives
`99de5a1c70cb684ca9df0cc9f24054ce067a20a121a3ac014d7488d7ab845020`; unchanged4a closure is
`d83ba1f5e7ce1056d82a924157aad617d64db84862e4be4005abf47fcf1a3e32`. Both agree with actual stage and
capture before/after identities. Namespace admission happens before lazy framework imports; successful source
execution also repeats self-isolation/environment/source checks before writing output. This review did not
independently reopen dead workers' namespace handles: their actual invocation/captured proof and the pinned
checked program establish that execution boundary, rather than a newly fabricated observation.

Actual root owning receipt/log: revision matches source pin, return0, no timeout; complete log SHA256
`04a797aacfd70ac5125b2d4bd6cf1d56f6a3610f2ead9a8fe6688387aa409de1` ends
`1114 passed, 11 subtests passed in 53.65s`. Actual genuine driver return0/no timeout and complete log SHA256
`ce996eb8e9135e752f7717d4105fb8070f55e7520d89ee1d32164adcce88c3f1` reports three successful cases and
one nonfinite refusal. Queue state is terminal with both jobs passed. These are root's actual executions, not
suite results produced by this review.

## Actual successful artifacts and deterministic/control evidence

Each of cases0/1/2 returns0 with empty stderr. The captured stdout hash is checked against the actual stdout bytes;
that canonical JSON report plus one newline exactly matches the canonical `trained/training-report.json` file.
The externally captured report's descriptor/blob pins are then supplied explicitly to the genuine safe-weight
reader. All three packages decode as six correctly named, contiguous, finite little-endian float32 tensors:
26 parameters/104 bytes, exact admitted shapes including conv `[2,3,1,1]`, occupancy head `[1,2]` and bin head
`[5,2]`. No pickle or executable weight object is used.

All three selected weight blobs have SHA256
`d1112df276f95ef2845744c662de79fa03ce63ab2b6b5444232d67f1630d7c28`; selected named-weight digest is
`a4bb1cd3587c0a476e014d4d9406111601b44a5889e20d5b414560d752ae540b`. Reports bind actual CPU Torch
`2.14.1+cpu` and NumPy `2.5.4`, matching the actual supplied environment identity/lock pins. They show four optimizer
updates, three fit and three selection examples per epoch, and two epochs. Selection epoch1/loss
`2.348416566848755` is the actual minimum against epoch2/loss `2.4411659240722656`. The reported initial
named-weight digest `25230649589f680d76e3bb1638ca9cb2f1bdc9916fc5b324ab52bb33a587eb06` differs from the
selected digest. Initial weights are source-computed/report-bound, not a separately retained initial artifact.

Cases0/1 have byte-identical job, canonical report, descriptor and weight blob despite distinct location roots.
Their job SHA256 is `4842d46c725a57c8473414d1cc2905f0c04b857ca688fca8d13739d3fbdbf8ce`; report SHA256 is
`43cffabf57db6cf1ede7e83562c848a2f87a3ab0755d9c8748a2bb02fb76bf3f`.

Case2 genuinely changes every referenced calibration/test frame's raw pixels and digest, updates actual label
frame-hash bindings, manifest bytes and job bytes; its job SHA256 is
`3120e6a8193dfb352e77098f2c1aee70f6ed7d53ddac960d3ed659a5cf36c2e7`. Bounded zlib decoding independently
verified all referenced actual frame hashes. Fit/selection pixels, labels, observer, scenario and run-parameter
bytes remain unchanged. Sample-order digest, initial/selected named-weight digests, weight blob, epoch losses,
selected epoch and selected loss remain identical. The changed held-out labels change their frame-hash bindings,
not their semantic class targets; no class-target mutation experiment is claimed. The source uses fit for updates
and selection for checkpoint choice;4a admission's integrity reads over all partitions are allowed and are not
optimization/selection leakage. This concrete control supports the intended held-out pixel exclusion boundary,
without claiming a universal empirical proof against every possible leakage.

## Actual controlled refusal and preserved failed predecessor

The nonfinite-loss attempt has actual Python exit1, empty stdout, complete capture/no timeout/clean group, and final
stderr line exactly `ValueError: nonfinite per-example loss`. The actual traceback reaches the pinned
`training_loop._losses` finite-loss check, rather than an earlier import/namespace/resource failure or arbitrary
keyword warning. Supplied job uses the explicit TEST-ONLY finite occupancy loss weight `1e308`; no output directory
or symlink exists at the requested `must-not-exist` path. Its stderr SHA256 is
`6be232af06cf93b265739ab3b5661143ea4d965bfdf12affaf7b98a234d9167f`; execution receipt SHA256 is
`ac74e2ecf935c4ddcf4d9144680a4ee8515afd318aa70105c04a249061ad7426`.

The earlier failed parent-namespace attempt remains intact in candidate
`automotive/assured-aeb/docs/evidence/training4b-parent-ns-failure-20261024`. Its actual exit1/empty stdout and
`PermissionError` reading `/proc/2917596/ns/net` are retained, not relabeled as training success. Original receipt
SHA256 is `cf07093c4e2ab119006d6d43721f6800994fdb0db309a393d8fb43706bcfb593`; original stderr SHA256 is
`bc2873eb98e390195f2f392ef3b873746a878ae6040e12c43cba1e80cac3f363`.

No source/candidate/thesis changes or acceptance flags were made. Root may now consider evidence retention and
integration under its existing delegation; acceptance/merge remain root actions. No new scientific values are
selected. The independent14bc design findings remain unchanged at external
`design/wp14bc-independent-review-20261024.md`, SHA256
`873c3169980d20e1a1fe043e6eff0edfed961b5ff0bb41ad66aff13b3bf57c41`.

Freshness: thesis branch/upstream remain `agent/synchronize-thesis-obsidian-notes` /
`origin/agent/synchronize-thesis-obsidian-notes`, HEAD/upstream `d97fdd1167bbd48b97aad5d4071ad59403665f42`.
Fetch completed successfully; no fetched incoming canonical-note commits were present, and the working note
remains blob `ba244ddb7df388386455524ab7667d4a1e86d5a3`. Existing thesis work was preserved; no pull/edit needed.
