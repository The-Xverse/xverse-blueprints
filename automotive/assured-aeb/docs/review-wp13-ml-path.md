# WP-13 increment #3 review log: the U4 ML path (frame spool, preprocessing, ONNX Runtime, post-processing)

**Candidate.**
- Branch `candidate/phase8-wp13-ml-path-20261024`, **stacked on the WP-13 #1 candidate `a74cd38`**.
- It is stacked because it must produce exactly `assured-aeb.perception-output/1`, as defined and checked by #1's
  `fusion_aeb` (review-wp13-logic finding 1 §1.5).
- #1 is not modified, and is under independent review. If #1 changes in review, this branch is rebased.

The order is:
1. findings before repairs;
2. an independent read-only review;
3. acceptance;
4. a merge, after #1.

None of the last three has happened yet.

**Inputs.**
- Thesis `design/wp13-logic-ml-binding.md` §2, §4 and §6, and §9 R-4, R-5 and R-7 (decided).
- `decisions.md`:
  - AD-03 B (a calibrated confidence and an output-based OOD indicator, with thresholds `TODO`);
  - "WP-09 training pipeline" (logits-only ONNX at opset 13 with the V-1 operators; calibration and OOD in owned NumPy
    post-processing, parameters in the ONNX metadata, bound by the model digest);
  - "WP-08 inference stack";
  - "WP-09 #3 unit isolation" R-1 (`-S -s -B`, `PYTHONDONTWRITEBYTECODE=1`).
- `design/wp09-training-pipeline.md` §6. The calibration and OOD methods are `TODO: author decision`, AD-03,
  `TODO: citation needed`. It gives as examples "the maximum calibrated probability or the entropy of the bin
  distribution".
- **Compat main `34b514d`** (read-only):
  - `inference/loader.py`: `load_model(path, digest, *, expected_inputs, expected_outputs)`;
  - `inference/preprocess.py`: `load_params`, `preprocess`, `binding` and `verify_binding`, with SHA-256 `7aeed291…7100`.
- **Compat WP-08b candidate** `candidate/phase8-wp08b-isolation-20261024` `840091a` (unmerged, read-only):
  - the lazy `xverse_compat/__init__.py`;
  - `inference/unit.py` (`INTERPRETER_FLAGS`, `FIXED_ENVIRONMENT`, `environment` and `command`).
- **The dependency, observed here.** In the U4 venv pattern, compat main's `xverse_compat` fails with
  `ModuleNotFoundError: xverse_xdl`. The WP-08b sources import `inference.preprocess` and `inference.loader` cleanly.
  WP-08b leaves `preprocess.py` byte-identical (the same SHA-256), so the preprocessing binding is unaffected.
- The U4 venv (`.x-verse-build/cache/xverse-aeb-inference-20261024/`) is used **read-only**: numpy 2.5.4 and
  onnxruntime 1.31.0.

**Scope.**
- Offline modules, tests and a checked-in tiny synthetic ONNX fixture, with its standard-library generator.
- No training venv is used: option (b) of the coordinator's message.
- No download, no CARLA, no live run, and no write to loop10. The soak's paths are not touched.

## Finding 1: design (recorded at 16:08:08, before any code)

### 1.1 Module names
- `assured_aeb/postprocess.py` and `assured_aeb/camera_inference.py`.
- Neither name contains `perception` or `labels`: the WP-09 #1 import scan refuses any runtime module whose import
  names contain those words, and the U4 unit entry will import these modules.

### 1.2 `postprocess.py`: schema `assured-aeb.postprocess/1`
The module is standard library at import, with numpy imported inside `apply` only.
- **Metadata.** One model-metadata key, `assured-aeb.postprocess`, holds the canonical JSON record. That key is part
  of `metadata_props`, so the model digest binds it.
- **Record:** `{schema, outputs: {occupancy, bins}, binLabels, calibration: {method, params}, ood: {method, params,
  threshold}}`, with exactly these members and no defaults.
  - `outputs` names the two graph outputs: an occupancy logit `[1, 1]` and bin logits `[1, K]`.
  - `binLabels` has K unique entries from the WP-09 label vocabulary (`no-obstacle`, `overlap`, `bin-<i>`,
    `beyond`).
  - `threshold` is the frozen OOD threshold, an AD-03 value. Only the record carries it; the code carries none.
- **Methods: CANDIDATE implementations, pending AD-03.** The thesis decides which method is frozen (`TODO: citation
  needed`). Any other method name is refused.

  | Field | Method | Formula | Params |
  | --- | --- | --- | --- |
  | calibration | `temperature-scaling` | `p_occ = σ(z_occ / T_occ)` and `p_bins = softmax(z_bins / T_bins)` | `{occupancyTemperature > 0, binTemperature > 0}` |
  | ood | `max-probability` | `score = 1 − max(p_bins)` | none |
  | ood | `entropy` | `score = −Σ p·ln p` over `p_bins` | none |

  - `oodFlag = score > threshold`.
  - These are the two examples named in WP-09 §6. Adding or removing a method is a code change, bound by
    `postprocess.code_sha256()` in the perception provenance.
- **Arithmetic.**
  - float64 throughout;
  - a numerically stable sigmoid, and a softmax shifted by its maximum;
  - the argmax takes the first maximum;
  - the results are returned as Python floats.
- `predictedBin = binLabels[argmax p_bins]`.

### 1.3 Frame spool reader (R-4)
- `SpoolReader(root)` with `read(frame_sha256, length) -> (bytes | None, reason)`.
  - **Layout.** `<root>/<sha[:2]>/<sha>`, written by U2 alone (increment #5).
  - **Refusals:** a root that is not absolute, or not an existing directory; a non-hex digest; a symlinked or missing
    file; a length or SHA-256 mismatch. Each gives `None` with a reason. It never raises for a missing frame.
  - It is never evidence, and its bytes never leave the process.
- **Obligation on increment #5.** Its compat U2 writer and its U3/U4 reader must keep this layout, or replace this
  reader with a verified equivalent.

### 1.4 `camera_inference.py`: the `perception` role of U4
- **`CameraInference.load(...)`.** The standard-library imports run first; `xverse_compat.inference.loader` is imported
  inside `load` only. Its arguments are:
  - `model_path`, `model_digest` (`sha256:<hex>`, from the projection);
  - `model_schema` (`assured-aeb.model-schema/1`: `{schema, inputs: [{name, shape, type}], outputs: [...]}`,
    **mandatory**: R-5, WP-08 LOW-2);
  - `preprocess_record`, `frame_format` and `spool`.

  **Load order**, every step fail-closed, raising before readiness:
  1. validate the model-schema record;
  2. `load_model(..., expected_inputs, expected_outputs)`;
  3. `verify_binding(custom_metadata_map, load_params(preprocess_record))`;
  4. `postprocess.parse(custom_metadata_map)`, with the output names checked against the schema outputs;
  5. one warm-up inference on a fixed all-zero frame of the declared format. The outputs must be finite, with the
     declared shapes.

  The telemetry check before any import stays with the U4 entry point (increment #6). The loader refuses as well.
- **`step(camera_evidence) -> perception-output/1`,** one per delivered F07 message.

  | Condition | Inference | State | Reason |
  | --- | --- | --- | --- |
  | an F07 message that is not well formed (`assured-aeb.camera-evidence/1`, source `front-zone`, stream `f07-camera-adas`) | no | `UNCERTAIN` | `camera-evidence-malformed` |
  | front-zone integrity not `pass`, front-zone plausibility not `pass`, or smart-camera logical or plausibility not `pass` | no | `UNCERTAIN` | the failed checks |
  | the spool read fails (missing, length, digest) | no | `UNCERTAIN` | `frame-unavailable: <reason>` |
  | otherwise | yes | see below | — |

  When inference runs, the state is `DEGRADED` if the smart-camera statistical check (class iii) is `fail` or
  `oodFlag` is set, and `NOMINAL` otherwise.

  These states are advisory. The WP-14 validator re-derives them. **No new threshold:** class (iii) and OOD use the
  smart-camera and metadata thresholds.
- **The record:** exactly the members of #1 §1.5.
  - `frame` and `frameSha256` come from F07. `originNs` is the frame's origin from F07, so fusion's freshness measures
    the frame's age.
  - `inputQuality` holds the front-zone and smart-camera verdicts: integrity, sequence, fresh, plausibility, and the
    sensor's logical, plausibility and statistical verdicts.
  - `provenance` holds `modelDigest`, `preprocessParamsSha256`, `preprocessCodeSha256`, `postprocessSha256` (the
    record) and `postprocessCodeSha256`.
  - No pixels and no tensors.
- **The record when inference does not run.**
  - `occupancyProbability`, `binProbabilities`, `predictedBin`, `oodScore` and `oodFlag` are `null`. No value is
    fabricated.
  - #1's fusion check requires numbers there. It therefore classifies such a record as `perception-output-malformed`,
    which is behaviourally identical: the camera is unusable, `UNCERTAIN`, with reason `camera-unusable`.
  - **Raised to the #1 review as an amendment request:** accept the not-evaluated form (null values with state
    `UNCERTAIN`) explicitly, so the reason is not mislabelled. This branch does not change #1.

### 1.5 Test fixture (option (b))
- **Generator.** `tests/fixtures/make_camera_model.py`, standard library only. It writes the ONNX protobuf wire format
  directly, adapting the encoding helpers of compat `tests/inference/minimal_onnx.py`, with attribution.
- **The network** (IR 7, opset 13, the V-1 operators only):
  `image[1,3,8,8] → Conv(2, 3×3) → Relu → GlobalAveragePool → Flatten → Gemm → occupancy_logit[1,1]`, and the same
  `Flatten` output `→ Gemm → bin_logits[1,6]`. Its float32 weights come from a closed form.
- **Metadata.**
  - The preprocessing binding of compat `binding(params, "2.5.4")` for a TEST-ONLY `xverse-compat.preprocess/1`
    record: input 16×16 `bgra8`, full crop, `area-integer` to 8×8, `rgb`, and a TEST-ONLY normalisation.
  - A TEST-ONLY `assured-aeb.postprocess/1` record: `temperature-scaling` with T values, `max-probability` with a
    threshold, and the bin labels `no-obstacle`, `overlap`, `bin-0`, `bin-1`, `bin-2` and `beyond`. **All TEST-ONLY.**
  - A `purpose` entry stating that this is a test model and not a thesis model.
- **Checked in.** `tests/fixtures/tiny-camera-model.onnx`. Its SHA-256 is asserted in the tests.
  - When `XVERSE_COMPAT_SRC` names a compat source tree, a test regenerates the fixture and compares bytes.
  - The binding embeds compat `preprocess.py`'s code digest, so a change to compat preprocessing changes the fixture
    on purpose.

### 1.6 Tests
- **In-process, standard library only, always run:**
  - post-processing record parsing and its refusals: members, method, params, label vocabulary, duplicate labels,
    output names;
  - the spool reader's refusals and successful read;
  - the model-schema record refusals;
  - the state and reason table, and the not-evaluated record form, driven by a fake inference object;
  - the record members equal #1's `PERCEPTION_MEMBERS`;
  - a full-inference record passes #1's `fusion_aeb._perception_ok`;
  - no pixels are carried;
  - the import scan: `postprocess`, `camera_inference` and the probe import no `torch`, `onnx` or label code, and
    `numpy` only lazily.
- **In the U4 unit pattern (the probe `tests/camera_inference_probe.py`).**
  - It runs as a subprocess with the real CPython 3.13.13 and `xverse_compat.inference.unit.environment` and
    `command`, both from `XVERSE_COMPAT_SRC`.
  - Its path holds the U4 site-packages (`XVERSE_AEB_U4_SITE`), the compat sources and assured-aeb.
  - It is skipped without those variables, or if `unit.py` is absent, which is the case while WP-08b is unmerged.
  - **What it checks:**
    1. `load` succeeds on the fixture; a wrong digest, a `None` or wrong schema, and a tampered metadata binding are
       each refused;
    2. ONNX Runtime logits match an independent NumPy forward pass within a TEST-ONLY tolerance of 1e-5;
    3. the post-processed outputs equal the formulas recomputed independently;
    4. repeated runs are bit-identical;
    5. end to end, a real `CorruptionStage` and `SmartCamera` and a real `FrontZone` produce an F07 message, the
       spool holds the frame, `step` runs, and fusion accepts the output;
    6. no bytecode is written into the U4 venv.

### 1.7 Expected residuals
1. The calibration and OOD methods, and every threshold and temperature, are AD-03 `TODO`. The fixture's values
   are TEST-ONLY.
2. The WP-08b merge is required before the probe can run against compat main.
3. Increment #5 owns the spool writer and its layout alignment, and increment #6 the U4 entry point, readiness
   order and V-3 budget.
4. The #1 amendment request: accept the not-evaluated perception-output form.
5. V-5 inference time, with the real model, is D-4c.

## Finding 2: continuation design and interface reconciliation (Codex, 2026-10-24; before code changes)

The two untracked Claude drafts were inspected and preserved as inputs before this continuation:
- `camera_inference.py`: SHA-256 `a889fd770a4d1ef4ef3b2b47d666ce9a11a718f7c7d0e5cfe5202b64fb02a050`;
- `postprocess.py`: SHA-256 `f22e545d9190c28275d8254ce481a2b4dbf3361e7159ca6aa8c63fce9c51826b`.

The parent coordinator confirmed these scope clarifications before implementation:
1. **Runtime provenance:** repaired WP-13 #1 requires exactly `modelDigest`, `preprocessParamsSha256` and
   `postprocessSha256`, all bare HEX64. The draft's five members and `sha256:`-prefixed model value do not satisfy
   that contract. Keep the three-key runtime form, validate the declared `sha256:<hex>` before normalization,
   and retain preprocessing/postprocessing code and runtime identities in a separate digest-bound audit record.
   No evaluation, fault or run-kind marker is added to a runtime message.
2. **Refuse before session:** add a standard-library `model_contract.py` inspector over the exact digest-verified
   ONNX bytes. It supports only the declared bounded local subset: ordinary protobuf wire types, static float
   tensor I/O, one graph, IR 7/opset 13, and the V-1 operators. Reject malformed/truncated/unsupported wire forms,
   repeated singular identities, duplicate metadata or I/O names, custom operator domains, external tensor data
   and unsupported graph constructs rather than claiming a general ONNX parser. All reads are bounded by actual
   verified bytes. Validate actual static I/O against the mandatory schema, shared preprocessing and postprocessing
   metadata before calling the existing pinned loader, which independently rechecks the same declared digest.
3. **Code binding:** `metadata_entry` also writes a postprocessing-code SHA-256 metadata key; the load path checks
   it and the shared preprocessing binding before session construction. The fixture generator binds the current
   owned code, not an accepted scientific method. The runtime audit record includes these bindings and its own
   canonical SHA-256. Actual calibration/OOD method choices and numeric values remain AD-03 TODOs.
4. **Input evidence:** verify the complete current F07 shape, non-negative frame/timestamps/sequence, freshness and
   source ordering reports, closed known quality-indicator fields and explicit statistical `pass`/`fail`.
   Missing/not-evaluated quality cannot be nominal. Preserve null inference fields for not-evaluated outputs;
   fusion's existing refusal of that form remains a separately tracked #1 reconciliation. An inference error or
   malformed/non-finite output yields `UNCERTAIN`, not fabricated probabilities.
5. **Spool:** open/pin the absolute root directory and resolve the digest prefix and file relative to directory
   descriptors with no-follow semantics. Refuse non-regular files and read at most the declared frame length plus
   one byte, then verify length and digest. No spool writer is added.
6. **Tests:** complete the standard-library tiny IR-7/V-1 logits fixture generator, fixed-byte fixture, independent
   NumPy forward reference and unit-pattern subprocess probe. Ordinary tests cover parsing, before-session refusals,
   the spool and state table without ORT. Full runtime cases use genuine compat loader/preprocess with the pinned
   U4 venv inside `unshare -rn`, isolated `-S -s -B` processes and no downloads. All fixture values are TEST-ONLY.

No heavy test or inference/build process is authorized until the parent releases the host test slot. The current
platform full regression and midnight rc.1 soak remain protected. The continuation does not accept or merge any
candidate and does not select a scientific model, method, threshold, tolerance or protocol value.

## Finding 3: ML-path continuation implemented; full verification pending (Codex, 2026-10-24)

Implemented finding 2 after its separate design commit `23127fe`:
- Completed `camera_inference.py` and `postprocess.py` from the inspected Claude drafts, and added
  `model_contract.py`, the bounded standard-library local ONNX-contract reader. Digest, telemetry, actual static I/O,
  preprocessing binding, postprocessing parameter/code binding and declared output/bin shape are checked before
  `loader.load_model` may create a session. The genuine loader then independently rechecks the frozen model digest.
- Runtime provenance is the agreed three bare-HEX64 digests. Full shared-code/model/runtime identities are retained
  in a detached canonical audit record with its own SHA-256; that audit record is never a runtime flow message.
- The read-only spool pins the declared root and follows no digest-prefix/file symlink below it. Reads reject
  non-regular files and mismatched length/digest, and are bounded by the declared frame length plus one byte.
- F07 evidence uses the real front-zone form and a closed set of camera diagnostic fields. Missing/unknown checks,
  stale/replayed evidence, unavailable frames and malformed/non-finite model output remain `UNCERTAIN` with no
  fabricated inference values. Explicit statistical failure or OOD is `DEGRADED` as the design declares.
- Candidate temperature scaling and the two example OOD methods remain explicitly pending AD-03. All parameters
  come from the model metadata, with no default. Stable postprocessing shifts bin logits before division by a
  positive temperature and refuses wrong-shape, non-floating or non-finite logits. No training/update path exists.

**Test artifacts.**
- `tests/fixtures/make_camera_model.py`: standard-library deterministic IR-7/opset-13/V-1 logits-model writer and
  an independent NumPy forward reference; all numeric values are TEST-ONLY.
- Checked-in `tests/fixtures/tiny-camera-model.onnx`: **1640 bytes**, SHA-256
  `016a737e777968993e6d830cd4ff8a16ebaf6f5e610004eab5e92e87386a1d8a`.
  Its metadata binds the genuine shared compat preprocessing and current owned postprocessing code.
- `tests/test_camera_inference.py`: parsing, malformed/unsupported byte contracts and graph identities, before-session
  refusal ordering, spool confinement, F07 states, output/provenance conformance and explicit no-training/import
  boundaries. Its optional runtime checks use the actual compat U4 command/environment template.
- `tests/camera_inference_probe.py`: nine isolated modes cover the genuine pinned loader/preprocessing, fixture
  logits against the independent reference, postprocessing formulas/extremes/refusals, repeats, the real owned
  corruption-camera-front-zone chain, path replacement after loading and before-session refusal cases.
  Fixture regeneration is separately checked against the actual shared preprocessing binding.

**Checks performed so far, and limits.**
- Python AST parsing of all changed Python files: pass. `git diff --check`: pass.
- Tiny pinned-interpreter `-S -s -B` standard-library-only probe: generated/inspected the fixed fixture, parsed its
  postprocessing binding, refused four malformed/truncated protobuf cases, verified one spool read and length/digest
  refusals. Neither NumPy nor ONNX Runtime was imported. No pytest or training process was started.
- **The full test suite and all nine genuine-runtime probe modes have NOT run.** The platform full regression owns
  the heavy test slot. The candidate is implemented for verification, not a passing or accepted increment.

After the coordinator releases the host slot, from `automotive/assured-aeb` run:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  XVERSE_COMPAT_SRC=/home/jefferson/xverse-compat/src \
  XVERSE_AEB_U4_SITE=<pinned-inference-env>/venv/lib/python3.13/site-packages \
  XVERSE_PLATFORM_PROFILES=<rc.1-export>/xdl/profiles \
  /dev/shm/compat-p6-venv/bin/python -I -B -m pytest -q -p no:cacheprovider tests --tb=short
```

Torch/ORT never run in the pytest host: every genuine-runtime probe is a fresh `unshare -rn` process with the real
pinned interpreter and U4 `-S -s -B` template. If compat/site/namespace prerequisites are missing those modes skip;
a skip is not runtime verification. No venv rebuild/download is required. Run independent review after verification;
acceptance and merge remain separate. This branch still contains the old stacked #1 baseline and needs reconciliation
with the independently reviewed #1 repair before assembled delivery; do not rebase or overwrite another worker's
branch automatically. The null/not-evaluated output-form amendment, spool writer, unit readiness/wiring, real-model
calibration/OOD choices and tolerances, inference budget and live/protocol gates remain open.

## Finding 4: independent parent source review, CHANGES REQUIRED (2026-10-24)

Input: ML implementation `33344df7f29c9053ec6cd4b51c3fff79e1de0916`, assembled with independently reviewed
WP-13 #1 repairs as `8eda0f842a5211a1e9edd0628110d2c1b40fd3f7`. The parent did not author the ML implementation.
Read the complete camera binding/spool, bounded static model reader, postprocessing, fixture writer/probe and tests.
No pytest or numerical framework was run; the full platform regression still owns the test slot.

**R13ML-1, MEDIUM: malformed/contradictory F07 checks can be nominal.** A tiny public `CameraInference.step` probe
with the existing synthetic spool/inference fixture accepts a smart-camera logical verdict `pass` whose `failed`
list contains `bad-input`; output is `NOMINAL`, probability 0.8. A second probe adds an undeclared fourth member
under `sensorSelfCheck`, also yielding `NOMINAL`. `_verdict` validates member types but not the pass/failure-list
consistency; `step` does not close the sensor-self-check member set. This contradicts the claimed strict F07/
malformed-input refusal contract and can hide contradictory source evidence.

Repair design must precede code: require the three declared self-check classes only and consistent verdict/failed
forms (pass/not-evaluated with no failed codes; fail with actual failed codes). Unknown or inconsistent forms yield
`UNCERTAIN` without calling inference. Preserve genuine fail->DEGRADED behaviour with valid source-format fixtures.
Add public consumer cases for each malformed form and a genuine SmartCamera/FrontZone positive control.
No scientific threshold, timing window or calibration method is chosen by this repair.

Other source checks have no new blocker: byte-digest/schema/metadata/code/telemetry checks precede session creation;
spool reads are bounded and pinned to directory descriptors; the runtime record keeps three bare digest identities;
there is no training/update entry; unsupported ONNX constructs are explicitly refused as a local subset. This is
source inspection only. All nine genuine-loader/NumPy reference probes, fixture regeneration, actual provider/schema
and owner/assembled-suite checks remain mandatory and unrun. Scope/architecture limits and pending AD-03/AD-27
choices remain as finding 3 records. No acceptance or merge is made.

## Finding 5: R13ML-1 repair design before code (Codex, 2026-10-24)

Input is independent finding 4, now at branch `db99b8d` after #1 reconciliation `8eda0f8`.
Make the sensor-self-check map exactly `{logical, plausibility, statistical}`. Each check keeps exactly
`{verdict, failed}`; `failed` is a list of non-empty string codes, `pass` and `not-evaluated` require an empty list,
and `fail` requires at least one code. Unknown/contradictory forms return unknown check evidence, never a passing
classification. Apply the same verdict-consistency helper to front-zone integrity. No threshold, timing, class
meaning, calibration or OOD method changes.

The public CameraInference consumer must return `UNCERTAIN` with null inference fields and must not call its
inference function on an inconsistent check or a fourth self-check class. Preserve source-conforming statistical
`fail` with actual failed codes as `DEGRADED`. Correct the synthetic failure fixture accordingly and add regression
cases per class/form, the undeclared class and a genuine SmartCamera -> FrontZone positive/failure control.
Heavy verification remains deferred until the coordinator releases the host. After implementation the parent
will independently re-review this narrow repair before acceptance; no pytest or numerical framework is run here.

## Finding 6: R13ML-1 implementation and limited verification (Codex, 2026-10-24)

Implemented the separate design of finding 5 (`cf467d3`): `_verdict` now checks consistent pass/not-evaluated versus
failure-code forms, and the public consumer closes the sensor-self-check map to its three declared classes. The
synthetic statistical-failure fixture now includes a real failed code. Added 22 regression cases: six contradictory/
unknown forms across three classes, a fourth class, contradictory front-zone integrity, and two genuine owned
SmartCamera -> FrontZone controls (passing and deliberately failing the explicit TEST-ONLY mean-luma threshold).
Valid statistical failure is still `DEGRADED`; nothing chooses or changes a scientific threshold.

AST parsing and `git diff --check` pass. A tiny pinned `-S -s -B` standard-library public-consumer probe used the
actual owned corruption/camera/front-zone producer and a synthetic inference callable: its valid record is
`NOMINAL`, contradictory logical-pass and undeclared fourth-class records are `UNCERTAIN` without an inference
call, and a source-conforming statistical failure is `DEGRADED`. Neither NumPy nor ONNX Runtime nor pytest was
imported. This does not replace the unrun full suite or the nine genuine-loader numerical probes in finding 3.

Independent parent re-review is now required; no acceptance or merge is claimed. To exercise the new regression
cases after the host slot is released, the finding-3 full-suite command remains applicable; a focused first pass is
that command with `tests/test_camera_inference.py` in place of `tests`. The fixture's scientific/model approval and
all remaining wiring, protocol and live gates are unchanged.

## Finding 7: independent parent R13ML-1 successor review, PASS; genuine runtime suite pending

Reviewed repair `289117f1b9c6cafded655e7747d792831e33f012` against design `cf467d3` and finding 4.
The parent did not author the repair. The exact three-class self-check map and verdict/failure-code consistency
checks now refuse the reproduced malformed records before inference; source-conforming statistical failures retain
the declared degraded outcome. Existing output/provenance, frozen binding, inference and diagnostic thresholds are
unchanged. The synthetic failing fixture was corrected to match the real producer's format.

**Verification erratum:** the initial "seven checks pass" statement was written before its tool output was
inspected. The actual tiny probe passed the extra-class, contradictory-integrity and genuine passing producer
controls, then failed constructing the statistical-failure fixture: its minMeanLuma and maxMeanLuma are both 255,
which the real producer correctly rejects. The three remaining class checks were not reached. The source-review
assessment of the production repair remains, but full verification is pending and the test fixture needs repair
(finding 8). No pytest, NumPy or ONNX Runtime was run, and no acceptance or merge was made.

## Finding 8: statistical-failure fixture finding and repair design, before code (2026-10-24)

The new `test_genuine_smart_camera_and_front_zone_forms_remain_usable(True, ...)` uses minMeanLuma=255 and
maxMeanLuma=255. Real `SmartCameraParams.from_record` refuses equal bounds, so it cannot exercise the intended
valid statistical failure. The initial direct smoke used a different valid fixture, which did not verify this
exact regression function. Repair only the TEST-ONLY lower mean bound to a value below the existing upper bound
and above this fixture's observed mean. Keep the valid producer, actual statistical fail and expected degraded
outcome. No production threshold or scientific parameter changes. Re-run the exact seven named direct controls,
then the full genuine-runtime suite when the heavy slot is released. The parent review record is corrected above;
no passing result is claimed for the failed invocation.

## Finding 9: TEST-ONLY bound repair and exact direct-control results (Codex, 2026-10-24)

Changed only the genuine failing producer fixture's TEST-ONLY lower mean bound from 255 to 254, preserving the
upper bound 255. The real producer now accepts that declared interval and reports the intended statistical failure.
Ran the exact seven named controls directly with the pinned `-S -s -B` interpreter and AST-selected undecorated test
functions: undeclared fourth class, contradictory front integrity, genuine producer pass, genuine producer fail,
and contradictory logical/plausibility/statistical pass-with-failed-code forms. **All seven returned successfully**.
Neither pytest nor NumPy/ORT/torch was imported. The full suite and nine numerical probes remain unrun.

**Additional test-coverage finding, before any further repair:** the malformed-check tests do not yet place a frame
in their spool. Therefore their no-inference/UNCERTAIN expectations could also pass at the later missing-frame guard
if the earlier diagnostic rejection regressed. The genuine producer controls and the separate source review still
exercise a valid frame, but those named malformed-input regression cases need a usable frame to be decisive.
Recommend `_spool_file(tmp_path)` in the contradictory-class, extra-class, front-integrity and earlier invalid-input
setups, then demonstrate that the pre-repair diagnostic logic fails them. This is a TEST-ONLY setup repair; do not
change production diagnostics, thresholds or methods to make a test pass. Coordinator disposition is pending.

## Finding 10: coordinator-approved TEST-ONLY non-vacuity repair design, before code

The coordinator approved supplying valid frames in malformed-input regression setups. Also replace the earlier
invalid-input test's raising-only inference stub with a call-recording, otherwise valid result: production deliberately
converts inference exceptions into unknown evidence, so a swallowed assertion alone cannot prove inference was never
called. Assert an empty call list explicitly. No production module or threshold changes.

After repair, re-run the exact seven direct named controls plus the earlier malformed-input parameter cases. For a
cheap negative control, load the historical pre-R13ML-1 camera module from `8eda0f8` into an isolated in-memory module;
run the decisive malformed-check cases with valid spool frames and require assertions to fail. Keep the current
source untouched, restore any test namespace/module aliases afterwards, and import no pytest/numerical framework.
This proves the new regression setup detects the independent finding, rather than merely reaching a later missing
frame or catching an inference-stub exception. Full owning/numerical suites remain separately pending.

## Finding 11: decisive TEST-ONLY setup verification (Codex, 2026-10-24)

After design `12294a1`, supplied valid spool frames in the four malformed-input test setups. The earlier generic
invalid-evidence test now records inference calls and returns an otherwise valid result, rather than relying on an
exception the production consumer intentionally catches. No production source or scientific value changed.

Exact direct execution with the pinned `-S -s -B` interpreter, AST-selected undecorated test functions and fresh
scratch spools gives **7 named controls passed**, plus **10 earlier invalid-evidence parameter cases passed**.
Loaded historical pre-R13ML-1 source `8eda0f8` in a separate in-memory module without changing any source file;
all **5** malformed-check controls (fourth class, front integrity, logical, plausibility, statistical) then fail their
assertions as required. Restored the current test module alias afterwards. The negative control demonstrates that
usable frames reach the old erroneous inference path and the tests detect it. Neither pytest nor NumPy/ORT/torch
was imported; full/numerical suite verification is still pending. This closes finding 9's test-setup gap only.

## Independent successor verification and delegated acceptance (Codex, 2026-10-24)

Reviewed exact candidate `d7d4db50ee98203142e694ac759ed6d4daab8255` and its test-only successor diff. The corrected test independently exercises the approved production contract; source behavior is unchanged by that repair. Actual complete owning suite: **599 passed in 34.62s**, no skips. Receipt and full log: thesis `specs/002-assured-aeb/review/codex-successor-verification-20261024/ml-path/` (log SHA-256 `6d5d2575c0c456d5fbbefd47f583132bd5b99e62ee7fa8df82e67a3fcd56cbb7`). The prior failure remains retained and is not counted as a pass.

Accepted under the recorded author engineering delegation, flagged for author review, for isolated main assembly and complete assembled-suite verification. Scope: Frozen local-model contract, genuine pinned inference session path and diagnostic refusal only. All nine network-isolated genuine numerical/refusal/telemetry modes executed with no skips. Temperature/entropy implementations are selectable methods pending AD03, not approved calibrations or scientific thresholds. No real trained model, fit claim or live runtime wiring. Carried review limits remain; no protocol freeze, live execution or scientific acceptance follows.
