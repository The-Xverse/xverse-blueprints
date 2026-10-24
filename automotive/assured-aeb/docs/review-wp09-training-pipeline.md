# WP-09 increment #4: offline training, export, calibration and freezing

**DESIGN ACCEPTED under recorded engineering delegation, flagged for author review, 2026-10-24. No implementation or real-model acceptance.**
Branch `candidate/phase8-wp09-training-design-20261024`, base blueprints main `8bd0d34`.
The coordinator requested this design under the existing engineering delegation. Method proposals DN-1 to DN-7
below require its disposition before code. Numeric scientific values remain author decisions/measurements;
synthetic verification will supply explicitly TEST-ONLY records. No factory or live run is admitted here.

## Finding 1: current contracts and decisions, inspected before design

Input byte hashes and exact revisions are in `evidence/wp09-training-design-inputs.json`.

- Thesis `specs/002-assured-aeb/design/wp09-training-pipeline.md` still has its historical DRAFT header, but the
  decisions ledger's **15:15 WP-09 training pipeline** row adopts recommendations 1–7 and increments #1–#7.
  Its 15:34 and 16:02 separation amendments and 15:44 exporter-IR amendment govern over the original draft text.
  Bins, a small logits-only two-head convolutional network, opset 13, the emitted IR 7, shared preprocessing,
  run splits, held-out calibration on ORT outputs, adjacent-lane negatives and one frozen ONNX artifact are decided.
  Calibration method, fit procedure, OOD score/rule, hyperparameters, numerical equivalence bounds and all real-data
  fidelity/count/seed/coverage values are **not** decided by that adoption.
- Dataset candidate `92dfe5ad4b77f9a4aa8aecfbb116872811a69267` implements manifest **/3**. Training/calibration runs
  meeting any declared evaluation section in their ego-traversed set are refused whole. Test runs meeting that
  set are reported, not refused on that basis; evaluation spawn point/seeds remain refused in every split.
  Supplied labels reproduce per-run digests and label-code/parameter/observer provenance. The code identity is a
  named `labels.py` plus `scenario.py` closure. `check_manifest` intentionally does **not** establish that consumed
  label flags/distance/class/timestamps have correct field types or coherent meanings. Parent review finding 10
  carries that requirement into #4. The later test-only repair `85df0ad` preserves these product contracts.
- Compat training candidate `11ff91e` provides pinned CPU torch `2.14.1+cpu`, onnx `1.23.2`, numpy `2.5.4` with
  a fourteen-wheel hash lock. Its repaired execution pattern is `unshare -rn`, clean environment, real CPython
  3.13.13, `-S -s -B`, explicit approved paths, no bytecode and no networked fallback. Its identity records the
  installer .pth hooks as a residual; actual training processes disable site loading. This candidate's previous
  probe trains/exports **one output**, so it cannot establish the real two-head U4 contract. No new import or tree
  verification is claimed by this source review.
- Compat main `4172f61` owns the sole shared `xverse_compat.inference.preprocess` implementation and bindings.
  Its exact float32 NCHW output uses declared crop/resize/colour/normalisation, numpy `2.5.4`, and source/parameter
  digests. #4 imports this implementation; it must not copy it into the offline or runtime blueprint.
- WP-13 ML candidate `d7d4db5` (product modules unchanged from the requested `430b367`) supplies the actual
  restricted static reader and runtime consumer. It requires **one static float32 input and two outputs**, IR 7,
  one default-domain opset 13, only `Conv`, `Relu`, `GlobalAveragePool`, `Flatten`, `Gemm`, finite local float32
  initializers, supported attributes/wire fields and explicit topological identities. It refuses external tensor
  data, symbolic/dynamic shapes, custom domains and unsupported graph/protobuf constructs. Passing the broad ONNX
  checker or an operator-name set alone is insufficient.
- Current runtime methods are candidate `temperature-scaling` with separate occupancy/bin temperatures and
  `max-probability` or `entropy` OOD scores. Their presence in code is **not** an AD-03 scientific choice. Runtime
  uses exactly the three provenance members `modelDigest`, `preprocessParamsSha256`, `postprocessSha256`; code,
  environment and training provenance remain bound metadata/offline audit material.

No conflict requires changing those product contracts. Real data still depends on recorder #6 proving complete
traversed-section capture, actual observer/world-map binding and source-record identities. A manifest's supplied
metadata cannot prove those facts by itself. The existing FrameStore verifies hashes on read but decompresses
before checking length; the #4 consumer must bound compressed input/decompression and validate expected frame length
before allocating tensors, rather than treating its digest check as a resource bound.

## Finding 2: proposed pipeline architecture and record contract

### 2.1 Offline boundary and stages

All training modules live in the offline-only `assured_aeb/perception/` package, with a standard-library launcher
in `tools/`. Proposed responsibilities are `training_record`, `dataset_consumer`, `training_network`,
`training_loop`, `calibration`, `model_export` and `model_freeze`. Runtime `camera_inference`, `postprocess`,
role modules and entry points import none of these. No torch/onnx dependency is added to any runtime venv or plan.
Shared compat preprocessing and the existing runtime postprocessor/inspector are consumed through their public
contracts. No platform code or deployment flow changes are needed by #4.

The launcher accepts only explicit job/source-location records, validates their canonical bytes and creates a
fresh isolated output directory. It dispatches sequential stages in the training environment or the separate
read-only U4 environment. Every torch/ORT process uses the existing isolated pattern, never a shared interpreter
with both dependency trees, and never a plain-subprocess fallback. A missing isolation facility is a recorded
unavailable verification result; required acceptance cannot count a skip as success. Temporary paths, host times
and run logs stay outside deterministic model metadata. Factory dispatch receipts, queue state and X-COM-format
operational logs belong in `/home/jefferson/x-verse_fabric`; future admitted factory runs use its entry gate.
Dataset/model development artifacts may use their declared cache roots. No live D-3 run is started by a test.

The state sequence is `admitted → trained → graph-exported → ORT-logits-verified → calibrated → characterised →
metadata-frozen → final-U4-verified → candidate-published`. Each output records input digests and its own digest.
A failed/refused stage leaves diagnostic and partial development artifacts, never a candidate publication marker.
Do not resume an arbitrary partial optimizer/model state; a rerun starts a fresh candidate from the same immutable
inputs. Increment #5 corruption curves and #7 real data/measurement remain separate outputs/gates, not synthetic
results substituted into their fields.

### 2.2 Required job and source records; no implicit values

Proposed job schema is `assured-aeb.training-job/1`, closed and canonical, with these required nested records.
Implementation must document exact member sets and reject missing, unknown, duplicate-JSON-key, nonfinite,
unrepresentable-number, cyclic/non-JSON and malformed members before framework import. All floats used in math
must be representable and finite; integer identities must exclude booleans. Paths are separate source locators,
never trusted identities and never embedded raw in the model.

| Record | Required contents and constraints |
| --- | --- |
| `identity` | Candidate ID, purpose (`synthetic-verification` or `development-training`), schema, code closure digest, input-record digests; purpose is offline only and creates no runtime mode |
| `dataset` | Expected manifest /3 digest, label-parameter record digest, frame-format record/digest, recorder/source-index digest; per-run source locators resolve scenario, labels, observer, run-parameter bytes and store root and must reproduce expected digests |
| `separation` | Complete five P-4 category seed lists (characterisation, training, calibration, pilot, evaluation) and their record digest; category lists pairwise disjoint; manifest evaluation seeds/sections equal the nominated separation record; recorded actual sections retain the /3 rule |
| `trainingPartition` | Explicit fit and checkpoint-selection run-ID lists partitioning the manifest training runs; nonempty, disjoint, no calibration/test run; proposed extra seed-disjoint fit/selection rule in DN-2; no implicit frame split |
| `preprocessing` | The exact existing `xverse-compat.preprocess/1` record, its canonical digest and expected existing compat code/numpy binding; format dimensions/encoding must agree with label-camera and stored frame bytes |
| `architecture` | Named static input/occupancy/bin outputs; nonempty ordered dense Conv/ReLU block list with each output-channel count, kernel, stride, padding, dilation and bias explicit; head bias flags and explicit initialization method/bounds; no layer width/depth/resolution chosen by code |
| `optimisation` | Explicit method, epochs, batch size, learning rate, momentum/dampening/weight decay/Nesterov settings if the selected SGD method supports them; loss weights, evaluation epochs/checkpoint rule; required CPU intra/inter-op threads, torch/numpy/data-order/initialisation seeds and deterministic-algorithm setting |
| `calibrationFit` | Approved method/status reference; ordered positive temperature candidate lists for occupancy and bins if DN-3 adopted; fit split/weighting and metric IDs; no default temperatures, count or search range |
| `oodFit` | Approved score/rule/status reference; either the proposed explicit nearest-rank quantile fraction or an explicitly supplied justified fixed threshold policy; exact declared population; never evaluation data |
| `verification` | Absolute/relative raw-logit and calibrated-probability bounds, decision-agreement acceptance, exact-repeat counts, sample selection, independent-reference cases, class coverage and metric acceptance records; `fusion.occupancyThreshold` value/reference for the existing `>=` decision comparator; all acceptance values explicit |
| `environments` | Exact training/U4 identity-record digests and lock/source revisions, interpreter locations and explicit sites; admitted engineering memory/disk/input/output byte bounds and worker timeout; these are engineering controls, not scientific verdicts |

Fields needed only by one method have an exact method-specific shape; unused values are refused. Derivable values
are computed and cross-checked, not independently adjustable: three input channels from shared preprocessing,
`K = len(distanceBinEdgesM) + 3`, final static shapes, convolution spatial dimensions and number of updates.
`num_workers=0` and CPU-only are existing accepted deterministic-training constraints. All remaining numeric
entries stay unset for real training. TEST-ONLY synthetic jobs must populate them explicitly and cannot be promoted
to the AD-27 protocol or used to establish calibration/OOD effectiveness.

### 2.3 Dataset admission and labels at the consumer

Before any tensor, call `check_manifest` with actual scenario files and actual supplied label lists; require no
refusals and retain its reports. Compare the result against the job's expected manifest/label-code/label-parameter
identities. Independently validate/rehash the actual label-parameter record and frame format. Source-byte checks
verify actual observer/run-parameter files against recorded digests when supplied by the recorder package; a
missing required source is a refusal, not a fabricated attestation. Source hashing still does not prove world-map
truth or traversed-set completeness: preserve recorder #6's signed-off evidence obligation in the data card.

Require every consumed label to have exactly the existing label /1 members:
`schema, frame, simElapsedNs, rawSha256, inCorridor, visible, obstacle, distanceM, distanceBin, provenance`.
Provenance is exactly `observerSha256, observerLine, labelCodeSha256, labelParamsDigest`; line is a positive integer
pointing beyond the header. Frame/timestamp must be nonnegative integers and equal the matching manifest frame;
digests must be bare HEX64 and reproduce the accepted source/closure identities. Flags are exact booleans, and
`obstacle == (inCorridor and visible)`. Distance is finite or explicit null; an obstacle requires finite distance.
For a scenario with no target, require the producer's actual false/false/false/null/no-obstacle form. With a
declared target the joined observed-target label has finite distance. Recompute only the existing distance-bin
mapping from those values and declared edges, including `< edge` boundaries, `overlap` at distance <= 0 and `beyond`;
refuse unknown/impossible class names. This checks consumed semantics, not the original planar geometry truth.

Derive a single explicit class order `no-obstacle, overlap, bin-0 … bin-(N-1), beyond`, and bind it to both the bin
head and postprocessing metadata. Do not infer order from class encounter frequency. Labels without a stored frame,
duplicate frame labels, changed hashes or a wrong map/scenario are refusals. A stored frame lacking a valid label
is excluded and counted, never assigned a negative target. Retain known recorder exclusion categories separately
from merely unlabelled counts; do not invent a reason not supplied by the recorder. Record per-run/split/class counts,
including target-absent and adjacent-lane negatives, and enforce only explicit coverage acceptance entries.

Open the content-addressed frame store read-only; never sweep its temporary files. Bound compressed reads and
zlib output by engineering limits/expected format length, require one complete stream without trailing/concatenated
payload, then verify length and raw SHA-256 before shared preprocessing. Stream batches rather than loading the
entire corpus into RAM. The existing /3 whole-run evaluation-section exclusion is repeated at admission and bound
in the report. Pilot/evaluation seeds never enter fit, checkpoint selection, calibration, OOD fitting or test data;
manifest `test` seeds must be in the characterisation category. Shared non-evaluation sections are reported as the
accepted limited independence, not silently declared disjoint.

### 2.4 Model, fit and checkpoint selection (DN-1/DN-2)

The proposed class is an ordered stack of dense Conv2d/ReLU blocks, followed by `AdaptiveAvgPool2d((1,1))`,
`Flatten` and separate Linear occupancy/bin heads. The fixed global pooling target is the operation's definition,
not a new fidelity or width value. No batch normalization, dropout, sigmoid, softmax, dynamic shape, arbitrary
pooling or auxiliary output is introduced. Check every convolution's resulting positive spatial dimensions from
record values before creating the model. Export input `[1,3,H,W]`, outputs `[1,1]` and `[1,K]`, all float32.

Proposal: occupancy `BCEWithLogitsLoss` plus multi-class cross-entropy on every admitted labelled frame, including
the explicit no-obstacle class, each multiplied by its required recorded positive weight. This avoids silently
masking no-obstacle bins or letting a hidden class-weight default change the task. Use CPU SGD with explicit
record settings and a constant learning rate; no unrecorded scheduler or early stopping. Initialization is owned
uniform initialization using recorded bounds and seed; all tensors are initialized explicitly in stable name order.
Framework constructor defaults do not become unrecorded initialization policy. No augmentation or corruption enters
training under the accepted clean in-ODD training design.

Enumerate runs/frames in a canonical order, then form the recorded deterministic shuffle for each epoch; retain
and record the final short batch. Record all seeds, exact sample order digest, algorithm setting and thread counts.
Fit uses only fit runs. At declared evaluation epochs compute the same weighted mean loss on the separately listed
training-selection runs in eval/no-grad mode, with every example weighted equally. Select the smallest loss,
ties to the earliest epoch; retain the exact selected weights. Calibration and test samples never select weights,
architecture or hyperparameters. Finite checks cover data, logits, loss, gradients and selected weights. Failure
refuses the candidate; no silent substitution of random weights or a previous checkpoint.

### 2.5 Genuine export and raw-logit boundary

Use the pinned torch exporter in eval mode with `dynamo=False`, opset 13, static shapes, embedded parameters and
`keep_initializers_as_inputs=False`; no `dynamic_axes`, custom opset or functions. The actual installed signature
has `dynamo=True` and `external_data=True` defaults, so flags and postconditions must be explicit. The current
legacy exporter probe already uses `dynamo=False`; inspect its genuine two-head output, not a hand-written fixture,
to establish compatibility. Disable external-data output and check the serialized initializers regardless of the
exporter's option interpretation. Assert actual IR == 7; **never overwrite IR/opset to force acceptance**.

Run ONNX's checker, then the current `model_contract.inspect` on exact output bytes and compare actual static I/O,
operator domains/types, allowed attributes/initializers and input/output names to the declared model schema. An
unsupported exporter construct is a visible failed boundary requiring a new finding and reviewed solution; do not
strip fields/nodes or widen the static reader silently. Export graph and named weight-descriptor digests are
recorded. Weight identity uses canonical ordered `{name,dtype,shape,sha256(little-endian contiguous bytes)}` records.

The preliminary graph binds the real preprocessing code/parameters/numpy but is explicitly **not a U4-ready frozen
artifact**: no dummy temperature or OOD threshold is invented before fitting. A raw-logit U4 worker uses the accepted
pinned loader, mandatory static schema, static inspection and preprocessing binding directly. It returns only
record-ordered logits/IDs/digests to offline calibration. It uses CPUExecutionProvider, sequential execution, one
intra/inter-op thread and BASIC optimization as the already accepted loader does. Torch is absent in that process.
Test raw logits against actual torch outputs on declared fixtures and the characterisation split with explicit
bounds; report maximum errors per output/sample and decision agreement, not just a single boolean.

### 2.6 Calibration, output-based indicator and independent reference (DN-3/DN-4)

Recommended initial supported fitting method: the existing two-temperature scaling contract, fitted **only on
calibration-split ORT logits**. Use finite sorted unique positive temperature grids supplied in the fit record;
minimize binary log-loss for occupancy and multi-class log-loss for bins separately, with equally weighted examples
and lowest temperature winning an exact tie. Exhaustive finite grid search avoids new SciPy dependencies or hidden
iterative tolerances; grid values/count remain explicit author choices. Report objective curves and selected values.
Stable log-loss uses logits/log-sum-exp, not clipped probabilities with an invented epsilon.

Recommended output-based OOD method: `max-probability`, exactly `1-max(calibrated bin probabilities)`, preserving
the current runtime `score > threshold` rule. A proposed fit rule sorts calibration scores and chooses the
nearest-rank empirical quantile at `ceil(q*n)-1`, with required `0 < q <= 1`; record q, count, index and selected
score. No interpolation or threshold default. Existing entropy remains supported in runtime code but is not selected
merely because it exists. Temperature fitting and score-threshold fitting on the same calibration split are disclosed;
calibration-split summaries are fitting observations, while independent characterisation/test data give held-out
quality and false-alarm observations. This score may miss confidently wrong outputs; it is not proof of OOD or safety.

Proposed reports: occupancy/bin NLL and Brier score before/after calibration, class counts/confusion matrices,
occupancy false/missed detections, OOD score distributions/flags and confidently wrong unflagged examples. Probability
calibration claims need explicit acceptance and scientific support, still TODO under AD-03. Distance-error reports
carry true longitudinal gap, predicted bin and interval-containment results. A scalar distance error requires an
explicit representative rule for each bin, particularly overlap/no-obstacle/unbounded beyond; absent that record,
report it unavailable rather than invent midpoints. No test/calibration result is used to tune on evaluation data.

An independent reference must reimplement the formulas with standard-library math/stable log-sum-exp (and an
independent direct NumPy Conv/ReLU/GAP/linear forward calculation for bounded synthetic cases), not call the fitted
production function as its expected value. Compare selected temperatures, scores/quantile, probabilities/classes and
raw logits against those references with the supplied bounds. Corruption characterisation calls actual GA-36 and
FR-034 code in #5; #4 neither substitutes fake curves nor designates AD-31 severities.

### 2.7 Frozen metadata, reports and final publication (DN-5)

Write actual compat `preprocess.binding(params)` entries and actual `postprocess.metadata_entry(record)`, including
their code hashes. The postprocess record has its existing exact member/method shape with fitted temperatures,
explicit class order/output names and fitted threshold; do not alter runtime provenance. Additional canonical
training metadata binds manifest/label-parameter/label-code closure, split/seed-record digests and counts, offline
training/fit/export code closure, job/hyperparameter record digest, training/U4 identity digests, exporter versions,
actual static schema/IR/opset and the pre-freeze equivalence report digest. Full observer/label data, evaluation
seeds/sections, scenario/fault/oracle information and host source paths stay outside runtime metadata; metadata
holds their offline provenance identities only. Runtime consumes no offline manifest or training record (FR-028).

Avoid digest cycles: equivalence/calibration reports identify the preliminary graph/weights and immutable inputs;
they do not claim to bind the not-yet-created final model. Attach their stable digests and fitted metadata, serialize
once deterministically, and compute the final file digest. A separate terminal package then binds that final digest,
all earlier reports and the final-U4 verification record. Do not embed a report containing the final digest back into
the same model. Wall times/pathnames stay in external operational records so they cannot defeat repeat-digest tests.

Finally use the genuine `CameraInference.load` on the final exact bytes/digest and declared model/preprocessing
schema, including its metadata and warmup checks, through the isolated U4 pattern. Repeat real inference per V-4 and
compare to the already recorded raw-logit/probability results; test actual F07-to-perception integration separately
from training. Preserve only the three existing runtime provenance fields. Check model digest at start/end and no
unit/environment bytecode or learned-weight writes. Repeat the **entire** train/export/calibrate/freeze process in
fresh processes on the same immutable job/manifest; compare selected checkpoint, named-weight digest, final ONNX
bytes/digest and deterministic reports. Any difference is reported and blocks a bit-reproducibility claim; do not
normalize away unexplained differences.

Publication is an atomic fresh candidate-directory operation only after all required checks pass. Emit a data/model
card with separation, coverage, planar-label, single-map/weather, adjacent-lane, preprocessing-crop, seed/section
sharing, confidence/OOD and reproducibility limits. A synthetic package is prominently TEST-ONLY and inadmissible as
the thesis frozen model. A real candidate is still subject to #7 measurements, scientific acceptance/AD-27 freeze,
V-3/V-5 and deployment binding; neither pipeline success nor engineering publication grants those approvals.

## Finding 3: method choices for coordinator disposition before code

These recommendations complete the engineering design without selecting scientific numeric values. Acceptance under
the delegation remains flagged for author review; the author can revoke it. An accepted method is not an accepted
real model or evidence of calibration quality. All scientific source support remains `TODO: citation needed`.

| ID | Proposed disposition | Reason and boundary |
| --- | --- | --- |
| DN-1 | Adopt the Conv/ReLU stack, GAP/Flatten and two independent Linear heads, with owned record-bounded uniform initialization; no other network class in #4 | Fits the already accepted class and V-1 subset; every width/depth/kernel/fidelity/initialization bound remains supplied, not chosen |
| DN-2 | Adopt weighted BCE-with-logits plus bin cross-entropy on all valid labels, explicit constant-rate SGD, checkpoint by minimum selection-run loss/earliest epoch; make fit/selection runs and seeds disjoint | Gives a complete reproducible fit/selection rule; no calibration/test selection. Optimizer/loss values, epochs, class coverage and batch size remain records. If seed-disjoint selection is not adopted, shared-seed dependence must be explicit rather than silently described as independent |
| DN-3 | Adopt separate occupancy/bin temperature scaling and explicit finite-grid NLL minimization, smallest temperature on ties | Compatible with current postprocess metadata and avoids additional optimization dependencies; no temperature/grid/iteration count or calibration-quality bound is set |
| DN-4 | Select max-probability score and explicit calibration nearest-rank quantile rule for this initial pipeline; report NLL/Brier/confusion/flag summaries and independently held-out quality | Preserves existing score direction and strict `>` flag. The q value, coverage and acceptance remain author/measurement inputs. Entropy remains an unselected code capability, not an additional principal condition |
| DN-5 | Adopt staged graph/reports/final-model/terminal-package identities, deterministic metadata and actual unmodified V-1 inspection/export boundary | Avoids report/model self-reference, dummy calibration and runtime-data leakage. An exporter incompatibility produces a finding, not permission to widen WP-13 |
| DN-6 | Adopt strict training-consumer label shape/coherence, five-list P-4 membership and bounded read/decompression; preserve /3 test-section reports and recorder #6 source-truth limits | Closes the independently carried consumer obligation without changing the accepted manifest/schema or claiming source attestation from hashes |
| DN-7 | Require two complete fresh synthetic training/export/calibration/freeze executions, actual U4 inference and independent reference comparisons as a blocking #4 integration verification | Distinguishes real pipeline execution from a mocked fixture. This repeat count is the accepted two-training reproducibility check from thesis design §4; any additional repetitions remain record-supplied |

**Still required as real-job inputs, not questions to guess:** actual non-evaluation/evaluation section sets and
P-4 seeds; label corridor/bin/camera values; preprocessor fidelity/crop/resize/normalization; all network and fit
values; temperature grids/q; coverage/calibration/model quality targets; model/reference numerical tolerances and
decision-agreement acceptance; distance representatives if scalar errors are wanted; resource limits and runtime
measurements. Their absence blocks **real** training/freeze claims. Synthetic TEST-ONLY jobs may exercise every
parameterized path after method disposition. They cannot fill those scientific TODOs by inference.

No canonical note change is made. Recommended later note update, **DELEGATED DESIGN DECISION, flagged for author
review**, only if accepted: add the adopted DN-1…DN-7 method/boundary dispositions to the existing Phase 8 entry,
link this review and the thesis WP-09 record, and retain every unresolved numerical/calibration-support and #7
acceptance gate. Do not duplicate the dynamic note or rewrite the historical accepted design header silently.

## Finding 4: verification and implementation increments proposed; execution not yet performed

| Order | Implementation / verification obligation | Decisive evidence |
| --- | --- | --- |
| 4a | Standard-library job/label/source/partition admission and bounded dataset reader | Genuine label_run/manifest /3 positive fixtures; all missing/extra/duplicate-key, malformed bool/int/nonfinite/huge-int, inconsistent class/flag/distance/time, source/digest mismatch and bounded zlib failures; rehashing malformed labels must not bypass consumer validation; whole protected-section run excluded even if its spawn is elsewhere |
| 4b | Record-driven CPU two-head network and training/checkpoint loop | Genuine shared preprocessing inputs and actual optimizer updates; independent explicit target/class order and partition checks; deterministic named-weight digest; no framework import on malformed job; no calibration/test sample reaches fit/checkpoint selection |
| 4c | Genuine legacy torch export and U4 raw-logit worker | Actual serialized two-head graph passes ONNX checker **and current static reader**, exact I/O/IR7/opset13/V-1 metadata; deliberately unsupported graph/external-data/shape is refused before ORT session; torch-vs-ORT/independent-forward comparisons with explicit test-only bounds, no exporter mock or graph-fixture substitution |
| 4d | Calibration/threshold fitting, frozen metadata and terminal package | Independent scalar/reference objective/temperature/score/quantile comparisons, stable extremal-logit cases and tie boundaries; class order/`>=` occupancy/first-argmax/strict-`>` OOD agreement; actual final CameraInference load, correct three-field provenance and tampered binding refusal; digest-DAG reconstruction and no cyclic identity claim |
| 4e | Full synthetic end to end and owning-suite assembly | Two fresh genuine train→export→ORT→calibrate→freeze→final-U4 processes from disjoint TEST-ONLY run/seed partitions; actual weights change through training, both logits finite and record-shaped, all repeat digests compared; finalized output reopens via real reader/loader; process isolation and no bytecode, source-runtime-import scan; retain real commands, exact revision, identities, logs, statuses and hashes |

Build the synthetic fixture through the actual label/store/manifest interfaces: procedurally drawn camera bytes and
hand-constructed evaluation-only observer/scenario records with geometrically checked known targets. Cover present,
absent and lateral negatives and declared bins; mark all sizes/values/seeds/epochs/tolerances TEST-ONLY. Keep samples
byte-distinct across runs so the real manifest duplicate-frame guard is exercised, not bypassed. No CARLA is needed
for that fixture. Test malformed labels whose hashes/provenance have been recomputed to prove that structural
consumer validation matters. Verify observer-line frame identity from the actual supplied observer bytes; this is
still not a replay of all label geometry or proof of the recorder's world-map/traversed-section observations.

Required framework cases are explicit integration gates: when their environments/namespace facility are absent,
record unavailable/skip and leave #4 incomplete. A quick stdlib suite cannot stand in for these runs. All framework
work is serialized by the coordinator behind the active platform full regression; no training/ORT/test runner has
been started in this design pass. No new wheels or downloads are needed or authorized here.

**Requirement/maturity disposition.** FR-005/V03 is **allocated** to #4/#7 and the WP-13 runtime consumer, not completed
by this document. FR-021/V14 and FR-028/V21 have **allocated** offline/runtime separation and metadata/import checks;
source-truth and projection integration remain #6/WP-17/WP-13 responsibilities. FR-024 protocol freeze stays
**deferred** to AD-27, FR-027 findings/review/acceptance remains binding, and FR-034/V27 corruption/input-quality
characterisation stays #5. The parent thesis SADS mapping allocates model integration/execution and results support;
no domain-neutral platform SADS completion is claimed. In the platform REF-002 traceability register,
`XVE-SYS-0031`–`XVE-SYS-0055` remain **allocated** architectural targets, except `XVE-SYS-0044`, which remains
**needs_clarification**; this offline design does not silently change any disposition or infer unspecified source
requirement text. Wider scenario/results requirements remain allocated to their owning platform/blueprint work.

**Checks actually performed for this design:** read-only accepted-design/ledger, manifest/label/store, training
lock/probe/identity-record, preprocessing and restricted ML-consumer source inspection; exact small input byte
hashes; Markdown/table review; evidence JSON parsing and whitespace diff check. No torch/onnx/ORT import, pytest,
environment-tree rehash, training, model export, simulator run, download, factory dispatch, acceptance or merge.

## Finding 5: coordinator independent design disposition (2026-10-24)

Reviewed48f9475e finding1–4 and the complete architecture/stage/consumer/export/calibration/digest/verification
contracts. AdoptDN-1–DN-7 as recorded in thesisdecisions.md, WP-09 #4 pipeline methods, under delegation and
flagged for author review. The preliminary raw-logit worker uses the existing generic pinned compat loader plus
static inspector and preprocessing binding; it does not pretend to be the final metadata-complete CameraInference
artifact and does not invent dummy postprocess values. Final genuine CameraInference acceptance remains mandatory.
Separate4a–4e increments are authorized; this is a method/design disposition, not source acceptance, actual
framework execution, real-model approval or scientific calibration validation. All required real numbers remain
unset and all recorder/source-truth, scientific-support, #7 and AD-27 gates remain.
