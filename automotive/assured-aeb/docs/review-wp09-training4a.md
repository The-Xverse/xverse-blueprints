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
