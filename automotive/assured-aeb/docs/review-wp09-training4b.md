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
