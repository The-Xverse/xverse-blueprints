# Training4b development fit contract (candidate; framework verification pending)

Read accepted pipeline `review-wp09-training-pipeline.md` and `review-wp09-training4b.md`. This increment adds
only offline CPU fitting and development weights. It does not export ONNX, fit calibration, publish a frozen
model, admit factory/live execution or supply any real scientific parameter. Parent4a verification/acceptance,
independent4b review, genuine isolated training and later4c–4e remain gates.

`training_worker` and its dependencies import no framework at module import. `run_training` reparses actual
job/location/stage bytes, validates the fresh worker/paths, enforces explicit engineering process limits, admits
the genuine dataset and verifies the environment before numpy/torch imports. It is a one-shot fresh worker API:
limits/thread settings are process-wide. Do not call it in a test runner, runtime process or ORT interpreter.
The owned launcher must start actual `unshare -rn` with the admitted real interpreter, `-S -s -B`, explicit training
site plus owned blueprint/compat import roots and actual parent net/user namespace proof captured before exec. No namespace
facility means refusal, never a plain-process fallback. `TMPDIR` and all four cache environment roots
`XDG_CACHE_HOME,TORCH_HOME,TORCHINDUCTOR_CACHE_DIR,TRITON_CACHE_DIR` must explicitly exist under that scratch root.
All new invocation artifacts/cache/scratch must be on the author's admitted external storage.

Finding12 accepts `training4b-namespace-proof-design.md` as the namespace repair design. The genuine launcher owns
read-only non-inheritable original net/user namespace handles across capture/cleanup and explicitly passes exactly
those two with close_fds=True/pass_fds. Required --parent-namespace-proof is the closed canonical operational record
with original parentPid and net/user fd/device/inode/actual-reference fields. Child NS_GET_NSTYPE and fstat compare
actual inherited identities with observations and with its own typed net/user identities, requiring both differ,
original parent, UID0 and loopback. No parent-proc traversal, network-owner=user-parent inference, guessed text,
plain-process/-cn fallback or optional successful proof. Unsupported reviewed Linux/x86_64 ABI/ioctl refuses.

Only declared actual typed namespace descriptors are adopted; unrelated file/pipe/socket/std descriptors are never
blindly closed. Every adopted child handle closes on success/refusal before environment verification/framework
imports; the outer CLI context closes them on bad file/job/stage admission. Unvalidated descriptors stay with their
caller, and an early failed CLI process exit closes its inherited copies at the kernel boundary. Idempotent owned
file-object close cannot close a later reused descriptor number. Own net/user/UID0/loopback stability is rechecked
before output. Generic supervisor controls may use empty pass_fds, but genuine driver/worker proof is mandatory.
FD/PID/ns observations are operational-receipt data only; no learned report/weight field is added. The actual
four-module4b closure rotates with this worker change; no existing stage/failure is silently repinned.

4a is byte-unchanged. Its TrainingJob/1 closure still names training_record/training_io/dataset_consumer only.
Separate canonical stage record is exactly:

```json
{"jobSha256":"<actual job bytes SHA256>","schema":"assured-aeb.training-stage4b/1","sourceClosureSha256":"<actual named four-module closure SHA256>"}
```

Placeholders are documentation, not accepted values. `training_worker.code_digest()` computes the ordered named
closure over training_network.py, training_weights.py, training_loop.py, training_worker.py. Every report and
weight descriptor binds actual job and stage byte identities. No job input field is widened or silently repinned.
The actual compat identity and lock are operational file locators; bytes must reproduce job environment pins.
CPU/interpreter/libpython/stdlib/site/venv trees and actual import search paths are verified before/after fit.
This consumes the genuine compat identity format; it does not re-run its installer or activate its .pth hooks.
Namespace/source/preprocessor stability is rechecked before output. Environment files are trusted immutable inputs;
these checks are not hostile-file mutation protection or a new environment attestation service.

The CPU float32 network has named `features.conv_<index>`/`relu_<index>` blocks, GAP/Flatten, occupancy_head and
bin_head. Parameter specifications are derived by stdlib `training_network.parameter_shapes(job)`; actual model
names/shapes/count must match. Uniform initialization uses the explicit bounds and a separate initialization-seed
CPU generator in lexicographically sorted named order. torch/numpy/dataOrder seeds remain independently explicit.
All SGD settings come from the job, with constant rate, foreach/fused/maximize/differentiable disabled. BCE logits
plus bin cross-entropy use both explicit weights on every example. Checkpoints use only declared selection epochs,
equal-example weighted loss and earliest-epoch ties. Selection never updates weights; calibration/test never enter
preprocessing or fitting. Admission may verify their bytes and coverage. All nonfinite data/logits/loss/gradient/
weights/SGD tensor state refuse the stage.

Data order is sorted by SHA256(canonical({seed,epoch,sample:{runId,frame,rawSha256}})), with canonical sample bytes
as the deterministic collision tie-break. The sample-order report hash appends canonical `{epoch,sample}` plus
one newline for every fit example actually requested. Only metadata identities and one raw/tensor batch are held.
To preserve4a's streaming-only API, a fit batch rescans/revalidates that iterator until its requested identities
are found, then reorders them. Worst-case reads are quadratic per epoch; no throughput claim is made. Selected
weights are detached CPU clones. Actual memory/timeout enforcement can refuse a job above4a's necessary floor;
that floor excludes process/allocator/backward/checkpoint peaks. No memory safety factor or grace is invented.

A successful stage writes a fresh directory containing exactly weights.f32, weights.json, training-report.json.
No existing output is overwritten. Total bytes including JSON must fit both outputBytes and diskBytes, regular
files and directory are fsynced, and write failure cleans the worker's own fresh files/directory. This is not the
atomic final candidate publication of4e. Failure before write leaves no trained-output directory. No resume or
optimizer state is persisted.

weights.f32 concatenates sorted-name contiguous little-endian IEEE754 float32 tensors. weights.json has exact
`schema,jobSha256,stageSha256,weightsSha256,namedWeightsSha256,tensors` (schema assured-aeb.training-weights/1).
Each tensor is exactly `name,dtype,shape,byteOffset,byteLength,sha256`; dtype is `float32-le`; offsets are contiguous
from zero with no padding/trailer. namedWeightsSha256 hashes the ordered canonical descriptor list with only
name/dtype/shape/sha256. The report binds weight file hashes and every fit/checkpoint/input identity without a
self-hash cycle. It contains no host time, scratch location or raw pixels. `training_weights.read_weights` reads
bounded regular files and requires caller-supplied expected descriptor/blob SHA256 values. These come from an
independently admitted report/input binding, never an untrusted co-located file.4c must admit the report digest
itself. `decode_weights` provides structural checking of supplied bytes and verifies job-derived names/ranks/shapes, exact byte ranges, all hashes and
finite scalars before any future tensor construction. Neither pickle nor torch.save/load nor object arrays occur.
This is a development handoff for4c, not a calibrated or deployment-compatible artifact.

## Verification commands for coordinator scheduling only

Owning stdlib tests: run the repository's established blueprint pytest environment with
`automotive/assured-aeb/tests/test_training_admission.py automotive/assured-aeb/tests/test_training_fit.py`.
No pytest has been run by this worker. The explicit genuine driver is not collected automatically; it requires
actual identity/lock/interpreter/compat source and explicit TEST-ONLY engineering memory/disk/timeout arguments:

```text
<real CPython> -S -s -B automotive/assured-aeb/tests/training4b_integration.py
  --identity <actual pinned training identity.json> --lock <actual accepted training.lock>
  --python <admitted real CPython> --compat-source <accepted compat src>
  --scratch <fresh external scratch directory> --memory-bytes <explicit engineering bound>
  --disk-bytes <explicit engineering bound> --timeout <explicit engineering bound seconds>
  --cleanup-term-seconds <explicit engineering bound> --cleanup-kill-seconds <explicit engineering bound>
```

The driver itself needs only blueprint/compat/tests source roots on PYTHONPATH, no framework site. It launches
three successful genuine isolated workers (two exact repeats and one rebound changed calibration/test corpus)
and one genuine nonfinite-loss refusal worker. It checks actual weight change, exact named shapes/classes,
checkpoint choice, all deterministic bytes, unchanged weights under held-out pixel mutation and no output on
nonfinite failure. Retain command/status/stdout/stderr and exact source/environment/job/stage identities. Missing
namespace/environment is failed or unavailable verification, never a counted pass. No full4c–4e equivalence,
exporter/static-reader/ORT/calibration/final-loader success is implied by this4b driver.

Each attempt exclusively retains worker.stdout, worker.stderr and worker-execution.json before interpreting the
model outcome. Receipt includes actual command/environment, source/input hashes before/after, actual return code,
timeout/error and owned-group cleanup; diagnostics remain outside deterministic fit artifacts. Timeout/capture
failure/incomplete cleanup cannot satisfy the expected nonfinite refusal. Supervisor owns a fresh group with
bounded TERM/KILL and cancellation-safe spawn ownership. A leader exit is not descendant completion. This is a
trusted owned-worker group claim, not containment of deliberately escaped sessions. Filesystem failure may leave
partial diagnostics and always fails verification; existing attempts are never overwritten. No genuine training
result is implied by supervisor-only stdlib controls.

Expected nonfinite refusal requires actual Python exit1 and the final stderr exception line from ValueError,
RuntimeError or OverflowError whose message contains nonfinite/overflow, complete capture and no output path or
symlink. Negative signal exit, an earlier keyword warning followed by another exception, ordinary success and a
partial capture are refused as verification. The genuine fitting cases remain separately unexecuted.
