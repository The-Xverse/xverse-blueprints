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
