# WP-09 training 4a: strict admission and bounded dataset reads

Candidate `candidate/phase8-wp09-training4a-20261024`, from accepted isolated integration
`12bc7464f7c3103f3beba34c040ac5c4afc2b9d4`. Sol at high reasoning is recommended for the closed-input and
resource boundaries. This is offline source engineering only; no training, export, calibration, publication,
framework import, live data collection, scientific value, acceptance or merge is supplied.

## Finding 1: detailed implementation design before code (2026-10-24)

Read accepted design `a89a52e`, its entire `review-wp09-training-pipeline.md` findings1–5, and thesis
`decisions.md` "WP-09 #4 pipeline methods". The accepted design and its historical input-hash record are copied
byte-exact, with explicit origin/base/file hashes in `evidence/wp09-training4a-design-provenance.json`; no older
design-branch baseline is merged. Fresh thesis fetch leaves HEAD/upstream `d97fdd1`, no incoming note change,
and working canonical note blob `ba244ddb`, previously fully read. Preserve all thesis/main dirty files.

Implement only standard-library `perception/training_record.py`, `training_io.py` and `dataset_consumer.py`.
No torch/numpy/onnx/ORT import, tensor allocation or output directory is introduced. Existing shared compat
preprocessing parameter/binding validation is consumed lazily with an explicit numpy version; its module is
stdlib at import and no image conversion is called. Runtime modules never import these offline modules.

### Closed records and pre-framework checks

`TrainingJob.from_bytes(data, max_record_bytes=...)` requires bounded canonical UTF-8 JSON bytes and exact closed
records, with duplicate keys, nonfinite/unrepresentable numbers, booleans as integers, unsupported Python values,
cycles and unknown/missing members refused. The external byte cap is an admitted engineering input, not a default.
Private copies prevent a caller changing admitted records. `code_digest()` names the three new module files;
the job must bind the running closure. Every future framework-affecting method/number is validated now:

- Top-level `schema=assured-aeb.training-job/1`, `identity`, `dataset`, `separation`, `trainingPartition`,
  `preprocessing`, `architecture`, `optimisation`, `calibrationFit`, `oodFit`, `verification`, `environments`.
- Identity: candidate id, synthetic-verification/development-training purpose, code closure digest and digest of
  dataset/separation/preprocessing inputs. Dataset: manifest/source-index digests, embedded label-parameter and
  frame-format records with canonical digests. Separate actual source files must reproduce those embedded records.
- Separation: embedded `assured-aeb.training-separation/1` record/digest, exactly the five P-4 category lists and
  evaluation section set. Seeds are sorted unique uint32 values (representation compatibility with numpy/torch
  seed APIs, not a selected seed). All lists nonempty/pairwise disjoint. Partition: sorted nonempty fit/selection
  run lists, disjoint; exact training-run coverage and disjoint actual seeds checked against the manifest.
- Preprocessing: existing record/digest, expected existing source digest and explicit numpy version. Validate
  the genuine shared function's parameter contract, input format/camera agreement and binding without numpy import.
- Architecture: distinct named input/occupancy/bin outputs; nonempty ordered dense Conv/ReLU blocks with explicit
  output channels, 2-D kernel/stride/padding/dilation and bool bias; explicit head biases; uniform initialization
  method and finite ordered bounds. Derive positive spatial sizes, fixed three input channels and class order
  `no-obstacle, overlap, bin-0..bin-(N-1), beyond` from actual edges. Derive parameter/activation counts; enforce
  supplied engineering bounds, including float32 representability of initialization bounds.
- Optimisation: SGD only, explicit positive epochs/batch/rate and nonnegative momentum/dampening/weight-decay,
  Nesterov bool with its momentum/dampening constraints, two positive loss weights, CPU/zero workers, positive
  CPU thread counts, explicit uint32 torch/numpy/data-order/initialization seeds and deterministic-algorithms true.
  Selection epochs are ordered unique within training, method minimum-selection-loss/earliest-epoch ties and
  equal-example weighting. Calibration: delegated method/reference, sorted unique positive occupancy/bin
  temperature grids, calibration-only/equal-example NLL and smallest-temperature tie policy. OOD: delegated
  max-probability/nearest-rank, explicit `0<q<=1`, calibration population and strict-greater comparison.
- Verification: explicit nonnegative absolute/relative raw-logit/probability tolerances, decision agreement in
  [0,1], exact-repeat count at least the already accepted two complete repeats, all-admitted sample selection,
  independent scalar/direct-numpy reference sample bound, per-partition per-class/negative minima, required
  nonnegative NLL/Brier/false-alarm acceptance values and explicit occupancy >= threshold/reference. These are
  validated future inputs only, never measured or described as accepted scientific thresholds here.
- Environments: exact training/U4 identity/lock/source revision digests plus explicit absolute interpreter/site
  locations; explicit positive engineering record/source/compressed/raw-frame/sample/model-parameter/tensor/
  epoch/batch/memory/disk/output-byte limits and worker timeout. No interpreter or environment tree is opened.
  Cross-check configured batch/epoch/model/input sizes against these limits before any future framework import.

The exact member sets and supported method strings will be documented with the implementation; unsupported
variants are refused rather than partially interpreted. There is no scalar-distance representative rule or
corruption policy in 4a. All real values remain TODO; fixtures/probes populate explicit TEST-ONLY records.

### Source, label and partition admission

`SourceLocations.from_bytes` is a separate closed locator record: schema plus absolute paths for manifest,
label parameters, frame format, source index and separation, and an exact per-run map of scenario/labels/
observer/run-parameter paths and store roots. Paths are locators, never identities. Bounded nonblocking regular
file reads reject special files/final symlinks. Expected digests always come from the admitted job/manifest,
not a co-located mutable default. JSON sources reject duplicate keys and unsafe numbers; observer JSONL is
bounded as a whole. The closed canonical source index lists each manifest run's four existing source digests
and supplied recorder exclusion counts; it attests bytes only, not world-map or traversal truth.

Admission first verifies source identities and independently validates every supplied label before invoking
the genuine `check_manifest` with actual scenario paths/label lists; retain its reports and require no refusals.
Require exact current label/provenance member sets, bool flags and coherent obstacle conjunction, nonnegative
integer frame/time matching the held frame table, bare digests, positive observer line beyond the header,
and the actual referenced observer frame/time. Refuse duplicate/unknown label frames. Verify actual observer
and run-parameter bytes against manifest pins. Parse/check observer-v2 evaluation-only header and duplicate
frame identities; never silently use a different line. A target-absent scenario requires false/false/false/null/
no-obstacle labels; declared-target labels require finite distance. Recompute only existing distance bins with
the genuine `< edge`/overlap/no-obstacle semantics, not geometry. Rehashing malformed labels cannot bypass checks.

Repeat P-4 membership: training runs use training seeds, calibration uses calibration seeds and test uses
characterisation seeds; pilot/evaluation seeds never enter any of these. Manifest evaluation seeds/sections must
equal the nominated separation record. Fit/selection exactly partition training runs and are also seed-disjoint.
The /3 entire-run protected-section exclusion remains unchanged; test-section and allowed section-sharing
reports are retained. Frame tables are unique, ordered and nonnegative; corpus sample count is bounded.
Record per-run/partition/class counts, target-absent/adjacent-lane negatives and unlabelled stored-frame counts;
retain supplied recorder exclusions separately without assigning a guessed reason. Enforce only the explicit
coverage minima. Report recorder#6 obligations for actual source/world/map/traversal completeness as outstanding.

### Read-only streaming dataset

Return a private admitted dataset with `iter_samples(partition)` for fit/selection/calibration/test only. Each
iteration reads one content-addressed frame from the selected run's store. Validate actual existing absolute
root and no symlink shard/file; open read-only and never call writable FrameStore/sweep/create. Read at most the
explicit compressed-byte limit plus one refusal byte. zlib output is capped at expected BGRA length plus one
refusal byte, require EOF with no unused/unconsumed/trailing/concatenated payload, exact expected length and raw
SHA-256. This prevents a matching digest from excusing an oversized decompression. Return raw bytes plus private
label/target metadata to future shared preprocessing; no entire raw corpus or tensor is retained. Reverify bytes
on every iteration so a changed file fails visibly. Stored-but-unlabelled frames are excluded and counted.

### Verification and remaining gates

Use genuine `LabelParams`/`label_run`, FrameStore producer and manifest /3 interfaces for small byte-distinct
TEST-ONLY present/absent/lateral fixtures, with nonoverlapping fit/selection/calibration/test seeds and P-4 lists.
Tests target closed/duplicate/unsafe job and source inputs, all method/number constraints, mismatched digests,
malformed rehashed labels, observer line/frame/time mismatches, partitions/coverage, whole-run segment refusal,
bounded/truncated/trailing/concatenated/bomb/wrong-length/digest frame stores, read-only temp preservation,
private copies and forbidden runtime/framework imports. No pytest/heavy/framework/live execution until the
coordinator schedules it; direct stdlib controls, AST and diff checks only now.

FR-005/V03 remains allocated across 4b–4e/#7/WP-13; 4a implements input/consumer checks only. FR-021/V14 and
FR-028/V21 remain partial pending runtime/composition checks. FR-024/AD-27 freeze and real numbers remain
deferred; FR-034/#5 is separate. Keep the accepted design's REF-002 dispositions and recorder#6 truth limits.
No launcher, training/export/calibration worker, tensor, publication marker or generated scientific result is
implemented. Independent source review and actual owning/assembled suite gates remain before acceptance.

## Finding 2: bounded scenario snapshots before consumer implementation (2026-10-24)

The genuine `check_manifest` reopens each scenario using an unbounded `Path.read_bytes`. An immutable-input
assumption alone would not preserve the new consumer's read bound if a source changed before that reopen.
Keep the existing manifest API/product untouched. After a bounded regular-file source read and digest check,
create temporary validation-only scenario snapshots of those exact private bytes; invoke `check_manifest`
against those snapshots and actual private label lists, then clean the temporary directory automatically.
This is temporary engineering validation storage, not an output/candidate directory or publication. No original
source/store is written and no manifest evidence or source identity is substituted: snapshots are byte-identical
to the verified actual inputs. Bound each and the total snapshot sizes by admitted source/disk limits. Every
observer/label/run-parameter record is likewise consumed from a private bounded byte snapshot in memory.

## Finding 3: implementation candidate and bounded verification (2026-10-24)

Implemented the three stdlib offline modules after design `0a3840ca` and the bounded-snapshot amendment
`cf6a5c2`. The private closed job validates all declared methods, numeric kinds, seeds, model/convolution sizes,
initialization float32 representation and resource cross-checks; it binds the running named three-module source
closure. The dataset consumer checks actual source/label/observer bytes, observer frame/time/role status,
coherent label targets/bins, exact P-4/run/seed partitions, explicit coverage and the unmodified manifest /3 rules.
It preserves owner overlap reports and recorder exclusions separately from unlabelled counts. All labelled frames
pass a bounded streamed read-only verification before admission and are reverified on each iteration. JSON-safe
reports and label access return private copies; derived job scalars/tuples are read-only.

`training4a-contract.md` documents the exact member sets/method strings, identity and iterator contracts and limits.
The expected numpy version and environment identity/lock digests are declarations at this stage; actual pinned
framework/interpreter/environment verification belongs to 4b–4e. Shared compat `load_params` and `binding` are
called without importing numpy. No training worker, optimizer, export, calibration, tensor, publication directory
or candidate marker is implemented. Temporary validation scenario snapshots are cleaned automatically.

Tests use real `LabelParams`, `label_run`, FrameStore writes and manifest /3 producers for byte-distinct TEST-ONLY
present, absent and lateral targets, plus a genuine no-observer exclusion. Written regressions cover exact and
duplicate JSON, unsafe numeric representations, nested methods/fields/derived bounds, closed source locators/index,
rehashed malformed labels and observer status/line/frame/time, P-4/run/seed partitions, coverage, entire-run
protected sections and allowed test overlap, unsafe zlib streams/length/digest/size, missing/symlink/FIFO sources,
read-only temporary preservation, changed-on-next-read refusal, private state and runtime/framework import limits.

Final-source checks performed: **51 tiny stdlib controls passed**, including a genuine 12-labelled-frame admission
and streamed reads, all 25 declared method/numeric mutation controls, strict JSON, rehashed malformed labels,
source-byte mismatches, zlib length/truncation/trailing/concatenated/bomb/digest cases, protected-section and
seed-disjoint refusal, private state and nonblocking FIFO refusal. AST parsing of five new Python files and
`git diff --check` passed. A preceding separate tiny control also verified rehashed observer-target absence is
refused; the written tests include that case and duplicates/time. No pytest, numpy/torch/ONNX/ORT import, training,
simulation, live data collection, download or heavy suite was performed. All probe/fixture values are TEST-ONLY.

Queued owning validation from `automotive/assured-aeb`, only when the coordinator schedules the serialized slot:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 XVERSE_AEB_SENSOR_SITE=/dev/shm/xverse-aeb-sensor-20261024/venv/lib/python3.13/site-packages XVERSE_PLATFORM_PROFILES=/tmp/codex-xverse-review-20261024-q93eotxv/xdl/profiles /dev/shm/compat-p6-venv/bin/python -I -B -m pytest tests/test_training_admission.py tests/test_perception_labels.py -q -p no:cacheprovider --tb=short
```

Then run the complete owning/assembled blueprint suite and obtain independent source review. No acceptance or
merge by this worker. Recorder#6 source/world/map/traversal truth, 4b–4e framework execution/isolation and two
complete genuine repeats, #5 characterisation, #7 real-model quality and AD-27 numeric/scientific freeze remain
open gates. The accepted design's requirement/SADS dispositions are preserved; source admission is not a completed
model or scientific result. Recommend a DRAFT Note23 update after author approval linking the accepted method
decision and this engineering scope; do not change the canonical note automatically.

## Finding 4: independent source review, CHANGES REQUESTED (Codex, 2026-10-24)

Reviewed exact source candidate `c494dbe48c838cf12346a09f8f55e1380b23686f`, accepted pipeline design `a89a52e`
(byte-exact carried findings 1–5), 4a design `0a3840ca`, snapshot amendment `cf6a5c2`, the exact admission contract,
all three new modules, fixtures/tests and the genuine label/scenario/manifest/store/preprocess owner contracts.
The reviewer did not author 4a and makes **no source/test repair**. Thesis freshness fetch succeeded at HEAD/upstream
`d97fdd1`; no incoming canonical-note change, working-note blob `ba244ddb` unchanged from fully read context.
Sol/high remains appropriate for narrow integrity/resource/I/O repairs and independent successor review.

### R4a-1, MEDIUM: actual pinned source records are checked with lossy Python equality

`dataset_consumer.py:192–194` compares parsed actual labelParams/frameFormat/separation with embedded admitted
records using `==`. Python considers integer 4 equal to float 4.0 (and also some booleans equal to integers), while
the declared identities are digests of canonical JSON and the owner contracts require exact integer fields/seeds.
The actual source does not have to reproduce the expected canonical-record digest or its exact typed record.

Three separately reproduced TEST-ONLY genuine-fixture cases, with **no job/expected-pin rewrite**:
- Change only actual label-parameter source `camera.width` from integer 4 to float 4.0.
- Change only actual frame-format source `width` from integer 4 to float 4.0.
- Change only actual separation source training seed list from `[10,11]` to `[10.0,11.0]`.

Each actual canonical digest differs from its admitted `labelParamsSha256`, `frameFormatSha256` or separation.sha256.
The genuine typed parameter/seed contract would refuse those types, but complete dataset admission still succeeds
and reports the original pinned record identity. Embedded job validation and frame reads remain otherwise valid;
this is a source-record identity/type gap, not a SHA-256 collision or a geometry-truth claim.

**Required disposition before repair:** bind each private actual parsed source to its expected canonical-record
identity (and preserve exact typed semantics), then consume the verified record. Do not replace pins with the newly
observed digest or accept Python numeric equality as byte identity. Canonical-record identity differs intentionally
from raw observer/run-parameter/scenario byte identity; preserve those existing owner contracts. Add decisive tests
where a mathematically equal, differently typed/re-encoded record has the wrong canonical digest, including these
three source roles; an ordinary unequal-value mutation alone does not exercise this bug.

### R4a-2, MEDIUM: model parameter storage can exceed admitted memoryBytes

`training_record.py:209–210` checks parameter count and its float32 byte size against modelParameters/outputBytes;
237–238 checks peak activation/batch bytes against memoryBytes. There is no necessary memory check for the model's
parameter storage itself. A valid record can pass every current size check yet be unable to hold its weights within
the declared memory budget even before gradients, optimizer state or other runtime overhead.

Concrete TEST-ONLY genuine-fixture mutation: one output channel, kernel `[99,99]`, padding `[49,49]`, existing
stride/dilation/bias and two heads; modelParameters=100000 and memoryBytes=50000. Positive static dimensions and
small activations remain valid. Admission derives 29416 parameters, needing **117664 float32 bytes > 50000**, yet
both TrainingJob.from_bytes and full dataset admission succeed, including source-snapshot accounting and all real
frame checks. No framework/model allocation was executed; this is a pre-framework budget contradiction, not an
observed OOM or estimate of PyTorch process RSS.

**Required disposition before repair:** derive/check at least necessary weight-memory storage against the supplied
memory bound before a future framework import, and document the boundary between these necessary static checks and
later actual gradient/optimizer/framework/process memory enforcement. Do not claim that one peak activation alone
bounds full training memory. Any stronger accounting policy must be explicit/reviewed; do not invent a safety factor
or scientific resource value. Include a parameter-dominated case where activation/input checks still pass.

### R4a-3, MEDIUM: no-symlink shard guarantee has a directory check/open race

`training_io.py:130–134` checks root/shard with `Path.is_dir/is_symlink` and then opens a full pathname via
read_regular. O_NOFOLLOW there protects the **final frame file**, not intervening directories. A root/shard can be
replaced by a symlink after its check and before that open, and the reader follows it.

The independent deterministic probe uses only a fresh temporary 64-byte-frame store. At the boundary immediately
before read_regular's real open, rename the checked shard and install a symlink at its old name to that renamed
directory. read_frame returns the genuine raw bytes while the traversed shard is now a symlink. This changes no
checkout, never accesses a real cache and uses no timing race/thread. Existing digest, exact-length, zlib completion,
regular-file, compressed/raw bounds and nonblocking checks remain effective: the probe **does not** demonstrate
wrong-digest bytes, a decompression-limit bypass or a FIFO hang. It disproves the advertised no-symlink path contract.

**Required disposition before repair:** traverse/open the admitted existing root and digest shard with directory
file descriptors and no-follow/type checks, opening the final file relative to that pinned directory; use equivalent
race-resistant semantics if a different mechanism is selected. Do not create/sweep/write stores or widen path trust.
A deterministic check/open substitution regression must be refused or remain rooted at the already admitted real
directory without following the replacement. Keep all existing per-read content/size/stream checks.

### Positive review, actual checks and carried limits

Closed canonical job/source-locator JSON refuses duplicate/unsafe/nonfinite/unknown fields; explicit future methods,
seeds, scalar domains, positive convolution dimensions, class order, exact fit/selection run coverage, P-4 membership,
whole protected-section training/calibration refusal and held-out split/seed rules are present. The shared genuine
preprocess parameter/source binding is used without importing NumPy. Calibration/OOD/method/quality fields remain
future-stage declarations, not measured evidence or a scientific value choice.

Consumed labels have closed shape/provenance, exact bool/int flags, actual observer-line/frame/time/status binding,
coherent obstacle conjunction and distance-bin semantics. Hashing redefined labels does not excuse these independent
checks. This does not replay original geometry or prove recorder#6 world/map/traversal/actual-seed truth. Supplied
recorder exclusions stay distinct from unlabelled counts. Private public-access copies protect admitted reports,
labels/job records and derived tuple/scalar properties; this is an API immutability observation, not language-level
security against deliberate private-attribute mutation.

Source reads use bounded nonblocking regular-file descriptors; scenarios passed to the genuine unchanged manifest
validator are exact private temporary snapshots. Raw frames are streamed and revalidated at every iteration, with
bounded compressed input, capped decompression, exact length/hash, EOF and no trailing/concatenated stream. No store
writer/sweeper is invoked by the consumer. R4a-3 concerns directory resolution only, not those effective checks.

**Actual independent checks:** the five counterexamples above reproduced all three findings (three source-role
identity cases, one memory case, one directory substitution). Thirteen separate tiny stdlib controls passed: genuine
12-labelled-frame admission/all partition reads, detached report/job access, rehashed integer obstacle refusal,
wrong observer-line refusal, whole-run protected-section refusal, truncated/trailing/concatenated/oversized-output/
short zlib refusals, changed-file next-iteration refusal and immediate nonblocking FIFO refusal. One initial control
script stopped because its own fixture-restoration dictionary shared nested provenance with the saved copy; that
harness was corrected to deepcopy on restoration, then all 13 completed. No product/test source was changed to make
the probe pass. Five Python AST parses and `git diff --check` passed.

No pytest, NumPy/torch/ONNX/ORT import, durable Argus, training/export/calibration, environment-tree hashing, simulator,
download, factory or live work occurred. Existing claimed 51 controls are the author's evidence, not rerun/claimed
as this review's suite. Owning/assembled tests remain deferred to the recorded coordinator schedule. Design-before-
repair, independent successor review, acceptance/merge, 4b–4e genuine execution/two repeats, recorder#6, #7 and AD-27
scientific gates remain open. This review accepts, merges and repairs nothing.
