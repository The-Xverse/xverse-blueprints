# WP-09 training4b: CPU network, fit/selection and safe weights

## Finding 1: implementation design before code (2026-10-24)

Authorized only4b, from reviewed4a assembly `5244fbd9ac4d0b087f95249a2b15ca8a32cc8dbf` (parent full-suite/acceptance pending).
Accepted pipeline `a89a52ef39952f003e8c2572a5b4d5dc3d60facd` findings1–5 and thesis pipeline-method dispositions govern.
Thesis fetch succeeded, HEAD/upstream `d97fdd1`, no incoming canonical-note update; working note blob remains
`ba244ddb7df388386455524ab7667d4a1e86d5a3`, already fully read. Preserve every dirty thesis/main file.
All source, worktree, scratch/cache and eventual test artifacts are on loop10. No framework/pytest/live execution
is authorized in this worker turn. Sol/high is a task-based recommendation for deterministic/resource boundaries,
not a benchmark or model switch. Parent independently reviews and schedules actual verification.

### Scope and input identities

Add offline-only `training_network.py`, `training_weights.py`, `training_loop.py`, `training_worker.py`; importing
these modules imports the standard library and existing stdlib admission modules only. No runtime import changes.
Do not change the named three-module4a closure, accepted TrainingJob/1, label/manifest/source contracts or genuine
compat preprocessing. A separate canonical closed `assured-aeb.training-stage4b/1` record has exactly `schema`,
`jobSha256`, `sourceClosureSha256`. The source closure is the canonical ordered list of actual file names/hashes
for these four4b modules; it is checked before framework import and recorded separately in every output. It binds
engineering implementation without manufacturing a real job field. Changing4b requires a new stage record;
changing4a still requires a new genuine job identity. Stage/job bytes remain separate, both bound in the report.
Actual identity/lock paths, output directory and parent network-namespace reference are operational locators/
launch observations, not scientific values or model metadata paths.

The public worker operation reparses actual job/location/stage bytes, admits the actual dataset with4a, and
requires a fresh worker with no preloaded torch/numpy/onnxruntime, `-S -s -B`, explicit admitted sites and only
loopback in the actual network namespace. Its current namespace must differ from the launcher's actual parent
reference; the later owned launcher must record that reference before genuine `unshare -rn`, never a made-up
namespace string. No shell/network/plain-subprocess fallback is added. Identity/lock bytes reproduce the job's
expected digests; the genuine compat training identity schema/import result/lock revision/interpreter/site/package
bindings are checked, including environment/interpreter source trees before imports. Loaded torch/numpy must
match lock versions, CPU-only and approved actual origins. U4/ORT is never imported in this worker. This is a
local immutable-input check, not hostile-code sandboxing; the recorded namespace/build/source-truth limits remain.

Set actual worker address-space and per-file write limits from explicit memoryBytes/outputBytes; total output
is checked separately against outputBytes/diskBytes. Apply the explicit worker wall timeout as an engineering
control. These limits can refuse an otherwise syntactically admitted job:4a's necessary tensor floor is not a
promise that framework/base process/workspace/checkpoint fits. No multiplier, allowance, hardware value or real
scientific number is invented. The later fresh-process supervisor must also enforce timeout and retain failure
artifacts/status; a failed worker never publishes a model/candidate marker.

### Network and deterministic fit

Construct exactly ordered Conv2d/ReLU blocks, fixed adaptive global-average pool to1, Flatten from dimension1,
and independent occupancy/bin Linear logits heads. Every declared convolution/head argument and bias flag is used;
CPU float32 is explicit. All parameters, including bias, receive owned uniform initialization from the supplied
bounds, one dedicated CPU generator and sorted named-parameter order. Constructor initialization is overwritten;
assert actual parameter count/names/shapes. No sigmoid/softmax, augmentation, corruption or online learning.

Set explicit CPU intra/inter-op threads, deterministic algorithms, torch/numpy seeds. Data order is an owned
SHA256-key permutation of canonical sample identity, dataOrder seed and epoch (all bound in source); this avoids
implicit global RNG/worker state. Canonical sample identity is runId/frame/rawSha256. Keep the final short batch.
The4a API has streaming iteration but no random lookup; retain only metadata identities and rescan the read-only
fit iterator for each requested batch. This costs additional verified reads (worst-case quadratic per epoch),
but retains only one batch's raw/preprocessed data and preserves4a without a silent API/closure change. No cached
raw/tensor corpus or hidden disk spool. A later performance change needs its own explicit review.

Use exact accepted occupancyTarget and binIndex/classOrder from admitted labels. Shared compat preprocessing alone
creates float32 NCHW. Verify actual numpy/source/parameter binding, shape/dtype/finite values; no local image
conversion. Fit reads fit only; checkpoint loss reads selection only. Admission can validate calibration/test
bytes but no such frame is preprocessed, forwarded, fitted or used to select weights in4b.

Use SGD with every record setting and explicit constant learning rate, no scheduler, foreach/fused/maximize/
differentiable paths. Weighted elementwise BCE-with-logits + bin cross-entropy includes all admitted examples,
including no-obstacle; mean each batch for its update. Selection is eval/no-grad on canonical selection batches,
with scalar equal-example mean via math.fsum, no optimizer mutation. Only listed evaluation epochs are eligible;
strictly smaller selection loss replaces checkpoint, exact ties retain earliest epoch. Record fit/selection loss,
counts, actual updates, sample-order digest and selected epoch. Check finite inputs, both logits, per-example
loss, reduced loss, gradients, parameters and SGD buffers; any failure aborts, no previous/random-weight fallback.
Use detached selected float32 CPU clones; checkpoint memory is subject to the actual worker limit, not exempted.

### Safe development artifacts for4c

No torch.save/load, pickle, NumPy object arrays, executable payload or optimizer resume format. Produce deterministic
`weights.f32` (concatenated sorted-name little-endian contiguous float32 bytes), `weights.json` (closed schema,
names/dtype/shapes/offsets/lengths/per-tensor hashes, raw blob digest and canonical named-descriptor digest), and
`training-report.json` (job/stage/source/dataset/preprocessing/environment identities, class order, architecture,
settings, counts/order/loss/checkpoint/initial-versus-selected weight identities). The report binds both weight
file identities; no report/model self-digest cycle. Source paths, host timings, process IDs and temporary names
stay outside deterministic report fields. These are development outputs, not calibrated/frozen/U4-ready models.

The stdlib weight reader verifies exact closed descriptors, stable unique names, required float32 dtype, positive
bounded shapes/counts/contiguous offsets/exact byte length, all hashes, finite values and expected job-derived
parameter names/shapes before any tensor creation. It returns private safe bytes/descriptors;4c reconstructs only
the admitted architecture. Bound JSON/blob allocations and totals. Output is a fresh directory created only for
successful selected results, with exclusive regular writes and cleanup on write failure; no overwrite/resume and
no candidate publication marker. Output cap includes all descriptor/report bytes, not weights alone.

### Verification plan and maturity

Write stdlib tests for separate source binding/job mismatch, malformed-before-framework refusal, stable seed/
identity order, equal-example aggregation/earliest-tie logic, safe-weight roundtrip/tamper/dtype/name/shape/offset/
nonfinite/huge-int/resource refusal, no pickle/runtime imports and admission partitions. Write genuine framework
worker cases for real synthetic label/store/manifest inputs, actual shared preprocessing/optimizer updates, exact
shape/class/partition handling, finite failure and fresh-process repeat digests; no mocked successful training.
Those cases remain unexecuted until root supplies the heavy slot and genuine isolated environment.
Only AST/compile-without-bytecode and tiny stdlib probes run now. Full4c export/ORT,4d calibration/freeze and4e
complete repeats stay separate and blocking. Real-model/scientific/calibration/#7/AD27 acceptance is not implied.
FR005/V03 partial implementation; FR021/V14 and FR028/V21 offline boundary remain partial pending composition;
FR024/AD27 deferred; FR034/#5 separate. Preserve accepted pipeline REF002 allocated/needs-clarification statuses.

## Finding 2: separate pre-verification source review (2026-10-24)

Before repairing: first candidate checks actual pinned framework origins but only filters site-packages paths;
an extra non-site search path could shadow a dependency. Tighten to the actual standard-library/zip/dynload paths,
admitted training site, owned blueprint import root and actual shared-compat source root. Refuse all other entries,
including relative/empty roots. This is dependency-origin hygiene for the owned launch, not arbitrary-code isolation.
Also require the admitted4a/4b/preprocessing source and environment identities unchanged after fitting and before
output writes; a start-only tree hash does not support a whole-stage unchanged-input claim. Recheck the actual
network namespace too. Do not claim hostile mutation immunity: source/environment files remain trusted immutable
inputs, not descriptor-frozen imported code. Final full pipeline isolation/repeat checks remain4e.

The same read-only pass checked actual pinned torch SGD signature (source only, no import): supports explicit
maximize/foreach/differentiable/fused flags used here. Identified fixture/API typo and a no-op tamper byte in draft
tests were corrected during initial writing before this review. The pre-repair stdlib pass performed33 small
controls with genuine label/store/manifest admission and safe-weight corruption cases; no pytest/framework.

## Finding 3: safe weight consumption needs an external expected pin (2026-10-24)

Before repairing: decode checks internally consistent hashes/job/stage and the exact non-executable shape/finite
contract, but read_weights accepted its co-located descriptor's hashes as the only file pins. That proves structural
consistency, not correspondence to the selected weights named by a separately hash-bound training report. Make
read_weights require expected descriptor/blob digests from the caller's admitted report/input binding and check
those before decoding.4c must independently admit that report's expected digest; a mutable co-located report is
not an identity source. Keep the lower-level decoder as bounded structural validation of supplied bytes, and use
it on freshly generated own bytes before writing. Add a public-reader case replacing both descriptor and blob with
a different structurally valid/rehashed package: unchanged external expected report pins must still refuse.

## Finding 4: completed source candidate and performed checks (2026-10-24)

Implemented only the four designed offline modules and separate stage binding. Final four-module closure is
`009804472ccd52670758bd9ee21595a4f9520c47e85dda770d3f3420a692c6eb`;
unchanged4a closure is `d83ba1f5e7ce1056d82a924157aad617d64db84862e4be4005abf47fcf1a3e32`.
Actual job/location/source/namespace/environment admission precedes framework imports. Exact record-driven network,
owned sorted uniform initialization, explicit CPU SGD, seeded metadata-order streaming batches, all-example loss,
selection-only checkpoints, finite guards, actual engineering memory/file/timeout limits and named float32 artifacts
are source-complete. Start/end code/preprocessing/environment checks and namespace stability precede output.
External expected descriptor/blob pins prevent a valid but different co-located weight package satisfying an
unchanged admitted report. No unchanged-input/hostile-source attestation beyond the stated immutable-input scope.

Coordinator confirmed purpose separation: unchanged4a reads/verifies all partition frames for bounded admission;
4b preprocessing/fit/checkpoint computation reads fit/selection respectively. **No zero-held-out-I/O claim.**
The genuine driver rebinds actual held-out bytes/labels/manifest/job, not just a fake wrapper, and must show identical
fit order/epoch losses/checkpoint/named weights. Initial calibration/test byte integrity never selects model state.

Checks actually performed:53 tiny stdlib controls across four passes (33 initial admission/order/loss/weight/
corruption/output/public-refusal checks,5 import-path/output-cleanup checks,11 genuine integration-fixture
preparation/admission checks,4 external expected weight-pin checks). Actual source metadata only from the existing
training identity/lock was read; no environment tree walk or framework import occurred. Final source/tests compile
with compile()/AST without bytecode; current whitespace diff and unchanged4a source comparison pass. One new
allowlist probe initially omitted stdlib from its simulated sys.path and failed while sysconfig imported its own
stdlib data; the fixture was corrected, and the5-control successor passed. No production fallback was added.

Written but **not run**: owning pytest suite and genuine driver (three successful fresh isolated fits plus one
nonfinite refusal). Actual two-head torch construction, uniform/SGD APIs and updates, peak resource feasibility,
pinned import-tree stability, fresh-process bit identity, genuine held-out invariance and refusal behavior are
unverified runtime hypotheses pending the coordinator's queue. Source checks are not those results. No training,
NumPy image execution, export/ONNX/ORT import, download, factory/C1/live operation, acceptance, merge or4c work.

Next gates: parent4a suite/acceptance; independent4b source review; coordinator-admitted genuine worker driver and
owning suite; then separate reviewed4c export/raw-logit worker.4d/4e/#5/#7/AD27 and real scientific choices remain
open. Keep this exact candidate pinned for review; no running queue is silently retargeted.

## Finding 5: independent source review — changes requested (2026-10-24)

Independently reviewed exact candidate `03987de1542d542b05b6fd2ddcfd314dd09c953d`, pre-code design `7571b13`,
pre-repair findings `9ec494f`/`aad1711`, both contracts, all four product modules, the owning stdlib tests and the
genuine driver against accepted pipeline `a89a52e`/DN1–7. The worktree was clean and the candidate remained pinned
through this review. Direct physical location is loop10 `codex-20261024/worktrees/xverse-blueprints/phase8-wp09-training4b-20261024`.
Thesis freshness fetch succeeded; HEAD/upstream remain `d97fdd1167bbd48b97aad5d4071ad59403665f42`, no incoming note
change, working canonical-note blob `ba244ddb7df388386455524ab7667d4a1e86d5a3` unchanged from fully read context.
Dirty thesis files were preserved. Sol/high is an informational task-based recommendation for this admission/
determinism review, not a model switch or benchmark.

### R4b-1 — MAJOR: timeout/interruption loses available worker evidence

`tests/training4b_integration.py:71–79` writes `worker.stdout`/`worker.stderr` only after `subprocess.run` returns.
On `TimeoutExpired`, available partial captured output is attached to the exception, but this driver does not
persist it. Interruption or other launch/capture exceptions likewise bypass these files. It also records no
per-attempt exact child command, actual terminal status/timeout or capture failure. A top-level driver traceback
is not a retained worker stdout/stderr record. This conflicts with the contract's explicit command/status/output
retention requirement and leaves the decisive failed genuine verification difficult to audit.

A tiny stdlib-only control extracted the actual `run` function by AST and supplied a controlled `subprocess.run`
that raises `TimeoutExpired` containing distinct TEST-ONLY stdout/stderr. The exception propagated and neither
worker output file existed. No unshare, interpreter worker, framework or real training was executed by this probe.

Recommended repair: design and implement an owned per-attempt supervisor that creates fresh diagnostic artifacts,
retains actual command/status/timeout/error and partial stdout/stderr on all supported terminal paths, and refuses
success after capture failure. Preserve failures without synthesizing successful framework receipts, overwriting
existing attempt outputs or turning an unavailable namespace into a pass. Keep diagnostics outside deterministic
weight/report bytes and use explicit engineering bounds rather than inventing scientific values.

### R4b-2 — MAJOR: the verification timeout does not establish owned descendant cleanup

The same `subprocess.run` call starts no fresh process group/session and checks no descendant completion. Its
POSIX timeout implementation kills and waits for the immediate child; a descendant created during the actual
framework invocation can survive. A descendant retaining the captured pipes can also prevent an otherwise
exited leader's communication from completing until the watchdog fires. The worker's own Python alarm does not
establish process-tree termination. A fresh user/network namespace is not a PID namespace or descendant cleanup.

This is a source-control-flow finding, not an observed training leak: no genuine framework process was launched
in this review. The genuine driver is the proposed owning verification path, so this gap must be resolved before
its execution is counted. The parent accepted both driver findings for a separate pre-code supervisor repair;
the four product modules and unchanged4a closure need not change for that repair.

Recommended repair: establish cancellation-safe ownership of a fresh group, use bounded TERM/KILL plus group/
leader completion checks on timeout, interruption and spawn/capture failure, and record incomplete/unknown cleanup
as refusal. Waiting only for a leader is insufficient; ensure cancellation during actual process construction
cannot lose ownership. Test normal completion, nonzero refusal, timeout with a TERM-ignoring descendant, interruption
and spawn failure using tiny processes before scheduling real training. Do not claim to control descendants that
deliberately escape the owned group or silently convert incomplete cleanup into success.

### Product/source boundaries independently confirmed

The exact named4b closure recomputes to `009804472ccd52670758bd9ee21595a4f9520c47e85dda770d3f3420a692c6eb`.
The three-module4a closure recomputes to `d83ba1f5e7ce1056d82a924157aad617d64db84862e4be4005abf47fcf1a3e32`;
its files are byte-unchanged from `5244fbd`. Stage/job identities remain separate. Actual closed job/location/
stage/source/dataset admission, fresh-worker/netns/cache checks and actual environment identity/lock/tree/origin
checks precede lazy numpy/torch imports. Source/preprocessor/environment and netns stability are rechecked before
output. These checks retain the documented trusted immutable-input limit and do not authenticate hostile code.

The CPU float32 Conv/ReLU/GAP/Flatten/two-head construction consumes record settings, checks names/shapes/count,
and overwrites parameters in sorted order using the independent initialization-seed generator. All SGD settings
and framework/data-order seeds are explicit. Every admitted fit example contributes weighted BCE logits and bin
cross-entropy; data order is identity-hash based; final short batches remain. Checkpoint inference is no-grad on
selection only, loss aggregation weights examples equally, and exact ties retain the earliest declared epoch.
Finite guards cover inputs, logits, loss, gradients, parameters, optimizer tensor state and emitted weights.

**All-partition integrity admission is allowed and preserved.** The unchanged4a consumer verifies calibration/test
bytes and coverage before fitting. The4b fit path requests only fit samples, and checkpoint computation requests
only selection samples. No calibration/test frame enters shared preprocessing, forward, optimization or checkpoint
selection in this increment. This is not a zero-held-out-I/O claim. The driver genuinely rebinds held-out pixels,
label raw hashes, manifest and job before its intended weight-invariance comparison.

The development artifact has explicit sorted float32-le tensors, closed descriptors, exact job-derived names/
shapes/ranges, finite values, external expected descriptor/blob pins and no pickle/object serialization. A different
internally consistent package fails unchanged external pins. Fresh output checks/aggregate byte limits/fsync and
own-file cleanup are present; final atomic candidate publication is still4e. Runtime imports remain separate.
No further product-source blocker was identified, but this is not a demonstrated optimizer/environment result.

### Checks actually performed and deferred gates

Independent stdlib probes at external `codex-20261024/scratch/review_wp15/training4b-review-probes.py` completed
ten control groups: exact closures; valid/three invalid separate-stage cases; genuine owner-produced label/store/
manifest admission with requested-fit order and duplicate/foreign refusals; deterministic order/equal-example/
earliest-tie controls; named shape/count/private safe-weight roundtrip; six typed/rehashed/nonfinite corruption
refusals; valid-package replacement refused by unchanged external pins; fresh/aggregate-limit/no-overwrite outputs;
the driver timeout evidence-loss witness; and absence of torch/numpy/ORT imports. One initial independent harness
run omitted its synthetic `args.lock` locator and failed before the timeout seam; correcting that harness field
produced the stated witness without a product change. Both source/tests parse, and whitespace/unchanged4a checks
pass. All new scratch/temp files were on loop10; tiny fixture directories were removed by their owning context.

No pytest, framework import, actual namespace worker, environment-tree walk, training/export/calibration/ORT,
download, factory/live run, acceptance or merge was performed. After independently reviewed driver repair, root
still schedules the owning `test_training_admission.py`/`test_training_fit.py` suite and genuine four-case driver
with actual admitted environment and explicit engineering bounds. Parent4a owning verification/acceptance,
actual4b repeated fitting/held-out invariance/nonfinite refusal, then4c–4e and all scientific/AD27 gates remain
pending. This finding records required repairs before code; it grants no execution or implementation acceptance.

## Finding 6: driver supervisor repair design before code (coordinator, 2026-10-24)

Accept R4b-1/R4b-2 in independent review-onlya20aeeb. Preserve every byte of the four product modules and the
three4a modules. Repair only the verification driver and its explicit stdlib supervisor controls. No framework,
pytest or actual training execution is authorized by this design. Sol/high is appropriate for independent
cancellation/evidence review; no model switch, benchmark or scientific parameter is selected.

Use a fresh owned session/group per worker with stdout/stderr streamed directly into exclusive attempt files.
Reserve the receipt before spawning; capture actual command, selected explicit environment, input-before/after
hashes, driver identity, parent namespace, actual exit/timeout/error, elapsed host time, output hashes and bounded
group cleanup. Keep this diagnostic record outside deterministic learned weights/reports. A capture failure,
timeout, input change or incomplete cleanup is never the expected nonfinite model refusal. Expected refusal
still needs actual nonzero worker exit, correct retained refusal diagnostic and no trained output.

Defer throwing installed cancellation handlers during Popen construction until the actual handle is assigned;
do not inherit a blocked termination mask into the worker. After assignment, always finalize ownership, including
interruptions and spawn/capture failure. TERM then KILL the owned group with separately supplied positive finite
engineering cleanup bounds; check group disappearance and reap the leader. A leader exit alone is insufficient.
Block repeated interruption during bounded cleanup/receipt persistence, then restore prior handlers/mask. A child
deliberately escaping the group is outside this trusted-owned-worker claim; make no hostile-tree-containment claim.
I/O failure may prevent a durable receipt: preserve partial files and fail, never overwrite or synthesize one.

Require explicit --cleanup-term-seconds and --cleanup-kill-seconds alongside the existing --timeout. Test tiny
normal/nonzero children, real partial diagnostics on timeout, a TERM-ignoring descendant with retained leader,
the actual spawn-assignment interrupt seam, post-assignment interruption, missing executable and no-overwrite.
Controls may use short explicit TEST-ONLY bounds and fork/subprocesses, with independent cleanup; they must not
launch frameworks or manufacture successful training receipts. A separately reviewed successor and actual owning
suite plus genuine isolated fitting driver remain mandatory before implementation acceptance.

## Finding 7: supervisor-only repair candidate and performed controls (coordinator, 2026-10-24)

Implemented the finding6 design only in the explicit integration driver, its new stdlib supervisor and controls.
Each attempt exclusively reserves diagnostics/receipt, streams real output, records actual command/environment/
input identities and terminal result, defers cancellation until spawn ownership is established, and performs
bounded TERM/KILL/group disappearance/reap checks. Expected nonfinite refusal requires complete capture plus
actual nonzero exit/diagnostic/no output; timeout/error/drift/incomplete cleanup cannot count. Added required
explicit engineering cleanup bounds to the CLI/contract, without a scientific value or fallback.

Actually ran seven unittest controls (stdlib only) in4.601s, rc0. They cover real stdout/stderr and normal/nonzero
exit, retained partial diagnostics on timeout, real child-created/pre-assignment SIGINT, post-assignment SIGTERM,
missing executable/input drift, no-overwrite without spawn, and timeout with a real TERM-ignoring descendant
requiring KILL/group disappearance. The last control uses a temporary harness-only Linux subreaper, reaps its
owned descendant and restores prior state. This is not a C1/namespace/training test or hostile-session proof.
Evidence `docs/evidence/training4b-supervisor-controls-20261024.json` retains actual command, tool terminal fragment,
exit and source hashes; earlier individual status lines are in the tool transcript, not claimed as a full file log.

All four product modules and all three4a files are byte-identical to reviewed03987de. Current training test
sources compile without bytecode and whitespace checks pass. No framework, pytest, real unshare worker, tree
environment scan, training/export/calibration/live work, acceptance, merge or4c execution occurred. Independent
successor review, parent4a acceptance and actual isolated owning/genuine-driver verification remain pending.
