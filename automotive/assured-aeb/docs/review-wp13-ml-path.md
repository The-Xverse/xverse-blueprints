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
